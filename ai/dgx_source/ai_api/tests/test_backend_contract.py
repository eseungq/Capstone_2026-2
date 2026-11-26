"""CPU fixture HTTP-handler checks; never GPU or real backend integration."""
import base64
import io
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from ai_api import backend_contract
from ai_api.tests import test_api
from ai_api.tests.test_api import memory_request
from ai_api.server import Handler

class BackendAdapterTests(unittest.TestCase):
    body=test_api.API.body
    tearDown=test_api.API.tearDown
    def setUp(self):
        test_api.API.setUp(self);self.service.response_profile=backend_contract.PROFILE

    def test_good_defect_cam_failure_fields_and_full_duration(self):
        download=self.service.downloader
        def slow(url):time.sleep(.02);return download(url)
        self.service.downloader=slow
        code,good=memory_request(self.service,self.body());self.assertEqual(code,200)
        self.assertIsNone(good['gradcam']);self.assertIsNone(good['calibratedDefectProbability']);self.assertIsNone(good['calibratorVersion'])
        self.assertIsInstance(good['inferenceTimeMs'],int);self.assertGreaterEqual(good['inferenceTimeMs'],20)
        code,defect=memory_request(self.service,self.body('defect'))
        self.assertEqual(code,200);self.assertEqual(defect['gradcam']['targetClass'],'DEFECT');self.assertEqual(defect['gradcam']['format'],'png')
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(defect['gradcam']['imageBase64'],validate=True))) as im:self.assertEqual(im.size,(10,20))
        self.engine.mode='cam-fail';code,failed=memory_request(self.service,self.body('defect'))
        self.assertEqual(code,200);self.assertEqual(failed['predictedQuality'],'DEFECT');self.assertIsNone(failed['gradcam'])
        records=[json.loads(line) for line in (Path(self.temp.name)/'requests.jsonl').read_text().splitlines()]
        wires=[r for r in records if r.get('event')=='wire_response']
        self.assertEqual(len(wires),3);self.assertTrue(all(r['classificationTimeMs']==1.0 for r in wires))
        self.assertTrue(all(r['wireInferenceTimeMs']>=20 for r in wires))

    def test_zero_constant_keep_success_and_legacy_computation_state(self):
        for mode,state in [('zero','ZERO_MAP'),('constant','CONSTANT_MAP')]:
            self.engine.mode=mode;status,r=memory_request(self.service,self.body('defect'))
            self.assertEqual(status,200);self.assertEqual(r['predictedQuality'],'DEFECT');self.assertEqual(r['gradcam']['status'],state)
        records=[json.loads(x) for x in (Path(self.temp.name)/'requests.jsonl').read_text().splitlines()]
        self.assertTrue(all(r['backendCompatibleKnownCase'] is False for r in records if r.get('event')=='wire_response'))

    def test_error_wrapper_trace_and_private_details(self):
        for mode,kind in [('inference-fail','good'),('normal','missing'),('normal','broken')]:
            self.engine.mode=mode;status,r=memory_request(self.service,self.body(kind))
            self.assertGreaterEqual(status,400);self.assertEqual(set(r),{'error'});e=r['error']
            self.assertEqual(set(e),{'code','message','traceId','inspectionId'});self.assertEqual(e['inspectionId'],'id-1');self.assertEqual(len(e['traceId']),32)
            self.assertNotIn('PRIVATE',json.dumps(r));self.assertTrue(any(json.loads(x)['requestId']==e['traceId'] for x in (Path(self.temp.name)/'requests.jsonl').read_text().splitlines()))
        status,r=memory_request(self.service,b'{',raw=True);self.assertEqual(status,400);self.assertIsNone(r['error']['inspectionId'])

    def test_parallel_identity_and_cam_do_not_mix(self):
        def run(i):
            kind='good' if i%2==0 else 'defect';code,r=memory_request(self.service,self.body(kind,str(i)))
            self.assertEqual(code,200);self.assertEqual(r['inspectionId'],str(i));self.assertEqual(r['predictedQuality'],'GOOD' if i%2==0 else 'DEFECT')
            self.assertEqual(r['gradcam'] is None,i%2==0)
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(run,range(6)))
        self.assertEqual(self.engine.overlaps,0)

    def test_models_shape_reflects_real_availability(self):
        self.engine.model=SimpleNamespace(training=False);self.engine.metadata={'model_sha256':'fixture-hash','model_name':'fixture'}
        with patch('prototype.engine.sha',return_value='fixture-hash'):
            result=backend_contract.inventory(self.service.model_inventory());self.assertTrue(result['data'][0]['loadable']);self.assertIsNone(result['data'][0]['calibratorVersion'])
        with patch('prototype.engine.sha',return_value='changed'):
            self.assertFalse(backend_contract.inventory(self.service.model_inventory())['data'][0]['loadable'])

    def test_get_models_actual_handler_header_and_loadable(self):
        self.engine.model=SimpleNamespace(training=False);self.engine.metadata={'model_sha256':'fixture-hash','model_name':'fixture'}
        wire=b'GET /internal/v1/models HTTP/1.0\r\n\r\n'
        class Connection:
            def __init__(self):self.output=bytearray()
            def makefile(self,*args):return io.BytesIO(wire)
            def sendall(self,data):self.output.extend(data)
            def settimeout(self,*args):pass
        connection=Connection()
        with patch('prototype.engine.sha',return_value='fixture-hash'):Handler(connection,('127.0.0.1',0),SimpleNamespace(service=self.service))
        head,payload=bytes(connection.output).split(b'\r\n\r\n',1)
        self.assertIn(b'200',head.split(b'\r\n')[0]);self.assertIn(b'X-AI-Model-SHA256: fixture-hash',head)
        self.assertEqual(json.loads(payload)['data'][0],dict(modelVersion='TEST_FIXTURE_NOT_GPU',partCode='DOOR',calibratorVersion=None,loadable=True))

if __name__=='__main__':
    import unittest
    unittest.main()
