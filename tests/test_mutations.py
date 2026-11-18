"""Known-bad controls: mutate isolated in-memory modules, never source files."""
import importlib
import inspect
import sys
import types
import unittest
from unittest.mock import patch
import test_core as _core_tests
import test_io as _io_tests
import test_explain as _explain_tests


class MutationControls(unittest.TestCase):
    def assert_caught(self, module_name, old, new, test_class, method):
        original = importlib.import_module(module_name)
        source = inspect.getsource(original)
        self.assertEqual(source.count(old), 1, 'Mutation anchor must be unique')
        changed = source.replace(old, new, 1)
        self.assertNotEqual(source, changed, 'A no-op is not a caught mutation')
        mutant = types.ModuleType(module_name)
        mutant.__file__ = original.__file__
        mutant.__package__ = original.__package__
        exec(compile(changed, '<isolated-known-bad-control>', 'exec'), mutant.__dict__)
        control = unittest.TestResult()
        test_class(method).run(control)
        self.assertTrue(control.wasSuccessful(), 'Baseline control must pass before mutation')
        result = unittest.TestResult()
        with patch.dict(sys.modules, {module_name: mutant}):
            test_class(method).run(result)
        self.assertEqual(len(result.errors), 0, 'A crash is not a caught behavior regression')
        self.assertEqual(len(result.failures), 1, 'Named product assertion must catch the mutation')
        self.assertIn(method, str(result.failures[0][0]))
        self.assertIn('AssertionError', result.failures[0][1])

    def test_vocabulary_guard_is_load_bearing(self):
        self.assert_caught('chat_input_contract.core',
            "vocab_changed = baseline['artifacts']['vocabulary_sha256'] != candidate['artifacts']['vocabulary_sha256']",
            'vocab_changed = False', _core_tests.CoreTests, 'test_vocabulary_change_even_with_identical_ids')

    def test_case_union_is_load_bearing(self):
        self.assert_caught('chat_input_contract.core', 'sorted(left.keys() | right.keys())',
            'sorted(left.keys() & right.keys())', _core_tests.CoreTests, 'test_missing_case_union_not_intersection')

    def test_postprocessing_predicate_is_load_bearing(self):
        self.assert_caught('chat_input_contract.core', "if a['input_ids'] != b['input_ids']:",
            'if False:', _core_tests.CoreTests, 'test_postprocessing_attribution_real_trace')

    def test_render_predicate_is_load_bearing(self):
        self.assert_caught('chat_input_contract.core', "if a['rendered_text'] != b['rendered_text']:",
            'if False:', _core_tests.CoreTests, 'test_render_prefix_difference')

    def test_privacy_guard_is_load_bearing(self):
        self.assert_caught('chat_input_contract.core', 'if include_content:',
            'if True:', _core_tests.CoreTests, 'test_equal_redacted_and_immutable')

    def test_alignment_budget_cannot_silently_expand(self):
        self.assert_caught('chat_input_contract.explain', 'ALIGNMENT_CELLS = 65_536',
            'ALIGNMENT_CELLS = 66_000', _explain_tests.ExplanationTests,
            'test_middle_product_boundary_both_sides')

    def test_window_omission_remains_visible(self):
        self.assert_caught('chat_input_contract.explain', "'omitted_windows': len(operations)-len(selected)",
            "'omitted_windows': 0", _explain_tests.ExplanationTests,
            'test_three_windows_keep_tail_and_report_omission')

    def test_explanation_content_opt_in_guard(self):
        self.assert_caught('chat_input_contract.explain', 'if include_content:',
            'if True:', _explain_tests.ExplanationTests, 'test_sensitive_preview_is_opt_in_and_bounded')

    def test_duplicate_json_guard_is_load_bearing(self):
        self.assert_caught('chat_input_contract.io', 'if key in result:', 'if False:',
            _io_tests.IOTests, 'test_duplicates_nan_and_bad_unicode_rejected')
