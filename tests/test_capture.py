import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest


def fixture(directory):
    from tokenizers import Tokenizer, models, pre_tokenizers, processors
    root = Path(directory)
    vocab = {'<unk>': 0, '<bos>': 1, '<eos>': 2, 'user': 3,
             'assistant': 4, ':': 5, 'hello': 6, 'world': 7, 'system': 8}
    backend = Tokenizer(models.WordLevel(vocab, unk_token='<unk>'))
    backend.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    backend.post_processor = processors.TemplateProcessing(
        single='<bos> $A <eos>', special_tokens=[('<bos>', 1), ('<eos>', 2)])
    backend.save(str(root / 'tokenizer.json'))
    (root / 'chat.jinja').write_text(
        '{{ bos_token }} {% for m in messages %}{{ m.role }} : {{ m.content }} {{ eos_token }} '
        '{% endfor %}{% if add_generation_prompt %}assistant :{% endif %}', encoding='utf-8')
    manifest = {'schema_version': 1, 'tokenizer': 'tokenizer.json', 'template': 'chat.jinja',
                'special_tokens': {'bos_token': '<bos>', 'eos_token': '<eos>', 'unk_token': '<unk>'},
                'options': {'route': 'direct', 'add_special_tokens': False,
                            'add_generation_prompt': True, 'continue_final_message': False},
                'cases': [{'id': 'hello', 'messages': [{'role': 'user', 'content': 'hello'}]}]}
    (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


class CaptureTests(unittest.TestCase):
    def setUp(self):
        try:
            self.capture = importlib.import_module('chat_input_contract.capture').capture_manifest
        except ModuleNotFoundError:
            self.fail('Missing real local capture implementation')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = fixture(self.root)

    def save(self, name='manifest.json'):
        path = self.root / name
        path.write_text(json.dumps(self.manifest), encoding='utf-8')
        return path

    def test_real_direct_ids_match_hand_calculation(self):
        s = self.capture(self.save())
        c = s['cases'][0]
        self.assertEqual(c['input_ids'], [1, 3, 5, 6, 2, 4, 5])
        self.assertEqual(c['unprocessed_ids'], c['direct_ids'])
        self.assertEqual(c['postprocessed_ids'], [1, 1, 3, 5, 6, 2, 4, 5, 2])
        self.assertEqual(s, self.capture(self.save()))
        self.assertNotIn(str(self.root), json.dumps(s))

    def test_template_runtime_version_is_recorded(self):
        import importlib.metadata
        s = self.capture(self.save())
        self.assertEqual(s['runtime'].get('jinja2'), importlib.metadata.version('jinja2'))

    def test_actual_bad_path_and_repair(self):
        from chat_input_contract.core import compare_snapshots
        baseline = self.capture(self.save())
        self.manifest['options'].update(route='render_then_encode', add_special_tokens=True)
        bad = self.capture(self.save('bad.json'))
        r = compare_snapshots(baseline, bad)
        self.assertEqual(r['status'], 'drift')
        self.assertIn('POSTPROCESSING_CHANGED', r['case_results'][0]['stages'])
        self.manifest['options']['add_special_tokens'] = False
        fixed = self.capture(self.save('fixed.json'))
        self.assertEqual(compare_snapshots(baseline, fixed)['status'], 'match')

    def test_inputs_untouched(self):
        paths = list(self.root.iterdir())
        before = {p.name: p.read_bytes() for p in paths}
        self.capture(self.root / 'manifest.json')
        self.assertEqual(before, {p.name: p.read_bytes() for p in paths})

    def test_manifest_invalid_rejected_before_library(self):
        mutations = [lambda m: m.update(schema_version=True),
                     lambda m: m.update(extra=1),
                     lambda m: m.update(cases=[]),
                     lambda m: m['options'].update(add_generation_prompt=1),
                     lambda m: m['options'].update(continue_final_message=True),
                     lambda m: m['cases'][0]['messages'][0].update(role='tool'),
                     lambda m: m['cases'][0]['messages'][0].update(content=[]),
                     lambda m: m['cases'].append(copy.deepcopy(m['cases'][0])),
                     lambda m: m.update(tokenizer='https://example.invalid/tokenizer.json'),
                     lambda m: m['special_tokens'].update(custom_token='x')]
        original = copy.deepcopy(self.manifest)
        for i, mutate in enumerate(mutations):
            with self.subTest(i=i):
                self.manifest = copy.deepcopy(original); mutate(self.manifest)
                with self.assertRaises(ValueError):
                    self.capture(self.save())

    def test_template_failure_does_not_echo_prompt(self):
        (self.root / 'chat.jinja').write_text("{{ raise_exception(messages[0].content) }}", encoding='utf-8')
        self.manifest['cases'][0]['messages'][0]['content'] = 'private-input-example'
        with self.assertRaises(ValueError) as cm:
            self.capture(self.save())
        self.assertNotIn('private-input-example', str(cm.exception))

    def test_vocabulary_fingerprint_covers_unobserved_tokens(self):
        from chat_input_contract.core import compare_snapshots
        baseline = self.capture(self.save())
        p = self.root / 'tokenizer.json'; value = json.loads(p.read_text(encoding='utf-8'))
        value['model']['vocab']['not-observed'] = 9
        p.write_text(json.dumps(value), encoding='utf-8')
        changed = self.capture(self.save())
        self.assertEqual(baseline['cases'][0]['input_ids'], changed['cases'][0]['input_ids'])
        self.assertEqual(compare_snapshots(baseline, changed)['status'], 'drift')

    def test_empty_special_token_matches_declared_string_contract(self):
        self.manifest['special_tokens']['bos_token'] = ''
        s = self.capture(self.save())
        self.assertEqual(s['cases'][0]['input_ids'], [3, 5, 6, 2, 4, 5])

    def test_capture_rejects_snapshot_larger_than_reader_budget(self):
        # Every per-case budget permits this. JSON escaping expands NUL to six bytes.
        template = '{{ ' + json.dumps('\0') + ' * 950000 }}'
        (self.root / 'chat.jinja').write_text(template, encoding='utf-8')
        self.manifest['cases'] = [
            {'id': str(i), 'messages': [{'role': 'user', 'content': 'hello'}]}
            for i in range(12)]
        with self.assertRaises(ValueError) as cm:
            self.capture(self.save())
        self.assertEqual(cm.exception.code, 'BUDGET_EXCEEDED')

    def test_missing_tokenizer_no_network_fallback(self):
        (self.root / 'tokenizer.json').unlink()
        with self.assertRaises(ValueError):
            self.capture(self.save())


if __name__ == '__main__':
    unittest.main()
