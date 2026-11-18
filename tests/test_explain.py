import copy
import importlib
import json
import random
import unittest
from test_core import snapshot


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module('chat_input_contract.explain')
        except ModuleNotFoundError:
            self.fail('Bounded explanation module is not implemented')

    def test_two_ended_insertions_are_distinct(self):
        r = self.module.sequence_changes([1, 2, 3], [0, 1, 2, 3, 4])
        self.assertEqual(r['alignment'], 'bounded')
        self.assertEqual(r['total_windows'], 2)
        a, b = r['windows']
        self.assertEqual((a['baseline_start'], a['baseline_end'], a['candidate_start'], a['candidate_end']), (0, 0, 0, 1))
        self.assertEqual((b['baseline_start'], b['baseline_end'], b['candidate_start'], b['candidate_end']), (3, 3, 4, 5))

    def test_equal_and_empty(self):
        for value in ([], [1, 1], ''):
            r = self.module.sequence_changes(value, value)
            self.assertEqual(r, {'alignment': 'equal', 'total_windows': 0, 'omitted_windows': 0, 'windows': []})
        self.assertEqual(self.module.sequence_changes([], [7])['windows'][0]['added_count'], 1)

    def test_large_middle_uses_explicit_linear_fallback(self):
        r = self.module.sequence_changes([1]*1000, [2]*1000)
        self.assertEqual(r['alignment'], 'enclosing')
        self.assertEqual(r['total_windows'], 1)
        self.assertEqual(r['windows'][0]['removed_count'], 1000)

    def test_middle_product_boundary_both_sides(self):
        self.assertEqual(self.module.sequence_changes([1]*256, [2]*256)['alignment'], 'bounded')
        self.assertEqual(self.module.sequence_changes([1]*257, [2]*256)['alignment'], 'enclosing')

    def test_three_windows_keep_tail_and_report_omission(self):
        a = list(range(20)); b = a.copy()
        for i in (1, 5, 9, 13, 17): b[i] += 100
        r = self.module.sequence_changes(a, b)
        self.assertEqual(r['total_windows'], 5)
        self.assertEqual(r['omitted_windows'], 2)
        self.assertEqual(len(r['windows']), 3)
        self.assertEqual(r['windows'][-1]['baseline_start'], 17)

    def test_small_random_alignment_reconstructs_candidate(self):
        rng = random.Random(917)
        for i in range(100):
            a = [rng.randrange(3) for _ in range(rng.randrange(10))]
            b = [rng.randrange(3) for _ in range(rng.randrange(10))]
            r = self.module.sequence_changes(a, b)
            if r['omitted_windows']: continue
            reconstructed, offset = [], 0
            for w in r['windows']:
                self.assertEqual(a[offset:w['baseline_start']], b[len(reconstructed):w['candidate_start']])
                reconstructed += a[offset:w['baseline_start']] + b[w['candidate_start']:w['candidate_end']]
                offset = w['baseline_end']
            reconstructed += a[offset:]
            self.assertEqual(reconstructed, b, i)

    def test_sensitive_preview_is_opt_in_and_bounded(self):
        a = [987654321]*600; b = [123456789]*600
        r = self.module.sequence_changes(a, b)
        self.assertNotIn('987654321', json.dumps(r))
        self.assertNotIn('123456789', json.dumps(r))
        r = self.module.sequence_changes(a, b, include_content=True)
        p = r['windows'][0]['baseline_preview']
        self.assertEqual(len(p['changed']), 32)
        self.assertEqual(p['omitted_items'], 568)
        r['windows'][0]['baseline_preview']['changed'][0] = 3
        self.assertEqual(a[0], 987654321)

    def test_character_preview_uses_codepoints(self):
        r = self.module.sequence_changes('中文abc', '中文xyz', kind='characters', include_content=True)
        self.assertEqual(r['windows'][0]['baseline_start'], 2)
        self.assertEqual(r['windows'][0]['baseline_preview']['changed'], 'abc')

    def test_report_v2_not_legacy_full_content(self):
        a, b = snapshot(), snapshot(); b['cases'][0]['rendered_text'] += '!'
        original = copy.deepcopy(b)
        r = self.module.explain_snapshots(a, b, include_content=True)
        self.assertEqual(r['schema_version'], 2)
        self.assertTrue(r['content_included'])
        row = r['case_results'][0]
        self.assertNotIn('content', row)
        self.assertEqual(row['analysis']['earliest_stage'], 'rendering')
        self.assertTrue(row['analysis']['character_change']['windows'])
        self.assertEqual(b, original)

    def test_changed_render_is_not_proven_tokenizer_failure(self):
        a, b = snapshot(), snapshot(); c = b['cases'][0]
        c['rendered_text'] += ' new'
        for key in ('input_ids', 'direct_ids', 'unprocessed_ids'): c[key].append(9)
        c['tokens'].append('new')
        row = self.module.explain_snapshots(a, b)['case_results'][0]
        self.assertEqual(row['analysis']['earliest_stage'], 'rendering')
        self.assertIn('downstream', ' '.join(row['analysis']['notes']))

    def test_route_inconsistency_precedes_postprocessing_blame(self):
        a, b = snapshot(), snapshot()
        b['cases'][0]['direct_ids'] = [7]
        b['cases'][0]['input_ids'] = [7]
        b['cases'][0]['tokens'] = ['different']
        row = self.module.explain_snapshots(a, b)['case_results'][0]
        self.assertEqual(row['analysis']['earliest_stage'], 'consistency')
        self.assertNotIn('POSTPROCESSING_CHANGED', row['stages'])

    def test_incomparable_does_not_align_unrelated_inputs(self):
        a, b = snapshot(), snapshot(); b['cases'][0]['messages_sha256'] = 'e'*64
        row = self.module.explain_snapshots(a, b, include_content=True)['case_results'][0]
        self.assertEqual(row['status'], 'incomparable')
        self.assertEqual(row['analysis']['earliest_stage'], 'inputs')
        self.assertIsNone(row['analysis']['character_change'])
        self.assertIsNone(row['analysis']['token_change'])

    def test_terminal_summary_is_indexed_bounded_and_content_free(self):
        from chat_input_contract.cli import terminal_summary
        a, b = snapshot(), snapshot()
        original = b['cases'][0]
        a['cases'] = []; b['cases'] = []
        for i in range(14):
            left = copy.deepcopy(original); left['id'] = f'private-name-{i:02d}\\n\\x1b'
            right = copy.deepcopy(left); right['rendered_text'] += ' secret-prompt-marker'
            a['cases'].append(left); b['cases'].append(right)
        text = terminal_summary(self.module.explain_snapshots(a, b, include_content=True))
        self.assertEqual(text.count('case['), 10)
        self.assertIn('4 further nonmatching cases omitted', text)
        self.assertNotIn('private-name', text)
        self.assertNotIn('secret-prompt-marker', text)

    def test_vocab_change_cannot_hide_behind_equal_integer_ids(self):
        a, b = snapshot(), snapshot(); b['artifacts']['vocabulary_sha256'] = 'e'*64
        row = self.module.explain_snapshots(a, b)['case_results'][0]
        self.assertEqual(row['analysis']['earliest_stage'], 'vocabulary')
        self.assertEqual(row['analysis']['token_change']['alignment'], 'equal')


if __name__ == '__main__': unittest.main()
