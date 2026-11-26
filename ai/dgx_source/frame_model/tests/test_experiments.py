import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from frame_model.check import ROOT
from frame_model.experiments import load_plan
from frame_model.train import dump,subset,write_csv
from frame_model.compare import paired,compare_suite

PLAN=Path(json.loads((ROOT/'frame_model/latest_experiment_plan.json').read_text())['plan'])

class ComparisonTests(unittest.TestCase):
    def test_real_plan_and_type_smoke_pairing(self):
        _,_,experiments=load_plan(PLAN)
        self.assertEqual(len(experiments),5)
        allval=subset(experiments['unified'][1]['model_selection'],8)
        for ident,(exp,tables) in experiments.items():
            if ident=='unified':continue
            selected=subset(tables['model_selection'],8)
            self.assertEqual(len(selected),16)
            self.assertEqual(selected,[r for r in allval if r['defect_type']==exp['inspection_type']])
    def test_invalid_predictions_rejected(self):
        row=dict(image_id='a',actual='1',predicted='1',raw_defect_score='0.8',defect_type='hole')
        with self.assertRaises(ValueError):paired([row,row],[row])
        with self.assertRaises(ValueError):paired([row],[dict(row,image_id='b')])
        with self.assertRaises(ValueError):paired([row],[dict(row,actual='0')])
        with self.assertRaises(ValueError):paired([row],[dict(row,raw_defect_score='nan')])
        with self.assertRaises(ValueError):paired([row],[dict(row,predicted='0')])
        result,_=paired([row],[row]);self.assertEqual(result['paired_counts']['both_correct'],1)
    def test_full_cpu_report_and_tamper_rejection(self):
        # Synthetic predictions only: this test never loads models and is not a performance report.
        _,_,experiments=load_plan(PLAN)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);runs=[]
            for ident,(exp,tables) in experiments.items():
                directory=root/ident;directory.mkdir()
                dump(directory/'run_config.json',{'mode':'smoke','versions':{'fixture':'synthetic'},'initial_tensor_sha256':'same-initial-state','experiment_context':{'plan_sha256':hashlib.sha256(PLAN.read_bytes()).hexdigest(),'experiment_id':ident}})
                dump(directory/'status.json',{'status':'passed','quality_evaluation':False})
                for role,rows in tables.items():write_csv(directory/f'{role}_used.csv',subset(rows,16 if role=='train' else 8))
                rows=list(csv.DictReader(io.StringIO((directory/'model_selection_used.csv').read_text())))
                predictions=[dict(image_id=r['image_id'],defect_type=r['defect_type'],actual=r['class_id'],predicted=r['class_id'],raw_defect_score='0.8' if r['class_id']=='1' else '0.2') for r in rows]
                for name in ['smoke_predictions_NOT_EVALUATION.csv','last_model_selection_predictions.csv']:write_csv(directory/name,predictions)
                hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in directory.iterdir() if f.name!='status.json'}
                dump(directory/'artifacts.json',hashes)
                runs.append({'experiment_id':ident,'directory':str(directory),'status':'passed'})
            dump(root/'suite.json',{'status':'passed','mode':'smoke','plan':str(PLAN),'plan_sha256':hashlib.sha256(PLAN.read_bytes()).hexdigest(),'runs':runs})
            report=compare_suite(root/'suite.json');self.assertFalse(report['quality_evaluation']);self.assertEqual(len(report['by_type']),4)
            file=root/'type_01/smoke_predictions_NOT_EVALUATION.csv';file.write_text(file.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'Artifact hash'):compare_suite(root/'suite.json')

if __name__=='__main__':unittest.main()
