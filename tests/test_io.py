import importlib
from pathlib import Path
import tempfile
import unittest


class IOTests(unittest.TestCase):
    def setUp(self):
        try:
            self.io = importlib.import_module('chat_input_contract.io')
        except ModuleNotFoundError:
            self.fail('Missing bounded JSON and output implementation')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_roundtrip_utf8_lf(self):
        p = self.root / 'one.json'
        self.io.write_json(p, {'value': '中文'})
        self.assertEqual(self.io.load_json(p), {'value': '中文'})
        self.assertNotIn(b'\r\n', p.read_bytes())

    def test_duplicates_nan_and_bad_unicode_rejected(self):
        p = self.root / 'bad.json'
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff'):
            with self.subTest(raw=raw):
                p.write_bytes(raw)
                with self.assertRaises(ValueError):
                    self.io.load_json(p)

    def test_numeric_exponent_overflow_rejected(self):
        for raw in (b'{"x":1e999}', b'{"x":-1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.io.decode_json(raw)
        self.assertEqual(self.io.decode_json(b'{"x":1e308}')['x'], 1e308)

    def test_encoded_json_budget_covers_escaping(self):
        with self.assertRaises(ValueError) as cm:
            self.io.json_bytes({'x': '\0' * (64 * 1024 * 1024 // 6 + 1)})
        self.assertEqual(cm.exception.code, 'BUDGET_EXCEEDED')

    def test_byte_budget_exact_boundary_has_both_controls(self):
        from unittest.mock import patch
        value = {'x': '\0\0'}
        raw = self.io.json_bytes(value)
        size = len(raw)
        self.assertEqual(self.io.MAX_JSON_BYTES, 64 * 1024 * 1024)
        with patch.object(self.io, 'MAX_JSON_BYTES', size):
            self.assertEqual(self.io.json_bytes(value), raw)
        with patch.object(self.io, 'MAX_JSON_BYTES', size - 1), self.assertRaises(ValueError):
            self.io.json_bytes(value)
        p = self.root / 'boundary.json'; p.write_bytes(raw)
        self.assertEqual(self.io.load_json(p, max_bytes=size), value)
        with self.assertRaises(ValueError):
            self.io.load_json(p, max_bytes=size - 1)

    def test_bounded_read(self):
        p = self.root / 'big.json'; p.write_text('{"x":123}')
        with self.assertRaises(ValueError) as cm:
            self.io.load_json(p, max_bytes=2)
        self.assertEqual(cm.exception.code, 'BUDGET_EXCEEDED')

    def test_no_clobber_and_force(self):
        p = self.root / 'x.json'; self.io.write_json(p, {'x': 1})
        with self.assertRaises(ValueError):
            self.io.write_json(p, {'x': 2})
        self.assertEqual(self.io.load_json(p), {'x': 1})
        self.io.write_json(p, {'x': 2}, force=True)
        self.assertEqual(self.io.load_json(p), {'x': 2})

    def test_protected_input_even_with_force(self):
        p = self.root / 'x.json'; p.write_bytes(b'original')
        with self.assertRaises(ValueError):
            self.io.write_json(p, {}, force=True, protected=[p])
        self.assertEqual(p.read_bytes(), b'original')

    def test_serialization_failure_leaves_no_output(self):
        p = self.root / 'x.json'
        with self.assertRaises(ValueError):
            self.io.write_json(p, {'x': float('nan')})
        self.assertFalse(p.exists())


if __name__ == '__main__':
    unittest.main()
