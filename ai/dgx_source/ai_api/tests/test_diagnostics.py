"""CPU-only automation checks. Do not claim GPU CAM computation."""
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from ai_api.diagnostics import choose,mask_indices,render,normalize_predictions,reuse_http_report,read,RUN,ROOT


class Diagnostics(unittest.TestCase):
    def test_actual_training_csv_without_kind(self):
        original=read(RUN/'best_internal_validation_predictions.csv')
        self.assertNotIn('kind',original[0])
        rows=normalize_predictions(original)
        self.assertEqual(Counter(r['kind'] for r in rows),dict(TP=1107,TN=891,FP=18,FN=23))
        self.assertNotIn('kind',original[0])
        internal={r['image_path'] for r in rows}
        samples=choose(rows,internal,dict(samples=[]))
        self.assertEqual(Counter(r['kind'] for r in samples),dict(TP=3,TN=3,FP=3,FN=3))
    def test_derivation_and_conflict_rejection(self):
        rows=[dict(image_path='a',class_id=str(y),predicted_class=str(p),raw_defect_score=str(.8 if p else .2))
              for y,p in [(1,1),(0,0),(0,1),(1,0)]]
        self.assertEqual([r['kind'] for r in normalize_predictions(rows)],['TP','TN','FP','FN'])
        with self.assertRaises(ValueError):normalize_predictions([dict(rows[0],kind='TN')])
        with self.assertRaises(ValueError):normalize_predictions([dict(rows[0],raw_defect_score='nan')])
    def test_reuse_completed_http_report_and_reject_wrong_version(self):
        p=ROOT/'ai_api/verification/20261016T135431_704517Z/verification.json'
        if not p.exists():self.skipTest('Specific host-run evidence not present')
        report=reuse_http_report(p,'UNREGISTERED-door-swin-tiny-diagnostic')
        self.assertTrue(report['independentHttpCamChecksPassed'])
        self.assertEqual(report['result'],'failed_or_blocked')
        self.assertTrue(report['savedScoreFailures'])
        with self.assertRaises(ValueError):reuse_http_report(p,'different-version')
    def test_equal_area_masks_and_excluded_padding(self):
        values=list(range(100));eligible=list(range(20,80))
        masks=mask_indices(values,eligible)
        self.assertEqual({len(v) for v in masks.values()},{12})
        self.assertEqual(masks['top'],list(range(68,80)))
        self.assertEqual(masks['low'],list(range(20,32)))
        self.assertEqual(masks,mask_indices(values,eligible))
        self.assertTrue(all(set(v)<=set(eligible) for v in masks.values()))
    def test_selection_balanced_internal_only_and_prior_cam(self):
        rows=[dict(image_path=f'/tmp/fixture-{kind}-{i}.jpg',kind=kind) for kind in ('TP','TN','FP','FN') for i in range(5)]
        internal={r['image_path'] for r in rows};prior=rows[4]['image_path']
        rows.append(dict(image_path='/tmp/outside-internal.jpg',kind='TP'))
        samples=choose(rows,internal,dict(samples=[dict(image_path=prior,target_class=1)]))
        self.assertEqual(Counter(r['kind'] for r in samples),dict(TP=3,TN=3,FP=3,FN=3))
        self.assertIn(prior,{r['image_path'] for r in samples})
        self.assertTrue(all(r['image_path'] in internal for r in samples))
    def test_partial_report_renders_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as folder:
            report=dict(samples=[dict(id='sample_00',savedKind='FP',error='sample failed',layers=[])])
            render(Path(folder),report)
            text=(Path(folder)/'index.html').read_text()
            self.assertIn('sample failed',text)
            self.assertIn('오프라인 실험',text)


if __name__=='__main__':unittest.main()
