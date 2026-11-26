"""CPU-only candidate binding tests, never GPU inference claims."""
import hashlib,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from ai_api.e02_engine import CandidateEngine,validate_candidate
from prototype.engine import Engine
from ai_api.e02_service import CandidateService
from ai_api import backend_contract

class CandidateBindingTests(unittest.TestCase):
 def test_exact_existing_inference_and_cam_reused(self):
  self.assertIs(CandidateEngine.predict,Engine.predict)
  self.assertIs(CandidateEngine.tensor,Engine.tensor)
  self.assertIs(CandidateEngine.explain,Engine.explain)
 def test_manifest_is_new_strict_candidate(self):
  m,run,cfg=validate_candidate()
  self.assertEqual(m['expectedEpoch'],2);self.assertEqual(cfg['config']['epochs'],10)
  self.assertNotIn('outputs/training/',str(run))
  self.assertFalse(m['backendModelVersionRegistered'])
 def test_inventory_tracks_candidate_bytes_and_version(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'candidate.pt';p.write_bytes(b'CPU fixture, not model weights');digest=hashlib.sha256(p.read_bytes()).hexdigest();version='CPU_FIXTURE_E02'
   engine=SimpleNamespace(metadata={'model_version':version,'model_sha256':digest,'model_name':'fixture'},model=SimpleNamespace(training=False),checkpoint_path=p,expected_checkpoint_sha256=digest)
   service=CandidateService(engine,version,lambda _:b'',Path(d)/'runtime',response_profile=backend_contract.PROFILE)
   self.assertTrue(service.model_inventory()['models'][0]['available'])
   p.write_bytes(b'changed');self.assertFalse(service.model_inventory()['models'][0]['available'])
   with self.assertRaises(ValueError):CandidateService(engine,'wrong',lambda _:b'',Path(d)/'other')
if __name__=='__main__':unittest.main()
