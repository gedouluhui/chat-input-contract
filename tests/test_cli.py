import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_capture import fixture
from test_core import snapshot

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'),
                        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONIOENCODING='utf-8')

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'chat_input_contract', *map(str, args)],
                              cwd=self.root, env=self.env, capture_output=True, text=True,
                              encoding='utf-8', timeout=90)

    def save_pair(self):
        a, b = snapshot(), snapshot()
        pa, pb = self.root/'a.json', self.root/'b.json'
        pa.write_text(json.dumps(a), encoding='utf-8'); pb.write_text(json.dumps(b), encoding='utf-8')
        return a, b, pa, pb

    def test_help(self):
        p = self.run_cli('--help')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('capture', p.stdout)

    def test_compare_three_exit_codes_and_redaction(self):
        a, b, pa, pb = self.save_pair(); out = self.root/'report.json'
        p = self.run_cli('compare', pa, pb, '--json', out)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn('rendered_text', out.read_text(encoding='utf-8'))
        b['cases'][0]['rendered_text'] += '!'; pb.write_text(json.dumps(b))
        p = self.run_cli('compare', pa, pb, '--json', out, '--force')
        self.assertEqual(p.returncode, 1, p.stderr)
        b['options']['add_generation_prompt'] = False; pb.write_text(json.dumps(b))
        p = self.run_cli('compare', pa, pb, '--json', out, '--force')
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(json.loads(out.read_text())['status'], 'incomparable')

    def test_output_collision_preserves_inputs(self):
        a, b, pa, pb = self.save_pair(); before = pa.read_bytes()
        p = self.run_cli('compare', pa, pb, '--json', pa, '--force')
        self.assertEqual(p.returncode, 2)
        self.assertIn('OUTPUT_CONFLICT', p.stderr)
        self.assertEqual(pa.read_bytes(), before)
        out = self.root/'new.json'
        p = self.run_cli('compare', pa, pb, '--json', out, '--html', out)
        self.assertEqual(p.returncode, 2)
        self.assertFalse(out.exists())

    def test_invalid_input_no_output_or_traceback(self):
        pa, pb = self.root/'a.json', self.root/'b.json'
        pa.write_text('{bad'); pb.write_text('{}'); out = self.root/'out.json'
        p = self.run_cli('compare', pa, pb, '--json', out)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn('Traceback', p.stderr)
        self.assertFalse(out.exists())

    def test_actual_capture_and_no_clobber(self):
        fixture(self.root); out = self.root/'capture.json'
        p = self.run_cli('capture', self.root/'manifest.json', '--out', out)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(out.read_text())['cases'][0]['input_ids'], [1,3,5,6,2,4,5])
        before = out.read_bytes()
        p = self.run_cli('capture', self.root/'manifest.json', '--out', out)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(before, out.read_bytes())
        p = self.run_cli('capture', self.root/'manifest.json', '--out', self.root/'chat.jinja', '--force')
        self.assertEqual(p.returncode, 2)
        self.assertIn('OUTPUT_CONFLICT', p.stderr)

    def test_real_demo_and_reuse_guard(self):
        out = self.root/'demo'
        p = self.run_cli('demo', '--out', out)
        self.assertEqual(p.returncode, 0, p.stderr)
        safe = json.loads((out/'safe-report.json').read_text())
        bad = json.loads((out/'broken-report.json').read_text())
        self.assertEqual(safe['status'], 'match')
        self.assertEqual(bad['status'], 'drift')
        self.assertIn('POSTPROCESSING_CHANGED', bad['case_results'][0]['stages'])
        self.assertTrue((out/'broken-report.html').exists())
        p = self.run_cli('demo', '--out', out)
        self.assertEqual(p.returncode, 2)


if __name__ == '__main__':
    unittest.main()
