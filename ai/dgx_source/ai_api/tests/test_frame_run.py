import unittest
from ai_api.prepare_frame_run import verify_review


class FrameRunValidation(unittest.TestCase):
    def setUp(self):
        self.manifest=dict(focusedSourceSha256='test',candidates=[dict(id='a',imageSha256='image')])
        self.review=dict(schema='door-framing-review-v1',focusedSourceSha256='test',candidateHashes=['image'],
            state=dict(cases=dict(a=dict(framing='전체',doorIdentity='가능',angle='허용'))))
    def test_complete_record_and_reject_unreviewed(self):
        verify_review(self.manifest,self.review)
        self.review['state']['cases']['a']['framing']='미확인'
        with self.assertRaises(ValueError):verify_review(self.manifest,self.review)
    def test_candidate_mismatch_is_rejected(self):
        self.review['candidateHashes']=['wrong']
        with self.assertRaises(ValueError):verify_review(self.manifest,self.review)


if __name__=='__main__':unittest.main()
