import unittest
from collections import Counter
from ai_api.prepare_framing import pick


class FramingSelection(unittest.TestCase):
    def test_disjoint_balanced_deterministic_candidates(self):
        rows=[dict(image_path=f'/tmp/{kind}/{i}.jpg',kind=kind) for kind in ('TP','TN','FP','FN') for i in range(12)]
        excluded={r['image_path'] for r in rows[::3]}
        result=pick(rows,excluded)
        self.assertEqual(result,pick(rows,excluded))
        self.assertEqual(Counter(r['kind'] for r in result),dict(TP=4,TN=4,FP=4,FN=4))
        self.assertFalse({r['image_path'] for r in result}&excluded)
        self.assertTrue(all('framing' not in r for r in result))


if __name__=='__main__':unittest.main()
