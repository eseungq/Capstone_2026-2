import csv
import io
import json
from pathlib import Path
import unittest
from PIL import Image
from frame_model.check import ROOT
from frame_model.prepare_cam_review import choose_cases
from frame_model.cam_review import verify_metadata

class CamReviewTests(unittest.TestCase):
    def test_metadata_json_roundtrip_and_real_mismatch(self):
        actual={'pretrained_configuration':{'input_size':(3,224,224),'mean':(.485,.456,.406),'pool_size':(7,7)},'config':{'prediction_cutoff':.5},'versions':{'timm':'1.0.30'}}
        expected=json.loads(json.dumps(actual))
        self.assertNotEqual(actual,expected)
        self.assertEqual(verify_metadata(actual,expected)['status'],'matched')
        for section,key,value in [('config','prediction_cutoff',.6),('versions','timm','other'),('pretrained_configuration','input_size',[3,384,384])]:
            changed=json.loads(json.dumps(expected));changed[section][key]=value
            with self.assertRaisesRegex(ValueError,r'metadata\.'):
                verify_metadata(actual,changed)
        changed=json.loads(json.dumps(expected));del changed['versions']
        with self.assertRaises(ValueError):verify_metadata(actual,changed)
        with self.assertRaises(ValueError):verify_metadata({'bad':float('nan')},{'bad':float('nan')})

    def test_fixed_selection_preserves_all_missed_candidates(self):
        path=ROOT/'outputs/frame_training/comparison_train_20261022T160533_169658Z/paired_predictions.csv'
        rows=list(csv.DictReader(io.StringIO(path.read_text())))
        selected,candidates=choose_cases(rows)
        self.assertEqual(len(candidates),45)
        self.assertEqual(len(selected),24)
        self.assertEqual({x['pair']['image_id'] for x in selected},{x['pair']['image_id'] for x in choose_cases(list(reversed(rows)))[0]})
        for kind in {r['defect_type'] for r in rows}:
            chosen=[x for x in selected if x['pair']['defect_type']==kind]
            self.assertEqual(len(chosen),6)
            self.assertTrue(any('both_TN_control' in x['reasons'] for x in chosen))
            self.assertTrue(any('both_TP_control' in x['reasons'] for x in chosen))
            self.assertEqual(sum(any(r.startswith('specialist_FN') for r in x['reasons']) for x in chosen),2)
    def test_prepared_images_have_correct_size_and_source_role(self):
        directory=ROOT/'outputs/frame_cam_review/20261026T144548_871522Z';selection=json.loads((directory/'selection.json').read_text())
        self.assertEqual(len(selection['items']),24)
        for row in selection['items']:
            self.assertEqual(row['source']['split'],'model_selection')
            with Image.open(directory/row['id']/'display.png') as im:self.assertEqual(list(im.size),row['display_size'])
            with Image.open(directory/row['id']/'input224.png') as im:self.assertEqual(im.size,(224,224))
            self.assertTrue((directory/row['id']/'label.json').is_file())

if __name__=='__main__':unittest.main()
