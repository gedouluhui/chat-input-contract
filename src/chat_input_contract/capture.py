"""Explicit local fast-tokenizer capture. Does not load model weights or remote code."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from .core import (MAX_CASES, MAX_CHARS, MAX_SEQUENCE, MAX_TOTAL_IDS, exact_keys,
                   require, text, validate_options, validate_snapshot)
from .errors import ContractError
from .io import decode_json, json_bytes, load_json, read_bytes

SPECIAL_KEYS = {'bos_token', 'eos_token', 'unk_token', 'pad_token', 'sep_token', 'cls_token', 'mask_token'}
CAPTURE_TIMEOUT_SECONDS = 60
CAPTURE_OUTPUT_BUDGET_BYTES = 64 * 1024 * 1024
CAPTURE_MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024
CAPTURE_CHUNK_BYTES = 64 * 1024


def _close_stream(stream):
    try:
        stream.close()
    except OSError:
        pass


def _limit_worker_memory():
    """Apply an address-space ceiling in the child, where the OS supports it."""
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    limits = [CAPTURE_MEMORY_LIMIT_BYTES]
    limits.extend(limit for limit in (soft, hard) if limit != resource.RLIM_INFINITY)
    resource.setrlimit(resource.RLIMIT_AS, (min(limits), hard))


def _run_worker(worker, payload, *, env=None):
    """Stream a worker's pipes under one byte budget, always killing/reaping it.

    Only bounded stdout is retained. Stderr is drained and counted, never stored
    or exported. Threads keep both pipes moving while stdin is written, so a
    noisy worker cannot deadlock or bypass the budget through the other pipe.
    """
    command = [sys.executable, str(worker)] if isinstance(worker, (str, os.PathLike)) else list(worker)
    stdout = bytearray()
    lock = threading.Lock()
    exceeded = threading.Event()
    read_errors = []
    total = 0
    process = None
    threads = []
    need_group_cleanup = False
    deadline = time.monotonic() + CAPTURE_TIMEOUT_SECONDS

    def read_pipe(stream, keep):
        nonlocal total
        try:
            while not exceeded.is_set():
                chunk = stream.read(CAPTURE_CHUNK_BYTES)
                if not chunk:
                    break
                with lock:
                    if total + len(chunk) > CAPTURE_OUTPUT_BUDGET_BYTES:
                        exceeded.set()
                        break
                    total += len(chunk)
                    if keep:
                        stdout.extend(chunk)
        except OSError:
            read_errors.append(True)

    def write_input(stream):
        view = memoryview(payload)
        try:
            while view and not exceeded.is_set():
                written = stream.write(view)
                if not written:
                    break
                view = view[written:]
        except OSError:
            # A worker may reject input or exit early; its status decides failure.
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    kwargs = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                  bufsize=0, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if os.name == 'posix':
        kwargs['preexec_fn'] = _limit_worker_memory
        kwargs['start_new_session'] = True
    try:
        process = subprocess.Popen(command, **kwargs)
        threads = [threading.Thread(target=read_pipe, args=(process.stdout, True), daemon=True),
                   threading.Thread(target=read_pipe, args=(process.stderr, False), daemon=True),
                   threading.Thread(target=write_input, args=(process.stdin,), daemon=True)]
        for thread in threads:
            thread.start()
        while process.poll() is None:
            if exceeded.is_set():
                need_group_cleanup = True
                raise ContractError('CAPTURE_OUTPUT_BUDGET',
                                    'Local capture worker exceeded its output budget; raw output is not exported.')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                need_group_cleanup = True
                raise ContractError('CAPTURE_TIMEOUT', 'Capture exceeded its wall-clock limit.')
            exceeded.wait(min(0.01, remaining))
        try:
            returncode = process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            need_group_cleanup = True
            raise ContractError('CAPTURE_TIMEOUT', 'Capture exceeded its wall-clock limit.') from None
        if exceeded.is_set():
            need_group_cleanup = True
            raise ContractError('CAPTURE_OUTPUT_BUDGET',
                                'Local capture worker exceeded its output budget; raw output is not exported.')
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            need_group_cleanup = True
            raise ContractError('CAPTURE_TIMEOUT',
                                'Capture pipes remained open after the worker exited; inherited handles were not closed before the deadline.')
        if read_errors:
            raise ContractError('CAPTURE_FAILED', 'Could not read the local capture worker output.')
        if returncode != 0:
            raise ContractError('CAPTURE_FAILED', 'Local capture worker failed; raw stderr is not exported.')
        return bytes(stdout)
    except ContractError:
        raise
    except OSError:
        raise ContractError('CAPTURE_FAILED', 'Could not start or clean up the local capture worker.') from None
    finally:
        if process is not None:
            if need_group_cleanup and os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
            process.wait()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    threading.Thread(target=_close_stream, args=(stream,), daemon=True).start()
        cleanup_deadline = time.monotonic() + 1
        for thread in threads:
            thread.join(timeout=max(0, cleanup_deadline - time.monotonic()))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_digest(value):
    return digest(json.dumps(value, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(',', ':')).encode('utf-8'))


def manifest_inputs(path):
    """Validate before importing Transformers; return manifest and exact local inputs."""
    manifest_path = Path(path).resolve()
    manifest = load_json(manifest_path, max_bytes=2 * 1024 * 1024)
    code = 'INVALID_MANIFEST'
    exact_keys(manifest, {'schema_version', 'tokenizer', 'template', 'special_tokens', 'options', 'cases'}, code)
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1,
            'Unknown manifest version.', code)
    for key in ('tokenizer', 'template'):
        name = manifest[key]
        require(text(name, nonempty=True) and '://' not in name and '\x00' not in name,
                'Expected a local input path, not a URL.', code)
    specials = manifest['special_tokens']
    require(type(specials) is dict and set(specials) <= SPECIAL_KEYS, 'Unknown special-token setting.', code)
    require(all(text(v) and len(v) <= 4096 for v in specials.values()),
            'Special tokens must be strings.', code)
    validate_options(manifest['options'], code)
    cases = manifest['cases']
    require(type(cases) is list and bool(cases), 'At least one input case is required.', code)
    require(len(cases) <= MAX_CASES, 'Case budget exceeded.', 'BUDGET_EXCEEDED')
    seen, chars = set(), 0
    for case in cases:
        exact_keys(case, {'id', 'messages'}, code)
        ident = case['id']
        require(text(ident, nonempty=True) and len(ident) <= 128, 'Invalid case identifier.', code)
        require(ident not in seen, 'Duplicate case identifier.', code)
        seen.add(ident)
        require(type(case['messages']) is list and bool(case['messages']), 'Messages must be nonempty.', code)
        for message in case['messages']:
            exact_keys(message, {'role', 'content'}, code)
            require(message['role'] in ('system', 'user', 'assistant'), 'Unsupported message role.', code)
            require(text(message['content']), 'Only text messages are supported.', code)
            chars += len(message['content'])
            require(chars <= MAX_CHARS, 'Message character budget exceeded.', 'BUDGET_EXCEEDED')
    tokenizer = (manifest_path.parent / manifest['tokenizer']).resolve()
    template = (manifest_path.parent / manifest['template']).resolve()
    return manifest, (manifest_path, tokenizer, template)


@dataclass(frozen=True)
class PreparedCapture:
    payload: bytes
    protected: tuple[Path, ...]


def prepare_capture(path: str | Path) -> PreparedCapture:
    manifest, protected = manifest_inputs(path)
    _, tokenizer_path, template_path = protected
    raw = read_bytes(tokenizer_path, 64 * 1024 * 1024)
    decode_json(raw)
    template_raw = read_bytes(template_path, 128 * 1024)
    payload = json.dumps({'manifest': manifest,
                          'tokenizer': base64.b64encode(raw).decode('ascii'),
                          'template': base64.b64encode(template_raw).decode('ascii')},
                         ensure_ascii=True, allow_nan=False).encode('utf-8')
    require(len(payload) <= 128 * 1024 * 1024, 'Capture transport budget exceeded.', 'BUDGET_EXCEEDED')
    return PreparedCapture(payload, protected)


def capture_prepared(prepared: PreparedCapture) -> dict:
    """Run native dependencies behind a bounded subprocess output boundary.

    This limits run duration, combined pipe output and (on POSIX) address space,
    not OS privileges. It is not a hostile-code or hard RAM/CPU sandbox.
    """
    env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONIOENCODING='utf-8')
    stdout = _run_worker([sys.executable, '-m', 'chat_input_contract._worker'], prepared.payload, env=env)
    result = decode_json(stdout)
    if type(result) is dict and set(result) == {'error'}:
        messages = {
            'CAPTURE_DEPENDENCY': 'Install the tested capture extra.',
            'CAPTURE_INCONSISTENT': 'Observed direct and rendered routes disagree; use a stable template.',
            'BUDGET_EXCEEDED': 'Capture exceeded its declared size budget.',
        }
        code = result['error'] if result['error'] in messages else 'CAPTURE_FAILED'
        raise ContractError(code, messages.get(code, 'Local tokenizer or template execution failed.'))
    validate_snapshot(result)
    return result


def capture_manifest(path: str | Path) -> dict:
    return capture_prepared(prepare_capture(path))


def execute_capture(manifest: dict, raw: bytes, template_raw: bytes) -> dict:
    """Internal worker implementation; callers should use capture_manifest."""
    try:
        template = template_raw.decode('utf-8')
    except UnicodeError:
        raise ContractError('INVALID_MANIFEST', 'Template must be UTF-8 text.') from None
    try:
        from tokenizers import Tokenizer
        from transformers import PreTrainedTokenizerFast
    except ImportError:
        raise ContractError('CAPTURE_DEPENDENCY', 'Install the capture extra with the tested dependencies.') from None
    try:
        # Parse the same bytes we fingerprint; do not reopen a potentially changed file.
        backend = Tokenizer.from_str(raw.decode('utf-8'))
        tokenizer = PreTrainedTokenizerFast(tokenizer_object=backend, chat_template=template,
                                           **manifest['special_tokens'])
        result = {
            'schema_version': 1, 'producer': 'chat-input-contract/0.2.0',
            'runtime': {name: importlib.metadata.version(name) for name in ('transformers', 'tokenizers', 'jinja2')},
            'artifacts': {
                'tokenizer_sha256': digest(raw), 'template_sha256': digest(template_raw),
                'vocabulary_sha256': canonical_digest({'vocab': tokenizer.get_vocab(),
                                                       'special_tokens': tokenizer.special_tokens_map})},
            'options': dict(manifest['options']), 'cases': []}
        options = manifest['options']
        flags = {k: options[k] for k in ('add_generation_prompt', 'continue_final_message')}
        total = 0
        for case in manifest['cases']:
            messages = case['messages']
            rendered = tokenizer.apply_chat_template(messages, tokenize=False, **flags)
            require(type(rendered) is str, 'Expected a text rendering.', 'CAPTURE_FAILED')
            require(len(rendered) <= MAX_CHARS, 'Render budget exceeded.', 'BUDGET_EXCEEDED')
            direct = tokenizer.apply_chat_template(messages, tokenize=True, return_dict=False,
                                                   padding=False, truncation=False, **flags)
            unprocessed = tokenizer.encode(rendered, add_special_tokens=False, padding=False, truncation=False)
            postprocessed = tokenizer.encode(rendered, add_special_tokens=True, padding=False, truncation=False)
            for seq in (direct, unprocessed, postprocessed):
                require(type(seq) is list and len(seq) <= MAX_SEQUENCE,
                        'Token sequence budget exceeded.', 'BUDGET_EXCEEDED')
            require(direct == unprocessed,
                    'Observed rendering and direct route disagree.', 'CAPTURE_INCONSISTENT')
            selected = direct if options['route'] == 'direct' else (
                postprocessed if options['add_special_tokens'] else unprocessed)
            total += len(selected)
            require(total <= MAX_TOTAL_IDS, 'Total token budget exceeded.', 'BUDGET_EXCEEDED')
            result['cases'].append({'id': case['id'], 'messages_sha256': canonical_digest(messages),
                                    'rendered_text': rendered, 'input_ids': selected,
                                    'tokens': tokenizer.convert_ids_to_tokens(selected),
                                    'direct_ids': direct, 'unprocessed_ids': unprocessed,
                                    'postprocessed_ids': postprocessed})
        validate_snapshot(result)
        # A successful capture must be serializable within its own reader's limit.
        json_bytes(result)
        return result
    except ContractError:
        raise
    except Exception:
        # Template exceptions can contain entire prompts. Do not echo library exception text.
        raise ContractError('CAPTURE_FAILED', 'Local tokenizer or template execution failed; check supported inputs.') from None
