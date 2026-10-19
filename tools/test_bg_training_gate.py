"""No network or game operations: promotion criteria and schedule identity."""
import unittest
import json
from pathlib import Path
import tempfile
from core.bg_training_gate import compare
from core.bg_lab_status import training_status

def rows(n,rank):
    return [dict(seed=100+i,seat=0,placements=[rank,1,2,3,5,6,7,8]) for i in range(n)]

class GateTests(unittest.TestCase):
    def test_small_sample_cannot_pass(self):
        self.assertFalse(compare(rows(16,5),rows(16,3))['lab_pass'])

    def test_large_clear_lab_gain_still_never_certifies_live_rules(self):
        result=compare(rows(64,5),rows(64,3))
        self.assertTrue(result['lab_pass'])
        self.assertFalse(result['live_deployable'])
        self.assertEqual(result['paired_bootstrap_95'],[2.,2.])

    def test_identical_policy_is_not_progress(self):
        self.assertFalse(compare(rows(64,4),rows(64,4))['lab_pass'])

    def test_schedule_mismatch_and_empty_data_rejected(self):
        a,b=rows(8,5),rows(8,3);b[0]['seed']=999
        with self.assertRaises(ValueError):compare(a,b)
        with self.assertRaises(ValueError):compare([],[])

    def test_manifest_never_activates_a_policy_and_exposes_no_arbitrary_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'status.json'
            self.assertFalse(training_status(p)['available'])
            p.write_text(json.dumps(dict(schema=1,candidates=[dict(name='test',api_key='must-not-leak')],
                                         active_for_live_decisions=True)),encoding='utf-8')
            status=training_status(p)
            self.assertTrue(status['available'])
            self.assertFalse(status['active_for_live_decisions'])
            self.assertNotIn('must-not-leak',json.dumps(status))

if __name__=='__main__':unittest.main()
