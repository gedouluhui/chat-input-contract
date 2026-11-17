import importlib
import unittest
from test_core import snapshot
from chat_input_contract.core import compare_snapshots


class ReportTests(unittest.TestCase):
    def setUp(self):
        try:
            self.render = importlib.import_module('chat_input_contract.report').render_html
        except ModuleNotFoundError:
            self.fail('Missing offline report implementation')

    def test_match_no_content_or_external_resources(self):
        s = snapshot(); r = compare_snapshots(s, s)
        html = self.render(r)
        self.assertIn('Input contract', html)
        self.assertIn('Match', html)
        self.assertIn('Content hidden', html)
        self.assertNotIn('&lt;bos&gt;', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('https://', html)
        self.assertIn("default-src 'none'", html)
        self.assertIn('width=device-width', html)
        self.assertIn('@media', html)

    def test_hostile_strings_escaped(self):
        a, b = snapshot(), snapshot()
        attack = '</script><img src=x onerror=alert(1)>'
        a['cases'][0]['id'] = b['cases'][0]['id'] = attack
        a['cases'][0]['rendered_text'] = b['cases'][0]['rendered_text'] = attack
        html = self.render(compare_snapshots(a, b, include_content=True))
        self.assertNotIn(attack, html)
        self.assertIn('&lt;img', html)
        self.assertIn('Content included', html)

    def test_drift_and_positions(self):
        a, b = snapshot(), snapshot(); b['cases'][0]['rendered_text'] += '!'
        html = self.render(compare_snapshots(a, b))
        self.assertIn('Drift', html)
        self.assertIn('RENDER_CHANGED', html)
        self.assertIn('zero-based', html)

    def test_postprocessing_only_does_not_blame_tokenizer_stage(self):
        a, b = snapshot(), snapshot()
        b['options'].update(route='render_then_encode', add_special_tokens=True)
        c = b['cases'][0]
        c['input_ids'] = list(c['postprocessed_ids'])
        c['tokens'] = ['<bos>', '<bos>', 'hello', '<eos>', '<eos>']
        html = self.render(compare_snapshots(a, b))
        self.assertIn('<strong>Tokenizer</strong><span>No reported difference</span>', html)
        self.assertIn('<strong>Postprocess</strong><span>Evidence to review</span>', html)

    def test_incomparable_explicit(self):
        a, b = snapshot(), snapshot(); b['options']['add_generation_prompt'] = False
        html = self.render(compare_snapshots(a, b))
        self.assertIn('Incomparable', html)
        self.assertIn('INTENT_CHANGED', html)


if __name__ == '__main__':
    unittest.main()
