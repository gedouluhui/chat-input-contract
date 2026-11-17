from pathlib import Path
import tomllib
import unittest


class PackagingTests(unittest.TestCase):
    def test_capture_declares_template_runtime(self):
        metadata = tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text(encoding='utf-8'))
        capture = metadata['project']['optional-dependencies']['capture']
        self.assertIn('jinja2==3.1.6', capture)
        self.assertIn('transformers==5.8.0', capture)
        self.assertIn('tokenizers==0.22.2', capture)
        self.assertEqual(metadata['project']['dependencies'], [])


if __name__ == '__main__':
    unittest.main()
