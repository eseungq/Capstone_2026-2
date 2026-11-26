import copy
import json
from pathlib import Path
import unittest
from PIL import Image
from frame_model.check import ROOT
from frame_model.validate_input_background import validate

class InputBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.source={'schema':'frame-input-background-regions-v1','reviewId':'fixture','probePlanSha256':'fixed','cases':[{'id':'10','displaySize':[4032,1960]}]}
        self.payload={'schema':self.source['schema'],'reviewId':'fixture','probePlanSha256':'fixed','reviewer':'fixture','cases':{'10':{'visibility224':'weak','visibility448':'clear','regionStatus':'marked','partBox':[.1,.1,.2,.2],'backgroundCenter':[.7,.7]}}}
    def test_equal_pixel_area_and_padding_exclusion(self):
        case=validate(self.payload,self.source)[0]
        a=case['part_mask_224'];b=case['background_mask_224'];v=case['display_crop_224']
        self.assertEqual((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
        for r in [a,b]:self.assertTrue(v[0]<=r[0]<r[2]<=v[2] and v[1]<=r[1]<r[3]<=v[3])
    def test_overlap_and_outside_rejected(self):
        for center in [[.15,.15],[0,0]]:
            payload=copy.deepcopy(self.payload);payload['cases']['10']['backgroundCenter']=center
            with self.assertRaises(ValueError):validate(payload,self.source)
    def test_skip_requires_reason(self):
        self.payload['cases']['10']['regionStatus']='unavailable'
        with self.assertRaises(ValueError):validate(self.payload,self.source)
        self.payload['cases']['10']['note']='No clear physical background'
        self.assertEqual(validate(self.payload,self.source)[0]['status'],'unavailable')
    def test_actual_assets_have_expected_sizes(self):
        directory=Path(json.loads((ROOT/'frame_model/latest_input_background.json').read_text())['directory']);source=json.loads((directory/'source.json').read_text());self.assertEqual(len(source['cases']),8)
        for case in source['cases']:
            self.assertEqual(case['source']['split'],'model_selection')
            for field,size in [('input224',(224,224)),('input224Enlarged',(448,448)),('input448',(448,448))]:
                with Image.open(directory/case[field]) as image:self.assertEqual(image.size,size)

if __name__=='__main__':unittest.main()
