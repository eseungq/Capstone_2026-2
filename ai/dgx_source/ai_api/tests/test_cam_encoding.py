"""Display codec and fixture-handler tests; not actual GPU/back-end JPEG acceptance."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from ai_api.cam_encoding import encode_overlay
from ai_api.server import Service
from ai_api import backend_contract
from ai_api.tests.test_api import FixtureEngine,picture,memory_request

class CamEncodingTests(unittest.TestCase):
    def source(self):
        im=Image.new('RGB',(64,40),(20,200,20))
        for x in range(32):
            for y in range(20):im.putpixel((x,y),(220,20,20))
        stream=io.BytesIO();im.save(stream,'PNG');return stream.getvalue()
    def test_default_png_exact_bytes(self):
        src=self.source();result,mime=encode_overlay(src,(64,40));self.assertEqual(result,src);self.assertEqual(mime,'image/png')
    def test_jpeg_keeps_geometry_and_orientation(self):
        for q in [85,90,95]:
            encoded,mime=encode_overlay(self.source(),(64,40),'jpeg',q);self.assertEqual(mime,'image/jpeg')
            with Image.open(io.BytesIO(encoded)) as im:
                self.assertEqual(im.format,'JPEG');self.assertEqual(im.size,(64,40));self.assertEqual(im.getexif().get(274,1),1)
                a,b=im.getpixel((8,8)),im.getpixel((50,30));self.assertGreater(a[0],a[1]);self.assertGreater(b[1],b[0])
    def test_corrupt_wrong_size_and_invalid_quality_rejected(self):
        for blob,size,q in [(b'broken',(64,40),90),(self.source(),(40,64),90),(self.source(),(64,40),0),(self.source(),(64,40),100)]:
            with self.assertRaises((ValueError,OSError)):encode_overlay(blob,size,'jpeg',q)
    def test_fixture_prediction_unchanged_and_encoding_failure_keeps_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine=FixtureEngine();service=Service(engine,'TEST_FIXTURE_NOT_GPU',lambda url:picture(200,True),tmp,response_profile=backend_contract.PROFILE,cam_format='jpeg',jpeg_quality=90)
            body=dict(inspectionId='codec-fixture',partCode='DOOR',requestedModelVersion='TEST_FIXTURE_NOT_GPU',imageUrl='http://fixture/defect')
            status,response=memory_request(service,body);self.assertEqual(status,200);self.assertEqual(response['predictedQuality'],'DEFECT');self.assertEqual(response['rawDefectProbability'],.9);self.assertEqual(response['gradcam']['format'],'jpeg')
            with Image.open(io.BytesIO(base64.b64decode(response['gradcam']['imageBase64'],validate=True))) as im:self.assertEqual(im.size,(10,20));self.assertEqual(im.format,'JPEG')
            records=[json.loads(x) for x in (Path(tmp)/'requests.jsonl').read_text().splitlines()];record=next(r for r in records if r.get('event')!='wire_response');self.assertEqual(record['camJpegQuality'],90);self.assertEqual(record['camFormat'],'jpeg')
            with patch('ai_api.server.encode_overlay',side_effect=RuntimeError('PRIVATE_ENCODER_DETAIL')):status,failed=memory_request(service,body)
            self.assertEqual(status,200);self.assertEqual(failed['rawDefectProbability'],.9);self.assertIsNone(failed['gradcam']);self.assertNotIn('PRIVATE',json.dumps(failed))
    def test_legacy_jpeg_configuration_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):Service(FixtureEngine(),'TEST_FIXTURE_NOT_GPU',lambda url:picture(200),tmp,cam_format='jpeg')

if __name__=='__main__':unittest.main()
