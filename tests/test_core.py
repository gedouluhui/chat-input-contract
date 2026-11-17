import copy
import importlib
import unittest


def snapshot():
    return {
        'schema_version': 1, 'producer': 'chat-input-contract/0.1.0',
        'runtime': {'transformers': '5.8.0', 'tokenizers': '0.22.2', 'jinja2': '3.1.6'},
        'artifacts': {'tokenizer_sha256': 'a'*64, 'template_sha256': 'b'*64,
                      'vocabulary_sha256': 'c'*64},
        'options': {'route': 'direct', 'add_special_tokens': False,
                    'add_generation_prompt': True, 'continue_final_message': False},
        'cases': [{'id': 'hello', 'messages_sha256': 'd'*64,
                   'rendered_text': '<bos> hello <eos>', 'input_ids': [1, 4, 2],
                   'tokens': ['<bos>', 'hello', '<eos>'],
                   'direct_ids': [1, 4, 2], 'unprocessed_ids': [1, 4, 2],
                   'postprocessed_ids': [1, 1, 4, 2, 2]}]}


class CoreTests(unittest.TestCase):
    def setUp(self):
        try:
            self.core = importlib.import_module('chat_input_contract.core')
        except ModuleNotFoundError:
            self.fail('Missing pure comparison implementation')
        self.a = snapshot()
        self.b = copy.deepcopy(self.a)

    def compare(self, **kwargs):
        return self.core.compare_snapshots(self.a, self.b, **kwargs)

    def test_equal_redacted_and_immutable(self):
        before = copy.deepcopy(self.a)
        result = self.compare()
        self.assertEqual(result['status'], 'match')
        self.assertEqual(result['summary'], {'total': 1, 'match': 1, 'drift': 0, 'incomparable': 0})
        self.assertNotIn('content', result['case_results'][0])
        self.assertEqual(before, self.a)
        self.assertNotIn('rendered_text', str(result))

    def test_content_requires_opt_in(self):
        result = self.compare(include_content=True)
        self.assertEqual(result['case_results'][0]['content']['baseline']['input_ids'], [1, 4, 2])
        result['case_results'][0]['content']['baseline']['input_ids'][0] = 99
        self.assertEqual(self.a['cases'][0]['input_ids'][0], 1)

    def test_vocabulary_change_even_with_identical_ids(self):
        self.b['artifacts']['vocabulary_sha256'] = 'e'*64
        result = self.compare()
        self.assertEqual(result['status'], 'drift')
        self.assertIn('VOCABULARY_CHANGED', result['case_results'][0]['stages'])

    def test_missing_case_union_not_intersection(self):
        second = copy.deepcopy(self.b['cases'][0]); second['id'] = 'extra'
        self.b['cases'].append(second)
        result = self.compare()
        self.assertEqual(result['status'], 'incomparable')
        self.assertEqual(result['summary']['total'], 2)
        self.assertEqual(result['summary']['incomparable'], 1)
        self.assertIn('MISSING_CASE', result['case_results'][0]['stages'])

    def test_input_change_incomparable(self):
        self.b['cases'][0]['messages_sha256'] = 'f'*64
        self.assertEqual(self.compare()['status'], 'incomparable')

    def test_intent_change_not_called_bug(self):
        self.b['options']['add_generation_prompt'] = False
        self.assertEqual(self.compare()['case_results'][0]['stages'], ['INTENT_CHANGED'])

    def test_postprocessing_attribution_real_trace(self):
        self.b['options'].update(route='render_then_encode', add_special_tokens=True)
        c = self.b['cases'][0]
        c['input_ids'] = list(c['postprocessed_ids'])
        c['tokens'] = ['<bos>', '<bos>', 'hello', '<eos>', '<eos>']
        r = self.compare()['case_results'][0]
        self.assertEqual(r['status'], 'drift')
        self.assertIn('POSTPROCESSING_CHANGED', r['stages'])
        self.assertEqual(r['first_token_difference'], 1)
        self.assertIsNone(r['first_char_difference'])

    def test_safe_two_stage_matches(self):
        self.b['options']['route'] = 'render_then_encode'
        result = self.compare()
        self.assertEqual(result['status'], 'match')
        self.assertTrue(result['provenance_changes'])

    def test_render_prefix_difference(self):
        self.b['cases'][0]['rendered_text'] += ' '
        r = self.compare()['case_results'][0]
        self.assertIn('RENDER_CHANGED', r['stages'])
        self.assertEqual(r['first_char_difference'], len(self.a['cases'][0]['rendered_text']))

    def test_tokenization_and_prefix_difference(self):
        c = self.b['cases'][0]
        for key in ('input_ids', 'direct_ids', 'unprocessed_ids'):
            c[key].append(7)
        c['tokens'].append('more')
        r = self.compare()['case_results'][0]
        self.assertIn('TOKENIZATION_CHANGED', r['stages'])
        self.assertEqual(r['first_token_difference'], 3)

    def test_internal_route_inconsistency(self):
        self.b['cases'][0]['unprocessed_ids'] = [2]
        self.assertIn('ROUTE_INCONSISTENCY', self.compare()['case_results'][0]['stages'])

    def test_provenance_alone_not_behavioral_failure(self):
        self.b['runtime']['transformers'] = '5.9.0'
        self.b['artifacts']['tokenizer_sha256'] = 'e'*64
        r = self.compare()
        self.assertEqual(r['status'], 'match')
        self.assertEqual(len(r['provenance_changes']), 2)

    def test_invalid_shapes_and_types_rejected(self):
        changes = [
            lambda s: s.update(schema_version=True),
            lambda s: s.update(schema_version=1.0),
            lambda s: s.update(extra='no'),
            lambda s: s.update(cases=[]),
            lambda s: s['cases'].append(copy.deepcopy(s['cases'][0])),
            lambda s: s['cases'][0]['input_ids'].__setitem__(0, True),
            lambda s: s['cases'][0]['input_ids'].__setitem__(0, 1.0),
            lambda s: s['cases'][0]['input_ids'].__setitem__(0, -1),
            lambda s: s['cases'][0].update(tokens=[]),
            lambda s: s['cases'][0].update(messages_sha256='not a hash'),
            lambda s: s['options'].update(add_generation_prompt=1),
            lambda s: s['options'].update(continue_final_message=True),
            lambda s: s['options'].update(add_special_tokens=True),
            lambda s: s['cases'][0].update(input_ids=[7], tokens=['x']),
            lambda s: s['runtime'].update(extra='no'),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                bad = snapshot(); change(bad)
                with self.assertRaises(ValueError):
                    self.core.validate_snapshot(bad)

    def test_budget_rejected(self):
        self.b['cases'][0]['rendered_text'] = 'x' * 1_000_001
        with self.assertRaises(ValueError) as cm:
            self.compare()
        self.assertEqual(cm.exception.code, 'BUDGET_EXCEEDED')

    def test_codepoint_index_not_utf8_bytes(self):
        self.a['cases'][0]['rendered_text'] = '中文a'
        self.b['cases'][0]['rendered_text'] = '中文b'
        self.assertEqual(self.compare()['case_results'][0]['first_char_difference'], 2)

    def test_summary_counts_and_precedence(self):
        self.b['artifacts']['vocabulary_sha256'] = 'e'*64
        c = copy.deepcopy(self.b['cases'][0]); c['id'] = 'z'; self.b['cases'].append(c)
        r = self.compare()
        self.assertEqual(r['status'], 'incomparable')
        self.assertEqual(r['summary'], {'total': 2, 'match': 0, 'drift': 1, 'incomparable': 1})


if __name__ == '__main__':
    unittest.main()
