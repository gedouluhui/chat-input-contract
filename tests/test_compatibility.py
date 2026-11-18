import copy
import hashlib
import json
from pathlib import Path
import unittest
from chat_input_contract import compare_snapshots, validate_snapshot


class CompatibilityTests(unittest.TestCase):
    def test_actual_v0_1_capture_is_readable_and_not_rewritten(self):
        path = Path(__file__).parent/'fixtures/v0_1_direct.json'
        before = path.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), '74e4dd58f04809cc03b59be5904eb4bf4b4ef498ac0bebd09163eb59d9f8ffa6')
        old = json.loads(before)
        self.assertEqual(old['producer'], 'chat-input-contract/0.1.0')
        validate_snapshot(old)
        result = compare_snapshots(old, copy.deepcopy(old))
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(result['status'], 'match')
        self.assertEqual(path.read_bytes(), before)

    def test_new_producer_compares_to_old_under_same_contract(self):
        old = json.loads((Path(__file__).parent/'fixtures/v0_1_direct.json').read_bytes())
        new = copy.deepcopy(old); new['producer'] = 'chat-input-contract/0.2.0'
        self.assertEqual(compare_snapshots(old, new)['status'], 'match')
        new['producer'] = 'unknown/future'
        with self.assertRaises(ValueError): validate_snapshot(new)

    def test_old_inconsistent_snapshot_does_not_claim_postprocessing_cause(self):
        from test_core import snapshot
        a, b = snapshot(), snapshot(); c = b['cases'][0]
        c['input_ids'] = c['direct_ids'] = [7]; c['tokens'] = ['changed']
        result = compare_snapshots(a, b)
        self.assertIn('ROUTE_INCONSISTENCY', result['case_results'][0]['stages'])
        self.assertNotIn('POSTPROCESSING_CHANGED', result['case_results'][0]['stages'])


if __name__ == '__main__': unittest.main()
