import unittest
from PIL import Image, ImageDraw
from ai_api.rank_similarity import features, metrics


class RankingTests(unittest.TestCase):
    def test_same_geometry_different_color(self):
        a=features(Image.new('RGB',(80,60),'blue'))
        self.assertEqual(metrics(a,a)['rankScore'],0)
        self.assertGreater(metrics(a,features(Image.new('RGB',(80,60),'red')))['rgbMAE64'],100)

    def test_shifted_boundary_and_aspect(self):
        image=Image.new('RGB',(80,60),'white')
        ImageDraw.Draw(image).rectangle((20,0,24,59),fill='black')
        shifted=Image.new('RGB',(80,60),'white')
        ImageDraw.Draw(shifted).rectangle((50,0,54,59),fill='black')
        self.assertGreater(metrics(features(image),features(shifted))['relativeEdgeDifference'],0.5)
        self.assertGreater(metrics(features(image),features(image.resize((60,80))))['aspectDifference'],0)


if __name__=='__main__': unittest.main()
