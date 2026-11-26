"""CPU fixtures only; no actual sockets, GPU or final-contract certification."""
import copy
import io
import json
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from ai_api.compatibility import candidate
from ai_api.server import Service,Handler
from ai_api.tests.test_api import FixtureEngine,picture,memory_request

class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.engine=FixtureEngine();self.service=Service(self.engine,'TEST_FIXTURE_NOT_GPU',lambda url:picture(200 if url.endswith('defect') else 10),self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def body(self,kind):return dict(inspectionId='fixture',partCode='DOOR',requestedModelVersion='TEST_FIXTURE_NOT_GPU',imageUrl='http://fixture/'+kind)
    def test_draft_preserves_original_and_does_not_invent_zero_state(self):
        for mode,kind,agreed in [('normal','good','NOT_REQUIRED'),('normal','defect','GENERATED'),('cam-fail','defect','FAILED'),('zero','defect',None),('constant','defect',None)]:
            self.engine.mode=mode;_,response=memory_request(self.service,self.body(kind));original=copy.deepcopy(response);draft=candidate(response)
            self.assertEqual(response,original);self.assertFalse(draft['activated']);self.assertEqual(draft['agreedStatusToPlace'],agreed);self.assertTrue(draft['unresolved'])
            self.assertNotIn('gradcamStatus',draft['responseDraftWithoutStatusPlacement'])
            self.assertNotIn('status',draft['responseDraftWithoutStatusPlacement']['gradcam'])
            self.assertIsNone(draft['responseDraftWithoutStatusPlacement']['calibratedDefectProbability'])
    def test_inventory_requires_loaded_eval_and_matching_current_file(self):
        self.assertFalse(self.service.model_inventory()['models'][0]['available'])
        self.engine.model=SimpleNamespace(training=False);self.engine.metadata={'model_sha256':'fixture-hash','model_name':'fixture'}
        with patch('prototype.engine.sha',return_value='fixture-hash'):
            self.assertTrue(self.service.model_inventory()['models'][0]['available'])
            self.engine.model.training=True;self.assertFalse(self.service.model_inventory()['models'][0]['available'])
            self.engine.model.training=False
        with patch('prototype.engine.sha',return_value='changed'):self.assertFalse(self.service.model_inventory()['models'][0]['available'])
        self.service.engine=None;self.assertFalse(self.service.model_inventory()['models'][0]['available'])
    def test_actual_get_handler_in_memory_not_tcp(self):
        wire=b'GET /internal/v1/models HTTP/1.0\r\n\r\n'
        class Connection:
            def __init__(self):self.output=bytearray()
            def makefile(self,*args):return io.BytesIO(wire)
            def sendall(self,data):self.output.extend(data)
            def settimeout(self,*args):pass
        connection=Connection();Handler(connection,('127.0.0.1',0),SimpleNamespace(service=self.service));header,data=bytes(connection.output).split(b'\r\n\r\n',1)
        self.assertEqual(int(header.split()[1]),200);self.assertFalse(json.loads(data)['models'][0]['available'])

if __name__=='__main__':unittest.main()
