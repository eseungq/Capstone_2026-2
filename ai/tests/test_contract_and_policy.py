import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from PIL import Image
from ai_api import contract
from ai_api.cam_encoding import encode_overlay
from ai_api.e02_engine import CandidateEngine, LegacyEngine
from ai_api.e02_integration.serve import IntegrationService
from ai_api.e02_integration.timing import REQUEST_TIMINGS, STAGES
from ai_api.e02_integration.verify_stub_http import main as verify_http
from tools.evaluate_policy_scores import evaluate


class IntegrationContractTests(unittest.TestCase):
    def test_v4_real_http_with_stub_engine(self):
        result=verify_http()
        self.assertEqual(result['status'],'passed')
        self.assertIn('ZERO_MAP',result['checks'])
        self.assertIn('classification_failure',result['checks'])

    def test_jpeg_encoding_keeps_dimensions(self):
        original=Image.new('RGB',(19,13),(10,50,100));blob=io.BytesIO();original.save(blob,format='PNG')
        encoded,mime=encode_overlay(blob.getvalue(),(19,13),'jpeg',90)
        self.assertEqual(mime,'image/jpeg')
        with Image.open(io.BytesIO(encoded)) as im:self.assertEqual(im.size,(19,13));self.assertEqual(im.format,'JPEG')

    def test_e02_stage_timings_are_request_local_and_audit_only(self):
        blob = io.BytesIO()
        Image.new('RGB', (19, 13)).save(blob, format='PNG')
        version = 'door-test'
        engine = CandidateEngine.__new__(CandidateEngine)
        engine.metadata = {'model_version': version}

        def download(url):
            if url.endswith('/fail'):
                raise contract.Failure('IMAGE_ACCESS_FAILED', 422)
            return blob.getvalue()

        def predict(path):
            engine.tensor(path)
            return {'raw_defect_score': predict.score, 'predicted_class': int(predict.score >= .5), 'processing_ms': 2.0}

        def explain(path, dest, cls):
            engine.tensor(path)
            return dict(state_unchanged=True, eval_mode=True, raw_min=0, raw_max=0, constant=True)

        with TemporaryDirectory() as folder, patch.object(engine, 'predict', predict), \
                patch.object(LegacyEngine, 'tensor', return_value=object()), \
                patch.object(LegacyEngine, 'explain', side_effect=explain):
            service = IntegrationService(engine, version, download, folder)
            body = dict(inspectionId='timing', partCode='DOOR', requestedModelVersion=version,
                        imageUrl='http://fixture/image?signature=private')
            predict.score = .9
            with patch('ai_api.e02_integration.timing.perf_counter', side_effect=[0, .001, .002, .005, .006, .015]):
                result = service.predict(body, request_id='defect')
            self.assertEqual(result['gradcam']['status'], 'ZERO_MAP')
            self.assertTrue(set(STAGES).isdisjoint(result))
            predict.score = .1
            service.predict(body, request_id='good')
            with self.assertRaises(contract.Failure):
                service.predict({**body, 'imageUrl': 'http://fixture/fail'}, request_id='failed')
            log = (Path(folder) / 'requests.jsonl').read_text()
            self.assertNotIn('signature=private', log)
            defect, good, failed = map(json.loads, log.splitlines())
            self.assertEqual([r['requestId'] for r in (defect, good, failed)], ['defect', 'good', 'failed'])
            for stage, milliseconds in zip(STAGES, (1, 3, 9)):
                self.assertAlmostEqual(defect[stage], milliseconds)
            self.assertIsNone(good['camGenerationMs'])
            self.assertGreaterEqual(failed['imageDownloadMs'], 0)
            self.assertIsNone(failed['preprocessingMs'])
            self.assertIsNone(failed['camGenerationMs'])
            self.assertIsNone(REQUEST_TIMINGS.get())

    def test_defect_prediction_never_passes_even_with_low_calibrated_value(self):
        row=dict(class_id=1,raw_defect_score=.9,predicted_class=1,calibrated_defect_probability=.001)
        self.assertEqual(evaluate([row],.1)['autoPassCount'],0)

    def test_missing_calibration_always_reviews(self):
        row=dict(class_id=0,raw_defect_score=.01,predicted_class=0,calibrated_defect_probability='')
        self.assertEqual(evaluate([row],.1)['reviewCount'],1)

    def test_policy_metrics_use_actual_defects_as_miss_denominator(self):
        rows=[dict(class_id=1,raw_defect_score=.1,predicted_class=0,calibrated_defect_probability=.01),
              dict(class_id=1,raw_defect_score=.9,predicted_class=1,calibrated_defect_probability=.9),
              dict(class_id=0,raw_defect_score=.01,predicted_class=0,calibrated_defect_probability=.01)]
        m=evaluate(rows,.05)
        self.assertEqual(m['missedDefectRate'],.5)
        self.assertEqual(m['autoPassContaminationRate'],.5)
        self.assertEqual(m['autoPassCount'],2)

    def test_invalid_nan_probability_rejected(self):
        row=dict(class_id=0,raw_defect_score=float('nan'),predicted_class=0,calibrated_defect_probability=.01)
        with self.assertRaises(ValueError):evaluate([row],.1)


if __name__=='__main__':unittest.main()
