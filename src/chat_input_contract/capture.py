"""Explicit local fast-tokenizer capture. Does not load model weights or remote code."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
from .core import (MAX_CASES, MAX_CHARS, MAX_SEQUENCE, MAX_TOTAL_IDS, exact_keys,
                   require, text, validate_options, validate_snapshot)
from .errors import ContractError
from .io import decode_json, json_bytes, load_json, read_bytes

SPECIAL_KEYS = {'bos_token', 'eos_token', 'unk_token', 'pad_token', 'sep_token', 'cls_token', 'mask_token'}


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


def capture_manifest(path: str | Path) -> dict:
    manifest, (_, tokenizer_path, template_path) = manifest_inputs(path)
    raw = read_bytes(tokenizer_path, 64 * 1024 * 1024)
    # Strict JSON check before the native tokenizer parser; no from_pretrained fallback.
    decode_json(raw)
    template_raw = read_bytes(template_path, 128 * 1024)
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
            'schema_version': 1, 'producer': 'chat-input-contract/0.1.0',
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
