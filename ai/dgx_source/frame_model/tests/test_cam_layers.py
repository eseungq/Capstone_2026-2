import csv
import io
import json
from pathlib import Path
import unittest
from frame_model.check import ROOT
from frame_model.prepare_cam_review import choose_shared_defect

class LayerSelectionTests(unittest.TestCase):
    def test_shared_defect_selection_excludes_prior_images_and_groups(self):
        previous=json.loads((ROOT/'outputs/frame_cam_review/20261026T144548_871522Z/selection.json').read_text())
        rows=list(csv.DictReader(io.StringIO((ROOT/'outputs/frame_training/comparison_train_20261022T160533_169658Z/paired_predictions.csv').read_text())))
        sources=list(csv.DictReader(io.StringIO((ROOT/'outputs/frame_experiment_plan/20261022T143934_220484Z/comparison_candidate/unified_model_selection.csv').read_text())))
        source={r['image_id']:r for r in sources};selected,_=choose_shared_defect(rows,source,[previous]);again,_=choose_shared_defect(list(reversed(rows)),source,[previous])
        self.assertEqual([x['pair']['image_id'] for x in selected],[x['pair']['image_id'] for x in again])
        self.assertEqual(len(selected),16);old_ids={r['source']['image_id'] for r in previous['items']};old_groups={r['source']['group_id'] for r in previous['items']}
        seen=set()
        for x in selected:
            r=x['pair'];self.assertEqual(r['unified_prediction'],'1');self.assertEqual(r['specialist_prediction'],'1');self.assertNotIn(r['image_id'],old_ids)
            group=source[r['image_id']]['group_id'];self.assertNotIn(group,old_groups|seen);seen.add(group)
        for kind in {x['pair']['defect_type'] for x in selected}:
            actual=[x['pair']['actual'] for x in selected if x['pair']['defect_type']==kind];self.assertEqual(actual.count('1'),3);self.assertEqual(actual.count('0'),1)
    def test_insufficient_fp_is_not_replaced(self):
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            choose_shared_defect([dict(image_id='x',defect_type='hole',unified_prediction='1',specialist_prediction='1',actual='1')],{'x':{'group_id':'g'}},[])

if __name__=='__main__':unittest.main()
