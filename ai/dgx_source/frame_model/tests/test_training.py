import unittest
from pathlib import Path
import json
from frame_model.train import manifests, metrics, subset
from frame_model.check import ROOT,read_image

class PreparationTests(unittest.TestCase):
    def test_confusion_metrics(self):
        rows=[{'actual':a,'predicted':p} for a,p in [(1,1),(0,0),(0,1),(1,0),(1,1)]]
        result=metrics(rows)
        self.assertEqual([result[k] for k in ['tp','tn','fp','fn']],[2,1,1,1])
        self.assertAlmostEqual(result['f1'],2/3)
        self.assertIsNone(metrics([])['f1'])
    def test_smoke_selection_and_source_read(self):
        prep=Path(json.loads((ROOT/'frame_model/latest_preparation.json').read_text())['preparation'])
        _,tables=manifests(prep)
        train=subset(tables['train'],16);val=subset(tables['model_selection'],8)
        self.assertEqual((len(train),len(val)),(128,64))
        self.assertEqual({r['image_id'] for r in train},{r['image_id'] for r in subset(list(reversed(tables['train'])),16)})
        self.assertFalse({r['group_id'] for r in train}&{r['group_id'] for r in val})
        display,padded=read_image(train[0])
        self.assertEqual(padded.size,(224,224));self.assertEqual(display.mode,'RGB')

if __name__=='__main__': unittest.main()
