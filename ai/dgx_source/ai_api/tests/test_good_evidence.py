import unittest
from ai_api.audit_door_good_evidence import note_evidence

class GoodEvidenceTests(unittest.TestCase):
    def test_negative_note_does_not_become_positive_by_word_defect(self):
        self.assertEqual(note_evidence('근접사진, 결함 없음'),'written_no_defect_observation_not_full_scope_certification')
    def test_written_positive_is_review_flag_not_final_class(self):
        self.assertEqual(note_evidence('근접 사진, 결함 확인 가능'),'written_defect_observation_requires_label_reconciliation')
    def test_mixed_text_is_not_good(self):
        self.assertEqual(note_evidence('결함 없음, 다른 부분은 결함 확인 가능'),'conflicting_free_text_requires_reconciliation')
    def test_capture_acceptance_does_not_certify_quality(self):
        self.assertEqual(note_evidence('구도 좋음 사용하기 괜찮음'),'capture_only_or_insufficient_quality_evidence')

if __name__=='__main__':unittest.main()
