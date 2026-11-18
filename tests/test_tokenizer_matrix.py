"""Offline integration matrix with self-authored, locally built tokenizers."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import tempfile
import unittest

from tokenizers import Tokenizer, decoders, models, normalizers, pre_tokenizers, processors, trainers

from chat_input_contract.capture import capture_manifest
from chat_input_contract.check import check_manifest
from chat_input_contract.core import compare_snapshots
from chat_input_contract.explain import explain_snapshots


TEXT_TEMPLATE = '{{ messages[0].content }}'
CHAT_TEMPLATE = (
    '{{ bos_token }}{% for message in messages %}'
    '{{ message.role }}: {{ message.content }}{{ eos_token }}\n'
    '{% endfor %}{% if add_generation_prompt %}assistant: {% endif %}'
)
BYTE_SPECIALS = {'unk_token': '<unk>', 'bos_token': '<bos>', 'eos_token': '<eos>'}
WORDPIECE_SPECIALS = {'unk_token': '[UNK]', 'cls_token': '[CLS]', 'sep_token': '[SEP]'}
WORDPIECE_VOCAB = {
    '[UNK]': 0, '[CLS]': 1, '[SEP]': 2,
    'Hello': 3, 'WORLD': 4, 'hello': 5, 'world': 6, '##s': 7, '!': 8,
}


def bytelevel_tokenizer():
    backend = Tokenizer(models.BPE(unk_token='<unk>'))
    backend.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    backend.decoder = decoders.ByteLevel()
    # Deliberately ASCII-only training: unseen Unicode must use the byte alphabet,
    # not memorized test sentences. These three strings are authored here.
    backend.train_from_iterator(
        [
            'user: A small lantern glows.\nassistant: Quiet light.\n',
            'system: Keep the reply short.\nuser: Write one line.\n',
            'user: A small lantern glows.\nassistant: Warm light.\n',
        ],
        trainer=trainers.BpeTrainer(
            vocab_size=320, min_frequency=2, show_progress=False,
            initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
            special_tokens=['<unk>', '<bos>', '<eos>'],
        ),
    )
    backend.post_processor = processors.TemplateProcessing(
        single='<bos> $A <eos>', special_tokens=[('<bos>', 1), ('<eos>', 2)],
    )
    return backend


def wordpiece_tokenizer(*, lowercase):
    backend = Tokenizer(models.WordPiece(dict(WORDPIECE_VOCAB), unk_token='[UNK]'))
    backend.normalizer = normalizers.BertNormalizer(
        clean_text=True, handle_chinese_chars=True, strip_accents=False, lowercase=lowercase,
    )
    backend.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    backend.decoder = decoders.WordPiece(prefix='##')
    backend.add_special_tokens(['[UNK]', '[CLS]', '[SEP]'])
    backend.post_processor = processors.TemplateProcessing(
        single='[CLS] $A [SEP]', special_tokens=[('[CLS]', 1), ('[SEP]', 2)],
    )
    return backend


def text_case(content, ident='sample'):
    return {'id': ident, 'messages': [{'role': 'user', 'content': content}]}


def canonical_sha256(value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                     separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


class TokenizerMatrixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cic-tokenizer-matrix-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def fixture(self, backend, specials, cases, *, template=TEXT_TEMPLATE,
                add_generation_prompt=False):
        backend.save(str(self.root / 'tokenizer.json'))
        # Preserve literal LF/CRLF independently of Windows text-mode translation.
        (self.root / 'chat.jinja').write_bytes(template.encode('utf-8'))
        self.manifest = {
            'schema_version': 1, 'tokenizer': 'tokenizer.json', 'template': 'chat.jinja',
            'special_tokens': dict(specials),
            'options': {'route': 'direct', 'add_special_tokens': False,
                        'add_generation_prompt': add_generation_prompt,
                        'continue_final_message': False},
            'cases': cases,
        }
        return self.save_manifest()

    def save_manifest(self, name='manifest.json'):
        path = self.root / name
        path.write_bytes(json.dumps(self.manifest, ensure_ascii=False).encode('utf-8'))
        return path

    def test_bytelevel_exact_unseen_unicode_and_whitespace_roundtrip(self):
        backend = bytelevel_tokenizer()
        self.assertTrue(set(pre_tokenizers.ByteLevel.alphabet()) <= set(backend.get_vocab()))
        expected = ' \tCafe\u0301 / Caf\u00e9  \u4e2d\u6587 \u03a9 \U00010437\r\nline\t two\u00a0end\u200b\n\n '
        path = self.fixture(backend, BYTE_SPECIALS, [text_case(expected)])

        row = capture_manifest(path)['cases'][0]

        self.assertEqual(row['rendered_text'], expected)
        self.assertNotIn(0, row['input_ids'], 'Full byte coverage must prevent unknown tokens')
        # Decode the worker's actual IDs back to the independent, literal source.
        # Comparing two captures alone would miss normalization or whitespace loss.
        self.assertEqual(backend.decode(row['input_ids'], skip_special_tokens=False), expected)
        self.assertEqual(row['input_ids'], backend.encode(expected, add_special_tokens=False).ids)
        self.assertEqual(row['direct_ids'], row['unprocessed_ids'])
        self.assertEqual(row['postprocessed_ids'], [1] + row['input_ids'] + [2])

    def test_bytelevel_direct_and_safe_two_stage_agree_on_stable_chat(self):
        backend = bytelevel_tokenizer()
        cases = [{'id': 'chat', 'messages': [
            {'role': 'system', 'content': 'Keep spacing.'},
            {'role': 'user', 'content': 'Caf\u00e9\t \u4e16\u754c'},
        ]}]
        path = self.fixture(backend, BYTE_SPECIALS, cases, template=CHAT_TEMPLATE,
                            add_generation_prompt=True)
        direct = capture_manifest(path)
        self.manifest['options']['route'] = 'render_then_encode'
        safe = capture_manifest(self.save_manifest('safe.json'))
        expected = '<bos>system: Keep spacing.<eos>\nuser: Caf\u00e9\t \u4e16\u754c<eos>\nassistant: '
        expected_ids = backend.encode(expected, add_special_tokens=False).ids

        for snapshot in (direct, safe):
            row = snapshot['cases'][0]
            self.assertEqual(row['rendered_text'], expected)
            self.assertEqual(row['input_ids'], expected_ids)
            self.assertEqual(row['direct_ids'], expected_ids)
            self.assertEqual(row['unprocessed_ids'], expected_ids)
            self.assertEqual(backend.decode(row['input_ids'], skip_special_tokens=False), expected)
        report = compare_snapshots(direct, safe)
        self.assertEqual(report['status'], 'match')
        self.assertEqual(report['case_results'][0]['stages'], [])
        self.assertEqual(report['provenance_changes'], [
            {'field': 'options.route', 'baseline': 'direct', 'candidate': 'render_then_encode'},
        ])

    def test_bytelevel_extra_bos_eos_is_real_postprocessing_drift(self):
        backend = bytelevel_tokenizer()
        path = self.fixture(backend, BYTE_SPECIALS, [text_case('One lamp.')],
                            template=CHAT_TEMPLATE, add_generation_prompt=True)
        baseline = capture_manifest(path)
        baseline_path = self.root / 'baseline.json'
        baseline_path.write_bytes(json.dumps(baseline).encode('utf-8'))
        self.manifest['options'].update(route='render_then_encode', add_special_tokens=True)
        bad_path = self.save_manifest('extra-specials.json')
        candidate = capture_manifest(bad_path)
        before, after = baseline['cases'][0], candidate['cases'][0]
        expected = '<bos>user: One lamp.<eos>\nassistant: '
        expected_ids = backend.encode(expected, add_special_tokens=False).ids

        self.assertEqual(before['rendered_text'], expected)
        self.assertEqual(after['rendered_text'], expected)
        self.assertEqual(before['input_ids'], expected_ids)
        self.assertEqual(after['unprocessed_ids'], expected_ids)
        self.assertEqual(after['direct_ids'], expected_ids)
        # The fixture's TemplateProcessing inserts BOS/EOS even though the
        # template already contains them. This is a real encode, not edited IDs.
        self.assertEqual(before['postprocessed_ids'], [1] + expected_ids + [2])
        self.assertEqual(after['postprocessed_ids'], [1] + expected_ids + [2])
        self.assertEqual(after['input_ids'], [1] + expected_ids + [2])
        self.assertEqual(backend.decode(after['input_ids'], skip_special_tokens=False),
                         '<bos>' + expected + '<eos>')
        self.assertEqual(baseline['artifacts'], candidate['artifacts'])

        report = check_manifest(bad_path, baseline_path, include_content=True)
        row = report['case_results'][0]
        self.assertEqual(report['status'], 'drift')
        self.assertIn('POSTPROCESSING_CHANGED', row['stages'])
        self.assertNotIn('RENDER_CHANGED', row['stages'])
        self.assertNotIn('TOKENIZATION_CHANGED', row['stages'])
        self.assertEqual(row['analysis']['earliest_stage'], 'postprocessing')
        self.assertEqual(row['analysis']['character_change']['alignment'], 'equal')
        changes = row['analysis']['token_change']
        self.assertEqual(changes['total_windows'], 2)
        self.assertEqual(changes['omitted_windows'], 0)
        self.assertEqual([w['candidate_preview']['changed'] for w in changes['windows']], [[1], [2]])
        self.assertEqual([(w['removed_count'], w['added_count']) for w in changes['windows']],
                         [(0, 1), (0, 1)])

    def test_wordpiece_case_folding_preserves_rendered_case_and_subwords(self):
        backend = wordpiece_tokenizer(lowercase=True)
        cases = [text_case('Hello WORLDs!', 'mixed'), text_case('hello worlds!', 'lower')]
        path = self.fixture(backend, WORDPIECE_SPECIALS, cases)
        direct = capture_manifest(path)
        self.manifest['options']['route'] = 'render_then_encode'
        safe = capture_manifest(self.save_manifest('safe.json'))

        for snapshot in (direct, safe):
            rows = {row['id']: row for row in snapshot['cases']}
            self.assertEqual(rows['mixed']['rendered_text'], 'Hello WORLDs!')
            self.assertEqual(rows['lower']['rendered_text'], 'hello worlds!')
            for row in rows.values():
                # Literal vocabulary: hello=5, world=6, suffix ##s=7, !=8.
                self.assertEqual(row['input_ids'], [5, 6, 7, 8])
                self.assertEqual(row['tokens'], ['hello', 'world', '##s', '!'])
                self.assertEqual(row['postprocessed_ids'], [1, 5, 6, 7, 8, 2])
        self.assertEqual(compare_snapshots(direct, safe)['status'], 'match')

    def test_wordpiece_same_render_normalizer_change_is_tokenization_drift(self):
        path = self.fixture(wordpiece_tokenizer(lowercase=True), WORDPIECE_SPECIALS,
                            [text_case('Hello WORLDs!')])
        folded = capture_manifest(path)
        # Change only the real tokenizer normalizer, not messages or the template.
        wordpiece_tokenizer(lowercase=False).save(str(self.root / 'tokenizer.json'))
        preserved = capture_manifest(path)
        before, after = folded['cases'][0], preserved['cases'][0]

        self.assertEqual(before['rendered_text'], 'Hello WORLDs!')
        self.assertEqual(after['rendered_text'], 'Hello WORLDs!')
        self.assertEqual(before['messages_sha256'], after['messages_sha256'])
        self.assertEqual(before['input_ids'], [5, 6, 7, 8])
        self.assertEqual(after['input_ids'], [3, 4, 7, 8])
        self.assertEqual(after['tokens'], ['Hello', 'WORLD', '##s', '!'])
        self.assertEqual(folded['artifacts']['vocabulary_sha256'],
                         preserved['artifacts']['vocabulary_sha256'])
        self.assertEqual(folded['artifacts']['template_sha256'],
                         preserved['artifacts']['template_sha256'])
        self.assertNotEqual(folded['artifacts']['tokenizer_sha256'],
                            preserved['artifacts']['tokenizer_sha256'])
        report = explain_snapshots(folded, preserved, include_content=True)
        row = report['case_results'][0]
        self.assertEqual(report['status'], 'drift')
        self.assertIn('TOKENIZATION_CHANGED', row['stages'])
        self.assertNotIn('RENDER_CHANGED', row['stages'])
        self.assertNotIn('VOCABULARY_CHANGED', row['stages'])
        self.assertNotIn('POSTPROCESSING_CHANGED', row['stages'])
        self.assertEqual(row['analysis']['earliest_stage'], 'tokenization')
        self.assertEqual(row['analysis']['character_change']['alignment'], 'equal')
        changes = row['analysis']['token_change']
        self.assertEqual(changes['total_windows'], 1)
        self.assertEqual(changes['windows'][0]['baseline_preview']['changed'], [5, 6])
        self.assertEqual(changes['windows'][0]['candidate_preview']['changed'], [3, 4])

    def test_assistant_prefill_continuation_removes_only_final_closing_marker(self):
        backend = bytelevel_tokenizer()
        cases = [{'id': 'prefill', 'messages': [
            {'role': 'user', 'content': 'Name a city.'},
            {'role': 'assistant', 'content': '{"city": "Par'},
        ]}]
        path = self.fixture(backend, BYTE_SPECIALS, cases, template=CHAT_TEMPLATE)
        closed = capture_manifest(path)
        self.manifest['options']['continue_final_message'] = True
        continued = capture_manifest(self.save_manifest('continued.json'))
        self.manifest['options']['route'] = 'render_then_encode'
        safe = capture_manifest(self.save_manifest('continued-safe.json'))
        expected = '<bos>user: Name a city.<eos>\nassistant: {"city": "Par'

        self.assertEqual(closed['cases'][0]['rendered_text'], expected + '<eos>\n')
        self.assertTrue(closed['cases'][0]['rendered_text'].endswith('<eos>\n'))
        self.assertEqual(closed['cases'][0]['input_ids'].count(2), 2)
        for snapshot in (continued, safe):
            row = snapshot['cases'][0]
            self.assertTrue(snapshot['options']['continue_final_message'])
            self.assertFalse(snapshot['options']['add_generation_prompt'])
            self.assertEqual(row['rendered_text'], expected)
            self.assertTrue(row['rendered_text'].endswith('{"city": "Par'))
            self.assertNotIn('<eos>', row['rendered_text'].split('assistant: ', 1)[1])
            self.assertEqual(row['input_ids'].count(2), 1, 'The earlier user closing marker remains')
            self.assertEqual(row['input_ids'], backend.encode(expected, add_special_tokens=False).ids)
            self.assertEqual(backend.decode(row['input_ids'], skip_special_tokens=False), expected)
        self.assertEqual(compare_snapshots(continued, safe)['status'], 'match')
        report = compare_snapshots(closed, continued)
        self.assertEqual(report['status'], 'incomparable')
        self.assertEqual(report['case_results'][0]['stages'], ['INTENT_CHANGED'])

    def test_self_authored_v01_schema_baseline_is_accepted_by_live_check(self):
        path = self.fixture(wordpiece_tokenizer(lowercase=True), WORDPIECE_SPECIALS,
                            [text_case('Hello WORLDs!')])
        # Compatibility content authored for this test, NOT an archived artifact
        # or evidence of historical v0.1 execution. IDs/spellings are hand-written;
        # only real local fingerprints and installed runtime versions are computed.
        legacy = {
            'schema_version': 1, 'producer': 'chat-input-contract/0.1.0',
            'runtime': {name: importlib.metadata.version(name)
                        for name in ('transformers', 'tokenizers', 'jinja2')},
            'artifacts': {
                'tokenizer_sha256': hashlib.sha256((self.root / 'tokenizer.json').read_bytes()).hexdigest(),
                'template_sha256': hashlib.sha256(TEXT_TEMPLATE.encode('utf-8')).hexdigest(),
                'vocabulary_sha256': canonical_sha256(
                    {'vocab': WORDPIECE_VOCAB, 'special_tokens': WORDPIECE_SPECIALS}),
            },
            'options': {'route': 'direct', 'add_special_tokens': False,
                        'add_generation_prompt': False, 'continue_final_message': False},
            'cases': [{
                'id': 'sample',
                'messages_sha256': canonical_sha256([{'role': 'user', 'content': 'Hello WORLDs!'}]),
                'rendered_text': 'Hello WORLDs!', 'input_ids': [5, 6, 7, 8],
                'tokens': ['hello', 'world', '##s', '!'],
                'direct_ids': [5, 6, 7, 8], 'unprocessed_ids': [5, 6, 7, 8],
                'postprocessed_ids': [1, 5, 6, 7, 8, 2],
            }],
        }
        baseline_path = self.root / 'self-authored-v01-schema.json'
        baseline_path.write_bytes(json.dumps(legacy).encode('utf-8'))
        baseline_bytes = baseline_path.read_bytes()

        current = capture_manifest(path)
        self.assertEqual(current['cases'], legacy['cases'])
        comparison = compare_snapshots(legacy, current)
        self.assertEqual(comparison['schema_version'], 1)
        self.assertEqual(comparison['status'], 'match')
        report = check_manifest(path, baseline_path)
        self.assertEqual(report['schema_version'], 2)
        self.assertEqual(report['status'], 'match')
        self.assertEqual(report['provenance_changes'], [])
        self.assertEqual(report['case_results'][0]['stages'], [])
        self.assertEqual(baseline_path.read_bytes(), baseline_bytes)


if __name__ == '__main__':
    unittest.main()
