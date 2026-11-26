import unittest
from ai_api.search_scratch_scope import diverse


class DiversityTests(unittest.TestCase):
    def test_excluded_anchor_and_opposite_hash(self):
        rows=[dict(image_path=p) for p in ['a','b','c']]
        fps={'a':dict(dhash=0),'b':dict(dhash=1),'c':dict(dhash=(1<<64)-1)}
        selected=diverse(rows,fps,1,{'a'})
        self.assertEqual([r['image_path'] for r in selected],['c'])

    def test_input_order_and_unique_paths(self):
        rows=[dict(image_path=p) for p in ['c','b','a']]
        fps={p:dict(dhash=h) for p,h in [('a',0),('b',3),('c',7)]}
        self.assertEqual(diverse(rows,fps,3),diverse(rows[::-1],fps,3))
        self.assertEqual(len({r['image_path'] for r in diverse(rows,fps,5)}),3)


if __name__=='__main__':unittest.main()
