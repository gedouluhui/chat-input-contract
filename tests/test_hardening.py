import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import chat_input_contract.capture as capture
from chat_input_contract.cli import main
from test_capture import fixture


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = fixture(self.root)
        self.path = self.root / 'manifest.json'

    def test_cli_uses_one_frozen_manifest_and_actual_input_fingerprint(self):
        token_bytes = (self.root/'tokenizer.json').read_bytes()
        original_hash = hashlib.sha256(token_bytes).hexdigest()
        other = json.loads(token_bytes); other['model']['vocab']['extra'] = 9
        (self.root/'other.json').write_text(json.dumps(other), encoding='utf-8')
        original = capture.manifest_inputs
        calls = []
        def replace_after_first_read(path):
            result = original(path); calls.append(1)
            if len(calls) == 1:
                self.manifest['tokenizer'] = 'other.json'
                self.path.write_text(json.dumps(self.manifest), encoding='utf-8')
            return result
        with patch.object(capture, 'manifest_inputs', replace_after_first_read), contextlib.redirect_stdout(io.StringIO()):
            rc = main(['capture', str(self.path), '--out', str(self.root/'out.json')])
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1, 'Preflight and capture must use one manifest read')
        result = json.loads((self.root/'out.json').read_text(encoding='utf-8'))
        self.assertEqual(result['artifacts']['tokenizer_sha256'], original_hash)
        self.assertEqual((self.root/'tokenizer.json').read_bytes(), token_bytes)

    def test_native_panic_has_safe_cli_boundary(self):
        p = self.root/'tokenizer.json'
        bad = json.loads(p.read_text(encoding='utf-8'))
        bad['post_processor']['special_tokens'] = {}
        p.write_text(json.dumps(bad), encoding='utf-8')
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'),
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        out = self.root/'out.json'
        run = subprocess.run([sys.executable, '-m', 'chat_input_contract', 'capture',
                              str(self.path), '--out', str(out)],
                             env=env, capture_output=True, text=True, timeout=90)
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertNotIn('Traceback', run.stderr)
        self.assertNotIn('panicked', run.stderr)
        self.assertNotIn(str(self.root), run.stderr)
        self.assertFalse(out.exists())

    def test_unstable_observed_routes_refuse_capture(self):
        template = b"{{ ['hello', 'world']|random }}"
        (self.root/'chat.jinja').write_bytes(template)
        with patch('random.choice', side_effect=['hello', 'world']):
            with self.assertRaises(ValueError) as caught:
                if hasattr(capture, 'execute_capture'):
                    capture.execute_capture(self.manifest, (self.root/'tokenizer.json').read_bytes(), template)
                else:
                    capture.capture_manifest(self.path)
        self.assertEqual(caught.exception.code, 'CAPTURE_INCONSISTENT')

    def test_prepared_bytes_remain_bound_when_files_change(self):
        prepared = capture.prepare_capture(self.path)
        original_hash = hashlib.sha256((self.root/'tokenizer.json').read_bytes()).hexdigest()
        (self.root/'tokenizer.json').write_bytes(b'changed after preparation')
        (self.root/'chat.jinja').write_bytes(b'also changed')
        self.path.write_bytes(b'not JSON any more')
        result = capture.capture_prepared(prepared)
        self.assertEqual(result['artifacts']['tokenizer_sha256'], original_hash)
        self.assertEqual(result['cases'][0]['input_ids'], [1,3,5,6,2,4,5])

    def test_real_worker_timeout_returns_fixed_diagnostic(self):
        prepared = capture.prepare_capture(self.path)
        self.assertEqual(capture.CAPTURE_TIMEOUT_SECONDS, 60)
        with patch.object(capture, 'CAPTURE_TIMEOUT_SECONDS', 0.000001):
            with self.assertRaises(ValueError) as caught:
                capture.capture_prepared(prepared)
        self.assertEqual(caught.exception.code, 'CAPTURE_TIMEOUT')
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_argument_errors_do_not_echo_secret_values(self):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
        run = subprocess.run([sys.executable, '-m', 'chat_input_contract', 'demo', '--out', 'unused', '--private-secret-example'],
                             env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertNotIn('private-secret-example', run.stdout + run.stderr)
        self.assertNotIn('Traceback', run.stderr)


if __name__ == '__main__':
    unittest.main()
