import unittest
from ai_api.prepare_review import orient_point,polygons,USER_OBSERVATIONS


class ReviewGeometry(unittest.TestCase):
    def test_exif_transforms_boundary_coordinates(self):
        expected={1:(20,10),2:(80,10),3:(80,40),4:(20,40),5:(10,20),6:(40,20),7:(40,80),8:(10,80)}
        for orientation,point in expected.items():
            self.assertEqual(orient_point(20,10,100,50,orientation),point)
    def test_flat_nested_segmentation_and_bbox(self):
        flat=[1,2,3,4,5,6]
        for segmentation in (flat,[flat]):
            shapes,kind=polygons(dict(segmentation=segmentation))
            self.assertEqual(kind,'segmentation');self.assertEqual(shapes,[[(1,2),(3,4),(5,6)]])
        shapes,kind=polygons(dict(segmentation={'counts':'RLE'},bbox=[1,2,3,4]))
        self.assertEqual(kind,'bbox');self.assertEqual(shapes,[[(1,2),(4,2),(4,6),(1,6)]])
        self.assertEqual(polygons(dict(bbox=[0,0,-1,2]))[1],'unsupported')
    def test_observations_follow_image_identity(self):
        self.assertEqual(len(USER_OBSERVATIONS),2)
        self.assertTrue(all(k.endswith('.jpg') for k in USER_OBSERVATIONS))


if __name__=='__main__':unittest.main()
