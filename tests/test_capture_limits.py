import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from chat_input_contract.capture import _run_worker
from chat_input_contract.core import validate_snapshot
from chat_input_contract.errors import ContractError
from tests.test_core import snapshot


MIB = 1024 * 1024


def process_is_running(pid):
    if os.name == 'nt':
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL,
                                         ctypes.wintypes.DWORD]
        kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = ctypes.wintypes.DWORD
        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 258  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class CaptureLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def worker(self, source):
        path = self.root / 'worker.py'
        path.write_text(source, encoding='utf-8')
        return path

    def assert_capture_error(self, code, worker, payload=b'{}'):
        with self.assertRaises(ContractError) as caught:
            _run_worker(worker, payload)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_worker_stdout_is_capped_while_streaming(self):
        worker = self.worker("import sys; sys.stdout.write('x' * (70 * 1024 * 1024))")
        error = self.assert_capture_error('CAPTURE_OUTPUT_BUDGET', worker)
        self.assertNotIn('x' * 1024, error.message)

    def test_worker_stderr_is_capped_while_streaming(self):
        worker = self.worker("import sys; sys.stderr.write('private-stderr' * (7 * 1024 * 1024))")
        error = self.assert_capture_error('CAPTURE_OUTPUT_BUDGET', worker)
        self.assertNotIn('private-stderr', error.message)

    def test_stdout_and_stderr_share_one_output_budget(self):
        worker = self.worker(
            "import sys; sys.stdout.write('a' * (600 * 1024)); sys.stdout.flush(); "
            "sys.stderr.write('b' * (600 * 1024))")
        with patch('chat_input_contract.capture.CAPTURE_OUTPUT_BUDGET_BYTES', MIB):
            self.assert_capture_error('CAPTURE_OUTPUT_BUDGET', worker)

    def test_output_overflow_kills_and_reaps_worker(self):
        pid_file = self.root / 'worker.pid'
        worker = self.worker(
            "import os, pathlib, sys; "
            f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
            "sys.stdout.write('x' * (70 * 1024 * 1024))")
        self.assert_capture_error('CAPTURE_OUTPUT_BUDGET', worker)
        self.assertFalse(process_is_running(int(pid_file.read_text(encoding='ascii'))))

    def test_timeout_kills_and_reaps_worker(self):
        pid_file = self.root / 'worker.pid'
        worker = self.worker(
            "import os, pathlib, time; "
            f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
            "time.sleep(60)")
        with patch('chat_input_contract.capture.CAPTURE_TIMEOUT_SECONDS', 2):
            self.assert_capture_error('CAPTURE_TIMEOUT', worker)
        self.assertFalse(process_is_running(int(pid_file.read_text(encoding='ascii'))))

    def test_inherited_pipe_descendant_cannot_block_deadline(self):
        pid_file = self.root / 'descendant.pid'
        worker = self.worker(
            "import pathlib, subprocess, sys; "
            f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
            "stdout=sys.stdout, stderr=sys.stderr); "
            f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))")
        started = time.monotonic()
        with patch('chat_input_contract.capture.CAPTURE_TIMEOUT_SECONDS', 0.3):
            self.assert_capture_error('CAPTURE_TIMEOUT', worker)
        self.assertLess(time.monotonic() - started, 3)
        pid = int(pid_file.read_text(encoding='ascii'))
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                               capture_output=True, timeout=5)
            else:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    def test_worker_failure_never_exports_raw_stderr(self):
        worker = self.worker(
            "import sys; sys.stderr.write('private-stderr-example'); sys.exit(3)")
        error = self.assert_capture_error('CAPTURE_FAILED', worker)
        self.assertNotIn('private-stderr-example', str(error))

    def test_successful_worker_output_is_returned_with_stderr_discarded(self):
        worker = self.worker(
            "import sys; sys.stderr.write('diagnostic'); "
            "sys.stdout.write('{\"result\": 1}')")
        self.assertEqual(_run_worker(worker, b'{}'), b'{"result": 1}')

    @unittest.skipIf(os.name != 'posix', 'RLIMIT_AS is POSIX-only')
    def test_worker_address_space_is_limited_where_supported(self):
        worker = self.worker("bytearray(128 * 1024 * 1024)")
        with patch('chat_input_contract.capture.CAPTURE_MEMORY_LIMIT_BYTES', 64 * MIB):
            self.assert_capture_error('CAPTURE_FAILED', worker)

    def test_structurally_valid_new_schema_is_unsupported(self):
        value = snapshot()
        value['schema_version'] = 2
        with self.assertRaises(ContractError) as caught:
            validate_snapshot(value)
        self.assertEqual(caught.exception.code, 'UNSUPPORTED_VERSION')

    def test_structurally_valid_new_producer_is_unsupported(self):
        value = snapshot()
        value['producer'] = 'chat-input-contract/99.0.0'
        with self.assertRaises(ContractError) as caught:
            validate_snapshot(value)
        self.assertEqual(caught.exception.code, 'UNSUPPORTED_VERSION')

    def test_malformed_new_schema_remains_invalid_snapshot(self):
        value = snapshot()
        value['schema_version'] = 2
        value['cases'][0]['tokens'] = 'not-a-list'
        with self.assertRaises(ContractError) as caught:
            validate_snapshot(value)
        self.assertEqual(caught.exception.code, 'INVALID_SNAPSHOT')

    def test_malformed_new_producer_remains_invalid_snapshot(self):
        value = snapshot()
        value['producer'] = 'chat-input-contract/99.0.0'
        value['artifacts']['tokenizer_sha256'] = 'not-a-hash'
        with self.assertRaises(ContractError) as caught:
            validate_snapshot(value)
        self.assertEqual(caught.exception.code, 'INVALID_SNAPSHOT')

    def test_v1_v2_producers_remain_compatible(self):
        for producer in ('chat-input-contract/0.1.0', 'chat-input-contract/0.2.0'):
            with self.subTest(producer=producer):
                value = json.loads(json.dumps(snapshot()))
                value['producer'] = producer
                validate_snapshot(value)


if __name__ == '__main__':
    unittest.main()
