import unittest
from ai_api.prioritize_door_similarity import distinct_pairs,select_diverse

class SimilarityPriorityTests(unittest.TestCase):
    def row(self,a,b,score=1.0,disagree=True,roles=None):
        return dict(validationReviewUnit=a,trainReviewUnit=b,rankScore=score,proposedLabelDisagreement=disagree,validation_image=a+'.jpg',train_image=b+'.jpg',proposalRoles=roles or ['train','model_selection'],sourceCategories=['스크래치','스크래치'])
    def test_symmetric_unit_pair_collapses_without_assuming_identity(self):
        rows=[self.row('a','b',2),self.row('b','a',1),self.row('c','d',3)]
        result=distinct_pairs(rows);self.assertEqual(len(result),2);self.assertEqual(len(rows),3);self.assertEqual(result[0]['rankScore'],1)
    def test_current_label_disagreement_precedes_lower_similarity_score(self):
        rows=[self.row('a','b',.01,False),self.row('c','d',2,True)]
        self.assertTrue(select_diverse(rows,1)[0]['proposedLabelDisagreement'])
    def test_both_sides_are_disjoint_and_order_is_reproducible(self):
        rows=[self.row('a','b',1),self.row('b','c',.9),self.row('d','e',2),self.row('f','g',3,roles=['calibration_fit','policy_development'])]
        selected=select_diverse(rows,3);ends=[r[k] for r in selected for k in ['validationReviewUnit','trainReviewUnit']]
        self.assertEqual(len(ends),len(set(ends)));self.assertEqual(selected,select_diverse(list(reversed(rows)),3))

if __name__=='__main__':unittest.main()
