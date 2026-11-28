"""Pure snapshot validation and comparison; no tokenizer dependency or I/O."""
from __future__ import annotations

import copy
import re
from .errors import ContractError

MAX_CASES = 256
MAX_CHARS = 1_000_000
MAX_SEQUENCE = 262_144
MAX_TOTAL_IDS = 1_000_000
HASH = re.compile(r'[0-9a-f]{64}\Z')
OPTIONS = {'route', 'add_special_tokens', 'add_generation_prompt', 'continue_final_message'}
CASE_KEYS = {'id', 'messages_sha256', 'rendered_text', 'input_ids', 'tokens',
             'direct_ids', 'unprocessed_ids', 'postprocessed_ids'}


def require(condition, message='Invalid snapshot structure.', code='INVALID_SNAPSHOT'):
    if not condition:
        raise ContractError(code, message)


def exact_keys(value, keys, code='INVALID_SNAPSHOT'):
    require(type(value) is dict and set(value) == set(keys), 'Unexpected object fields.', code)


def text(value, *, nonempty=False):
    if type(value) is not str or (nonempty and not value):
        return False
    try:
        value.encode('utf-8')
    except UnicodeError:
        return False
    return True


def validate_options(options, code='INVALID_SNAPSHOT'):
    exact_keys(options, OPTIONS, code)
    require(options['route'] in ('direct', 'render_then_encode'), 'Unknown capture route.', code)
    for key in OPTIONS - {'route'}:
        require(type(options[key]) is bool, 'Options must be booleans.', code)
    require(not (options['add_generation_prompt'] and options['continue_final_message']),
            'Generation and continuation are mutually exclusive.', code)
    require(not (options['route'] == 'direct' and options['add_special_tokens']),
            'Direct capture cannot enable extra special tokens.', code)


def validate_snapshot(snapshot: dict) -> None:
    exact_keys(snapshot, {'schema_version', 'producer', 'runtime', 'artifacts', 'options', 'cases'})
    # Check version field types before structure, but decide support only after
    # the complete v1-shaped snapshot has passed validation.
    require(type(snapshot['schema_version']) is int)
    require(text(snapshot['producer'], nonempty=True) and len(snapshot['producer']) <= 128)
    exact_keys(snapshot['runtime'], {'transformers', 'tokenizers', 'jinja2'})
    require(all(text(v, nonempty=True) and len(v) <= 128 for v in snapshot['runtime'].values()))
    exact_keys(snapshot['artifacts'], {'tokenizer_sha256', 'template_sha256', 'vocabulary_sha256'})
    require(all(type(v) is str and HASH.fullmatch(v) for v in snapshot['artifacts'].values()),
            'Invalid artifact fingerprint.')
    validate_options(snapshot['options'])
    cases = snapshot['cases']
    require(type(cases) is list and bool(cases), 'At least one case is required.')
    require(len(cases) <= MAX_CASES, 'Case budget exceeded.', 'BUDGET_EXCEEDED')
    seen, total = set(), 0
    for case in cases:
        exact_keys(case, CASE_KEYS)
        ident = case['id']
        require(text(ident, nonempty=True) and len(ident) <= 128, 'Invalid case identifier.')
        require(ident not in seen, 'Duplicate case identifier.')
        seen.add(ident)
        require(type(case['messages_sha256']) is str and HASH.fullmatch(case['messages_sha256']),
                'Invalid input fingerprint.')
        require(text(case['rendered_text']), 'Rendered text must be UTF-8 text.')
        require(len(case['rendered_text']) <= MAX_CHARS, 'Render budget exceeded.', 'BUDGET_EXCEEDED')
        for key in ('input_ids', 'direct_ids', 'unprocessed_ids', 'postprocessed_ids'):
            seq = case[key]
            require(type(seq) is list, 'Token IDs must be a list.')
            require(len(seq) <= MAX_SEQUENCE, 'Token sequence budget exceeded.', 'BUDGET_EXCEEDED')
            require(all(type(v) is int and 0 <= v <= 2**32-1 for v in seq),
                    'Token IDs must be unsigned integers, not booleans or floats.')
        tokens = case['tokens']
        require(type(tokens) is list and len(tokens) == len(case['input_ids']))
        require(all(text(v) for v in tokens), 'Token spellings must be UTF-8 text.')
        require(sum(len(v) for v in tokens) <= MAX_CHARS, 'Spelling budget exceeded.', 'BUDGET_EXCEEDED')
        options = snapshot['options']
        source = ('direct_ids' if options['route'] == 'direct' else
                  'postprocessed_ids' if options['add_special_tokens'] else 'unprocessed_ids')
        require(case['input_ids'] == case[source], 'Selected IDs disagree with the recorded route.')
        total += len(case['input_ids'])
        require(total <= MAX_TOTAL_IDS, 'Total token budget exceeded.', 'BUDGET_EXCEEDED')
    require(snapshot['schema_version'] == 1 and
            snapshot['producer'] in ('chat-input-contract/0.1.0', 'chat-input-contract/0.2.0'),
            'Snapshot version is structurally valid but unsupported.', 'UNSUPPORTED_VERSION')


def first_difference(a, b):
    for index, (left, right) in enumerate(zip(a, b)):
        if left != right:
            return index
    return None if len(a) == len(b) else min(len(a), len(b))


def compare_snapshots(baseline: dict, candidate: dict, *, include_content: bool = False) -> dict:
    """Compare a declared baseline. Drift is not a model-quality verdict."""
    require(type(include_content) is bool, 'include_content must be boolean.')
    validate_snapshot(baseline)
    validate_snapshot(candidate)
    provenance = []
    for section in ('runtime', 'artifacts', 'options'):
        for key in sorted(baseline[section]):
            a, b = baseline[section][key], candidate[section][key]
            if a != b:
                provenance.append({'field': f'{section}.{key}', 'baseline': str(a), 'candidate': str(b)})
    left = {c['id']: c for c in baseline['cases']}
    right = {c['id']: c for c in candidate['cases']}
    intent_changed = any(baseline['options'][k] != candidate['options'][k]
                         for k in ('add_generation_prompt', 'continue_final_message'))
    vocab_changed = baseline['artifacts']['vocabulary_sha256'] != candidate['artifacts']['vocabulary_sha256']
    summary = {'total': 0, 'match': 0, 'drift': 0, 'incomparable': 0}
    results = []
    for ident in sorted(left.keys() | right.keys()):
        a, b = left.get(ident), right.get(ident)
        stages = []
        if a is None or b is None:
            stages.append('MISSING_CASE')
            status = 'incomparable'
        elif a['messages_sha256'] != b['messages_sha256']:
            stages.append('INPUT_CHANGED')
            status = 'incomparable'
        elif intent_changed:
            stages.append('INTENT_CHANGED')
            status = 'incomparable'
        else:
            if vocab_changed:
                stages.append('VOCABULARY_CHANGED')
            if a['rendered_text'] != b['rendered_text']:
                stages.append('RENDER_CHANGED')
            if a['unprocessed_ids'] != b['unprocessed_ids']:
                stages.append('TOKENIZATION_CHANGED')
            if a['input_ids'] != b['input_ids']:
                if (a['rendered_text'] == b['rendered_text'] and a['unprocessed_ids'] == b['unprocessed_ids']
                        and all(c['direct_ids'] == c['unprocessed_ids'] for c in (a, b))):
                    stages.append('POSTPROCESSING_CHANGED')
                else:
                    stages.append('TOKENS_CHANGED')
            if any(c['direct_ids'] != c['unprocessed_ids'] for c in (a, b)):
                stages.append('ROUTE_INCONSISTENCY')
            if a['tokens'] != b['tokens']:
                stages.append('TOKEN_SPELLING_CHANGED')
            status = 'drift' if stages else 'match'
        lengths = {}
        for side, c in (('baseline', a), ('candidate', b)):
            lengths[f'{side}_chars'] = None if c is None else len(c['rendered_text'])
            lengths[f'{side}_tokens'] = None if c is None else len(c['input_ids'])
        row = {'id': ident, 'status': status, 'stages': stages, 'lengths': lengths,
               'first_char_difference': first_difference(a['rendered_text'], b['rendered_text']) if a and b else None,
               'first_token_difference': first_difference(a['input_ids'], b['input_ids']) if a and b else None}
        if include_content:
            row['content'] = {side: None if c is None else
                              copy.deepcopy({key: c[key] for key in ('rendered_text', 'input_ids', 'tokens')})
                              for side, c in (('baseline', a), ('candidate', b))}
        results.append(row)
        summary['total'] += 1
        summary[status] += 1
    overall = 'incomparable' if summary['incomparable'] else 'drift' if summary['drift'] else 'match'
    return {'schema_version': 1, 'status': overall, 'summary': summary,
            'provenance_changes': provenance, 'case_results': results}
