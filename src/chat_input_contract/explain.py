"""Bounded evidence windows and cautious interpretation, without model dependencies."""
from difflib import SequenceMatcher
from .core import compare_snapshots, require

ALIGNMENT_CELLS = 65_536
ALIGNMENT_ITEMS = 4_096
MAX_WINDOWS = 3


def _preview(sequence, start, end, kind):
    context, limit = (24, 160) if kind == 'characters' else (4, 32)
    return {'before': sequence[max(0, start-context):start],
            'changed': sequence[start:min(end, start+limit)],
            'after': sequence[end:end+context],
            'omitted_items': max(0, end-start-limit)}


def sequence_changes(a, b, *, include_content=False, kind='tokens'):
    """Return at most three windows, not a claim of unique or minimal edit distance."""
    require(type(include_content) is bool, 'Content export must be boolean.')
    require(kind in ('tokens', 'characters'), 'Unknown sequence kind.')
    prefix, common = 0, min(len(a), len(b))
    while prefix < common and a[prefix] == b[prefix]:
        prefix += 1
    if prefix == len(a) == len(b):
        return {'alignment': 'equal', 'total_windows': 0, 'omitted_windows': 0, 'windows': []}
    suffix = 0
    while suffix < common-prefix and a[len(a)-1-suffix] == b[len(b)-1-suffix]:
        suffix += 1
    a_end, b_end = len(a)-suffix, len(b)-suffix
    na, nb = a_end-prefix, b_end-prefix
    if na*nb <= ALIGNMENT_CELLS and na+nb <= ALIGNMENT_ITEMS:
        mode = 'bounded'
        operations = [(prefix+i, prefix+j, prefix+k, prefix+l)
                      for tag, i, j, k, l in SequenceMatcher(None, a[prefix:a_end], b[prefix:b_end], autojunk=False).get_opcodes()
                      if tag != 'equal']
    else:
        mode, operations = 'enclosing', [(prefix, a_end, prefix, b_end)]
    selected = operations if len(operations) <= MAX_WINDOWS else operations[:2] + operations[-1:]
    windows = []
    for i, j, k, l in selected:
        w = {'baseline_start': i, 'baseline_end': j, 'candidate_start': k, 'candidate_end': l,
             'removed_count': j-i, 'added_count': l-k}
        if include_content:
            w['baseline_preview'] = _preview(a, i, j, kind)
            w['candidate_preview'] = _preview(b, k, l, kind)
        windows.append(w)
    return {'alignment': mode, 'total_windows': len(operations),
            'omitted_windows': len(operations)-len(selected), 'windows': windows}


def _interpret(row, a, b):
    if row['status'] == 'incomparable':
        return 'inputs', ['Resolve missing cases or changed inputs/intent before interpreting token differences.']
    if any(c['direct_ids'] != c['unprocessed_ids'] for c in (a, b)):
        return 'consistency', ['The recorded direct and rendered routes disagree. Unstable rendering or capture behavior may explain this; postprocessing is not established as the cause.']
    stages = row['stages']
    if 'VOCABULARY_CHANGED' in stages:
        return 'vocabulary', ['Vocabulary identity changed. Equal integer IDs do not establish equal token meaning; review the mappings.']
    if 'RENDER_CHANGED' in stages:
        return 'rendering', ['The rendered text changed first. Token differences may be downstream consequences, not evidence that the tokenizer implementation is wrong.']
    if 'TOKENIZATION_CHANGED' in stages:
        return 'tokenization', ['The same rendered text produced different unprocessed IDs. Review tokenizer configuration and runtime provenance.']
    if 'POSTPROCESSING_CHANGED' in stages:
        return 'postprocessing', ['Rendered text and unprocessed IDs agree, but the selected paths differ. Review route/add_special_tokens and the recorded postprocessor output before changing the baseline.']
    if 'TOKEN_SPELLING_CHANGED' in stages:
        return 'token_spelling', ['Selected spellings differ; inspect the vocabulary/decoder evidence. This does not measure model quality.']
    return None, ['All recorded cases agree under the selected contract; unobserved inputs remain untested.']


def explain_snapshots(baseline, candidate, *, include_content=False):
    require(type(include_content) is bool, 'Content export must be boolean.')
    report = compare_snapshots(baseline, candidate)
    report['schema_version'] = 2
    report['content_included'] = include_content
    left = {c['id']: c for c in baseline['cases']}
    right = {c['id']: c for c in candidate['cases']}
    for row in report['case_results']:
        a, b = left.get(row['id']), right.get(row['id'])
        stage, notes = _interpret(row, a, b)
        if stage == 'consistency':
            row['stages'] = [s for s in row['stages'] if s != 'POSTPROCESSING_CHANGED']
        comparable = row['status'] != 'incomparable'
        row['analysis'] = {
            'earliest_stage': stage, 'notes': notes,
            'character_change': sequence_changes(a['rendered_text'], b['rendered_text'],
                                                include_content=include_content, kind='characters') if comparable else None,
            'token_change': sequence_changes(a['input_ids'], b['input_ids'],
                                            include_content=include_content) if comparable else None}
    return report
