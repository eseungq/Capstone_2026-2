import csv
import io
import json
from pathlib import Path
import unittest
import tempfile
from frame_model.cam_objective_probe import render
from frame_model.check import ROOT

class ProbePlanTests(unittest.TestCase):
    def test_interrupted_report_render_preserves_partial_results(self):
        directory=Path(json.loads((ROOT/'frame_model/latest_cam_probe.json').read_text())['directory']);plan=json.loads((directory/'probe_plan.json').read_text())
        item=plan['items'][0]
        with tempfile.TemporaryDirectory() as temporary:
            render(Path(temporary),plan,{'results':[{'id':item['id'],'model':'unified','layer':plan['layers'][0]}]})
            self.assertIn('NOT_COMPLETED',(Path(temporary)/'index.html').read_text())

    def test_scope_and_source_evidence(self):
        directory=Path(json.loads((ROOT/'frame_model/latest_cam_probe.json').read_text())['directory']);plan=json.loads((directory/'probe_plan.json').read_text())
        self.assertEqual(len(plan['items']),8);self.assertEqual(set(plan['checkpoints']),{'unified','type_03','type_04'});self.assertEqual(plan['objectives'],['defect','margin'])
        self.assertFalse(plan['training_performed']);self.assertFalse(plan['service_changed']);self.assertFalse(plan['final_test_used'])
        self.assertEqual(sum(int(r['pair']['actual']) for r in plan['items']),6)
        for item in plan['items']:
            self.assertEqual(item['source']['split'],'model_selection')
            for model in ['unified',item['specialist_id']]:
                self.assertEqual(item['baseline_results'][model]['predicted_quality'],'DEFECT')
                self.assertTrue(item['baseline_results'][model]['class_matches_saved'])
                self.assertTrue(item['baseline_results'][model]['batch_score_matches_saved'])
            self.assertTrue(Path(item['display_path']).is_file())
        geometry=list(csv.DictReader(io.StringIO((directory/'input_geometry.csv').read_text())))
        self.assertEqual({int(r['contained_height']) for r in geometry},{101,109})
        self.assertTrue(all(0<float(r['padding_area_fraction'])<1 for r in geometry))

if __name__=='__main__':unittest.main()
