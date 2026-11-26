import random
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from frame_model.audit_similarity import HashIndex,segments,rank_pairs
from ai_api.audit_data import difference_hash

class SimilarityTests(unittest.TestCase):
    def test_ranking_distinguishes_pixel_exact_from_flat_hash_collision(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary);(out/'thumbs').mkdir()
            rows=[]
            for ident,role,color,pixel_hash,label in [('valid','model_selection','black','same','1'),('train_same','train','black','same','0'),('train_other','train','white','other','1')]:
                Image.new('RGB',(64,64),color).save(out/'thumbs'/f'{ident}.png')
                rows.append({'image_id':ident,'role':role,'type':'fixture','class_id':label,'group_id':ident,'width':64,'height':64,'dhash64':'0','dual_hash128':'0','average_hash64':'0','display_pixel_sha256':pixel_hash})
            result=rank_pairs(rows,out)
            self.assertEqual(result['candidate_pairs'],2)
            self.assertEqual(result['exact_display_pixel_pairs'],1)
            self.assertEqual(result['cross_source_quality_pairs'],1)
            import json
            gallery=json.loads((out/'gallery_candidates.json').read_text())
            self.assertTrue(gallery[0]['exact_display_pixels'])
            self.assertFalse(gallery[1]['exact_display_pixels'])

    def test_multi_index_never_misses_threshold_neighbors(self):
        rng=random.Random(42)
        for bits,radius in [(64,8),(128,12)]:
            values=[rng.getrandbits(bits) for _ in range(100)];index=HashIndex(values,bits,radius)
            for n in range(20):
                base=values[n];query=base
                for bit in rng.sample(range(bits),radius):query^=1<<bit
                expected={i for i,v in enumerate(values) if (query^v).bit_count()<=radius}
                self.assertTrue(expected<=index.query(query));self.assertIn(n,index.query(query))
                found={i for i in index.query(query) if (query^values[i]).bit_count()<=radius};self.assertEqual(found,expected)
    def test_same_pixels_and_vertical_structure(self):
        im=Image.new('RGB',(80,60));im.putdata([(x*3%256,y*4%256,(x+y)%256) for y in range(60) for x in range(80)])
        self.assertEqual(difference_hash(im),difference_hash(im.copy()))
        self.assertEqual(len(segments(128,12)),13)
        self.assertEqual(sum(mask.bit_count() for _,mask in segments(128,12)),128)

if __name__=='__main__':unittest.main()
