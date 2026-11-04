import io
import unittest
from PIL import Image
from ai_api.cam_encoding import encode_overlay
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
