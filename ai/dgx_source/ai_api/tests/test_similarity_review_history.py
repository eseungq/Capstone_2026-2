import hashlib,json,tempfile,unittest
from pathlib import Path
from ai_api.similarity_review_history import load_imports

class SimilarityHistoryTests(unittest.TestCase):
    def fixture(self,folder,decision='DIFFERENT'):
        folder.mkdir(parents=True,exist_ok=True)
        queue=[dict(caseId='candidate_01',validation_image='valid.jpg',train_image='train.jpg')];qp=folder/'queue.json';qp.write_text(json.dumps(queue));qhash=hashlib.sha256(qp.read_bytes()).hexdigest()
        review=dict(schema='door-remaining-candidate-review-v1',sourceQueueSHA256=qhash,applied=False,originalsModified=False,reviewer='FIXTURE',reviewedAt='2026-10-28T00:00:00Z',records=[dict(queue[0],decision=decision,reason='fixture')]);rp=folder/'original_user_export.json';rp.write_text(json.dumps(review))
        summary=dict(originalsModified=False,splitApplied=False,queueSource=str(qp),queueSHA256=qhash,sourceReviewSHA256=hashlib.sha256(rp.read_bytes()).hexdigest(),recordCount=1);sp=folder/'summary.json';sp.write_text(json.dumps(summary));return sp,rp
    def test_multiple_batches_preserved_and_later_judgment_explicitly_wins(self):
        with tempfile.TemporaryDirectory() as temp:
            a,_=self.fixture(Path(temp)/'old');b,_=self.fixture(Path(temp)/'new','UNSURE');rows,hashes=load_imports([a,b]);self.assertEqual(rows[('valid.jpg','train.jpg')]['decision'],'UNSURE');self.assertIn(str(a),hashes);self.assertIn(str(b),hashes)
    def test_changed_preserved_export_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p,r=self.fixture(Path(temp));r.write_text('{}')
            with self.assertRaises(ValueError):load_imports([p])
    def test_modified_original_flag_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p,_=self.fixture(Path(temp));s=json.loads(p.read_text());s['originalsModified']=True;p.write_text(json.dumps(s))
            with self.assertRaises(ValueError):load_imports([p])

if __name__=='__main__':unittest.main()
