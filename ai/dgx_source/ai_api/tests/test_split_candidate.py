import unittest
from collections import Counter
from ai_api.prepare_split_candidate import allocate


class AllocationTests(unittest.TestCase):
    def test_counts_order_invariance_and_rare_strata(self):
        rows=[dict(group_id=str(i),image_path=str(i),proposed_class_id=str(i%2)) for i in range(101)]
        categories={str(i):'rare' if i==0 else 'common' for i in range(101)}
        a=allocate(rows,categories,20261017)
        self.assertEqual(a,allocate(rows[::-1],categories,20261017))
        self.assertEqual(Counter(r['future_split'] for r in a),{'train':71,'model_selection':15,'calibration_fit':8,'policy_development':7})
        self.assertEqual(len({r['image_path'] for r in a}),101)

    def test_repeated_group_rejected(self):
        with self.assertRaises(ValueError):allocate([dict(group_id='x'),dict(group_id='x')],{},1)


if __name__=='__main__':unittest.main()
