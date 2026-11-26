import unittest
from ai_api.refresh_door_split import constrain, validate, scene_relation

class SplitConstraintTests(unittest.TestCase):
    def rows(self):
        return [dict(group_id=g,image_path=g+'.jpg',future_split=r) for g,r in [('a','train'),('b','model_selection'),('c','policy_development'),('d','calibration_fit')]]

    def test_transitive_suspicion_preserves_representatives_and_order_independence(self):
        rows=self.rows(); result,sets=constrain(rows,[('a','b'),('b','c')]); reverse,other=constrain(list(reversed(rows)),[('c','b'),('b','a')])
        roles={r['group_id']:r['future_split'] for r in result}
        self.assertEqual(len({roles[g] for g in 'abc'}),1)
        self.assertEqual({r['image_path'] for r in result},{r['image_path'] for r in rows})
        self.assertEqual(roles,{r['group_id']:r['future_split'] for r in reverse})
        self.assertEqual(sets,other)
        self.assertEqual(roles['d'],'calibration_fit')

    def test_unknown_or_held_endpoint_blocks_assignment(self):
        with self.assertRaises(ValueError):constrain(self.rows(),[('a','held')])

    def test_validator_rejects_crossing_and_missing_representative(self):
        rows=self.rows();groups=[dict(groupId=r['group_id'],members=[r['image_path']]) for r in rows]
        with self.assertRaises(ValueError):validate(groups,rows,rows,[('a','b')])
        with self.assertRaises(ValueError):validate(groups,rows[:-1],rows,[])
        fixed,_=constrain(rows,[('a','b')]);self.assertTrue(validate(groups,fixed,rows,[('a','b')]))

    def test_existing_scene_evidence_enters_role_constraints_without_merging(self):
        evidence={'status':'suspected_same_physical_scene_not_confirmed','evidence':[{'imagePath':'a.jpg'},{'imagePath':'c.jpg'}]}
        relation=scene_relation(evidence,{'a.jpg':'a','c.jpg':'c'});self.assertEqual(relation,('a','c'))
        result,_=constrain(self.rows(),[relation]);roles={r['group_id']:r['future_split'] for r in result}
        self.assertEqual(roles['a'],roles['c']);self.assertEqual(len(result),4)
    def test_scene_evidence_rejects_unknown_scope_and_status(self):
        valid={'status':'suspected_same_physical_scene_not_confirmed','evidence':[{'imagePath':'a.jpg'},{'imagePath':'unknown.jpg'}]}
        with self.assertRaises(ValueError):scene_relation(valid,{'a.jpg':'a'})
        with self.assertRaises(ValueError):scene_relation(dict(valid,status='automatic_duplicate'),{'a.jpg':'a','unknown.jpg':'c'})

if __name__=='__main__':unittest.main()
