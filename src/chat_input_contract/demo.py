"""Generate original tiny fixtures and exercise real good, bad and repaired paths."""
from pathlib import Path
from .capture import capture_manifest
from .core import compare_snapshots
from .errors import ContractError
from .io import write_bytes, write_json
from .report import render_html


def run_demo(directory) -> dict:
    root = Path(directory).resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ContractError('OUTPUT_CONFLICT', 'Demo needs a new or empty output directory.')
    try:
        from tokenizers import Tokenizer, models, pre_tokenizers, processors
    except ImportError:
        raise ContractError('CAPTURE_DEPENDENCY', 'Install the capture extra to run the real demo.') from None
    root.mkdir(parents=True, exist_ok=True)
    vocab = {'<unk>': 0, '<bos>': 1, '<eos>': 2, 'user': 3,
             'assistant': 4, ':': 5, 'hello': 6, 'world': 7, 'system': 8}
    backend = Tokenizer(models.WordLevel(vocab, unk_token='<unk>'))
    backend.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    backend.post_processor = processors.TemplateProcessing(
        single='<bos> $A <eos>', special_tokens=[('<bos>', 1), ('<eos>', 2)])
    write_bytes(root / 'tokenizer.json', backend.to_str(pretty=True).encode('utf-8'))
    template = ('{{ bos_token }} {% for m in messages %}{{ m.role }} : {{ m.content }} {{ eos_token }} '
                '{% endfor %}{% if add_generation_prompt %}assistant :{% endif %}')
    write_bytes(root / 'chat.jinja', template.encode('utf-8'))
    cases = [
        {'id': 'single-turn', 'messages': [{'role': 'user', 'content': 'hello'}]},
        {'id': 'multi-turn', 'messages': [{'role': 'user', 'content': 'hello'},
                                        {'role': 'assistant', 'content': 'world'},
                                        {'role': 'user', 'content': 'hello world'}]},
        {'id': 'whitespace', 'messages': [{'role': 'system', 'content': 'hello world'},
                                        {'role': 'user', 'content': ' hello\nworld '}]},
    ]
    snapshots = {}
    for name, route, add in (('direct', 'direct', False), ('safe', 'render_then_encode', False),
                             ('broken', 'render_then_encode', True)):
        manifest = {'schema_version': 1, 'tokenizer': 'tokenizer.json', 'template': 'chat.jinja',
                    'special_tokens': {'bos_token': '<bos>', 'eos_token': '<eos>', 'unk_token': '<unk>'},
                    'options': {'route': route, 'add_special_tokens': add,
                                'add_generation_prompt': True, 'continue_final_message': False}, 'cases': cases}
        manifest_path = root / f'{name}-manifest.json'
        write_json(manifest_path, manifest)
        snapshots[name] = capture_manifest(manifest_path)
        write_json(root / f'{name}-snapshot.json', snapshots[name])
    reports = {}
    for name in ('safe', 'broken'):
        reports[name] = compare_snapshots(snapshots['direct'], snapshots[name])
        write_json(root / f'{name}-report.json', reports[name])
        write_bytes(root / f'{name}-report.html', render_html(reports[name]).encode('utf-8'))
    if reports['safe']['status'] != 'match' or reports['broken']['status'] != 'drift':
        raise ContractError('DEMO_FAILED', 'The expected real good/bad path contrast did not occur.')
    if not all('POSTPROCESSING_CHANGED' in c['stages'] for c in reports['broken']['case_results']):
        raise ContractError('DEMO_FAILED', 'The expected postprocessing evidence did not occur.')
    return {'safe': reports['safe']['status'], 'broken': reports['broken']['status'],
            'cases': reports['safe']['summary']['total']}
