import unittest
from ai_api.duplicate_groups import components, validate


class GroupTests(unittest.TestCase):
    def test_transitive_and_singleton(self):
        self.assertEqual(components(['d','c','a','b'],[('a','b'),('b','c')]),[['a','b','c'],['d']])
        with self.assertRaises(ValueError): components(['a'],[('a','outside')])

    def test_split_and_conflict_guards(self):
        groups=[dict(groupId='g',members=['a','b'],labelConflict=False),
                dict(groupId='h',members=['c'],labelConflict=True)]
        self.assertEqual(validate(groups,[dict(image_path=p,split='train') for p in ['a','b']])['status'],'passed')
        bad=validate(groups,[dict(image_path='a',split='train'),dict(image_path='b',split='validation'),dict(image_path='c',split='train')])
        self.assertEqual({r['type'] for r in bad['errors']},{'group_crosses_splits','unresolved_label_conflict'})
        self.assertEqual(validate(groups,[])['status'],'failed')


if __name__=='__main__': unittest.main()
