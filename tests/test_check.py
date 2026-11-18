import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_capture import fixture
from chat_input_contract.capture import capture_manifest
from chat_input_contract.io import write_json


class CheckTests(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module('chat_input_contract.check')
        except ModuleNotFoundError:
            self.fail('Live check workflow not implemented')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.manifest = fixture(self.root)
        self.path = self.root/'manifest.json'; self.base = self.root/'baseline.json'
        write_json(self.base, capture_manifest(self.path))

    def save(self):
        self.path.write_text(json.dumps(self.manifest), encoding='utf-8')

    def cli(self, *args):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'),
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        return subprocess.run([sys.executable, '-m', 'chat_input_contract', *map(str, args)],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=90)

    def test_same_bad_repaired_real_calls(self):
        self.assertEqual(self.module.check_manifest(self.path, self.base)['status'], 'match')
        self.manifest['options'].update(route='render_then_encode', add_special_tokens=True); self.save()
        r = self.module.check_manifest(self.path, self.base)
        self.assertEqual(r['status'], 'drift')
        self.assertEqual(r['case_results'][0]['analysis']['earliest_stage'], 'postprocessing')
        self.assertEqual(r['case_results'][0]['analysis']['token_change']['total_windows'], 2)
        self.manifest['options']['add_special_tokens'] = False; self.save()
        self.assertEqual(self.module.check_manifest(self.path, self.base)['status'], 'match')

    def test_no_outputs_no_mutation(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        run = self.cli('check', self.path, '--baseline', self.base)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_output_alias_preflight_before_capture(self):
        from chat_input_contract.cli import main
        before = self.base.read_bytes()
        with patch('chat_input_contract.capture.capture_prepared', side_effect=AssertionError('must not capture')):
            with contextlib.redirect_stderr(io.StringIO()):
                rc = main(['check', str(self.path), '--baseline', str(self.base), '--json', str(self.base), '--force'])
        self.assertEqual(rc, 2)
        self.assertEqual(before, self.base.read_bytes())

    def test_invalid_baseline_precedes_capture(self):
        self.base.write_text('{}')
        with patch('chat_input_contract.capture.capture_prepared', side_effect=AssertionError('must not capture')):
            with self.assertRaises(ValueError): self.module.check_manifest(self.path, self.base)

    def test_cli_rich_reports_terminal_never_contains_prompt_or_tokens(self):
        self.manifest['cases'][0]['messages'][0]['content'] = 'secret-synthetic-content'
        self.save(); write_json(self.base, capture_manifest(self.path), force=True)
        self.manifest['options'].update(route='render_then_encode', add_special_tokens=True); self.save()
        out = self.root/'report.json'
        run = self.cli('check', self.path, '--baseline', self.base, '--json', out, '--include-content')
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertIn('case[1]', run.stdout)
        self.assertIn('postprocessing', run.stdout)
        self.assertNotIn('secret-synthetic-content', run.stdout+run.stderr)
        self.assertNotIn('<bos>', run.stdout+run.stderr)
        r = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(r['schema_version'], 2)
        self.assertTrue(r['content_included'])

    def test_intent_difference_is_exit_two(self):
        self.manifest['options']['add_generation_prompt'] = False; self.save()
        self.assertEqual(self.cli('check', self.path, '--baseline', self.base).returncode, 2)

    def test_existing_report_is_not_silently_replaced(self):
        out = self.root/'report.json'; out.write_bytes(b'important')
        run = self.cli('check', self.path, '--baseline', self.base, '--json', out)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(out.read_bytes(), b'important')

    def test_compare_retains_v1_and_opt_in_explanations(self):
        out = self.root/'legacy.json'
        run = self.cli('compare', self.base, self.base, '--json', out)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(out.read_text())['schema_version'], 1)
        run = self.cli('compare', self.base, self.base, '--json', out, '--force', '--explain')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(out.read_text())['schema_version'], 2)

    def test_hardlinked_baseline_cannot_be_overwritten(self):
        alias = self.root/'alias.json'
        os.link(self.base, alias)
        before = self.base.read_bytes()
        run = self.cli('check', self.path, '--baseline', self.base, '--json', alias, '--force')
        self.assertEqual(run.returncode, 2)
        self.assertIn('OUTPUT_CONFLICT', run.stderr)
        self.assertEqual(self.base.read_bytes(), before)
        self.assertEqual(alias.read_bytes(), before)

    def test_version_matches_distribution(self):
        import chat_input_contract
        run = self.cli('--version')
        self.assertEqual(run.returncode, 0)
        self.assertIn(chat_input_contract.__version__, run.stdout)


if __name__ == '__main__': unittest.main()
