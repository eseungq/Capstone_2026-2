import json
import tempfile
import unittest
from pathlib import Path
from collections import Counter
from ai_api.setup_followup import select_additional,load_selection
from ai_api.diagnostics import ROOT,RUN,read,normalize_predictions


class Followup(unittest.TestCase):
    def test_disjoint_balanced_reproducible_selection(self):
        rows=[dict(image_path=f'/tmp/{kind}-{i}',kind=kind) for kind in ('TP','TN','FP','FN') for i in range(10)]
        excluded={r['image_path'] for r in rows[::2]}
        chosen=select_additional(rows,excluded)
        self.assertEqual(chosen,select_additional(rows,excluded))
        self.assertEqual(Counter(r['kind'] for r in chosen),dict(TP=3,TN=3,FP=3,FN=3))
        self.assertFalse({r['image_path'] for r in chosen}&excluded)
    def test_actual_followup_list_and_tamper_rejection(self):
        path=ROOT/'ai_api/verification/followup_20261016T154826_744914Z/additional_selection.json'
        if not path.exists():self.skipTest('Prepared evidence not present')
        rows=normalize_predictions(read(RUN/'best_internal_validation_predictions.csv'))
        self.assertEqual(len(load_selection(path,rows)),12)
        d=json.loads(path.read_text());d['samples'][0]['raw_defect_score']='0'
        with tempfile.TemporaryDirectory() as folder:
            altered=Path(folder)/'altered.json';altered.write_text(json.dumps(d))
            with self.assertRaises(ValueError):load_selection(altered,rows)


if __name__=='__main__':unittest.main()
