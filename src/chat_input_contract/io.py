"""Bounded strict JSON input and complete, no-clobber output publication."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
from .errors import ContractError

MAX_JSON_BYTES = 64 * 1024 * 1024


def read_bytes(path, max_bytes):
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(max_bytes + 1)
    except OSError:
        raise ContractError('INPUT_IO', 'Cannot read the requested local file.') from None
    if len(raw) > max_bytes:
        raise ContractError('BUDGET_EXCEEDED', 'Input byte budget exceeded.')
    return raw


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON number')


def _finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError('Non-finite JSON exponent')
    return parsed


def decode_json(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=_constant, parse_float=_finite_float)
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError('INVALID_JSON', 'Expected finite UTF-8 JSON with unique object keys.') from None


def load_json(path, max_bytes=MAX_JSON_BYTES):
    return decode_json(read_bytes(path, max_bytes))


def json_bytes(value):
    try:
        raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ContractError('INVALID_OUTPUT', 'Output cannot be serialized as finite UTF-8 JSON.') from None
    if len(raw) > MAX_JSON_BYTES:
        raise ContractError('BUDGET_EXCEEDED', 'Serialized JSON exceeds the reader byte budget.')
    return raw


def check_output(path, *, force=False, protected=()):
    try:
        target = Path(path).resolve()
        for source in protected:
            other = Path(source).resolve()
            if target == other or (target.exists() and other.exists() and target.samefile(other)):
                raise ContractError('OUTPUT_CONFLICT', 'An output would overwrite an input or another output.')
        if target.exists() and (not force or not target.is_file()):
            raise ContractError('OUTPUT_CONFLICT', 'Output already exists; use --force only for replaceable output.')
        return target
    except OSError:
        raise ContractError('OUTPUT_IO', 'Cannot inspect the requested output path.') from None


def write_bytes(path, raw, *, force=False, protected=()):
    target = check_output(path, force=force, protected=protected)
    tmp = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix='.cic-', dir=target.parent, delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck aliases immediately before publication. Inputs are trusted local paths.
        check_output(path, force=force, protected=protected)
        if force:
            os.replace(tmp, target)
        else:
            # Same-filesystem hard link provides atomic exclusive publication.
            os.link(tmp, target)
    except OSError:
        raise ContractError('OUTPUT_IO', 'Could not publish the complete output file.') from None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def write_json(path, obj, *, force=False, protected=()):
    raw = json_bytes(obj)
    write_bytes(path, raw, force=force, protected=protected)
