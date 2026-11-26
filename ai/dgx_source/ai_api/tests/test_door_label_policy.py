import json
import tempfile
import unittest
from pathlib import Path
from ai_api.prepare_door_data_readiness import inspect

class DoorImageLabelTests(unittest.TestCase):
    def inspect_label(self,annotations):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'source.json';p.write_text(json.dumps({'categories':[{'id':101,'name':'스크래치'},{'id':102,'name':'외관 손상'}],'annotations':annotations}))
            return inspect(dict(json_path=str(p),image_path='fixture.jpg',quality='양품',class_id='0'))
    def annotation(self,quality,category=101):return dict(category_id=category,attributes=dict(part='도어',quality=quality))
    def test_one_defect_overrides_good_annotations(self):
        result=self.inspect_label([self.annotation('양품'),self.annotation('불량품',102)])
        self.assertEqual(result['annotation_any_defect_class'],1)
    def test_category_catalog_is_not_positive_evidence(self):
        result=self.inspect_label([self.annotation('양품')]);self.assertEqual(result['annotation_any_defect_class'],0)
        self.assertEqual(result['source_annotation_categories'],'스크래치')
    def test_empty_or_unknown_quality_is_not_good(self):
        for annotations in [[],[self.annotation('미확인')]]:
            result=self.inspect_label(annotations);self.assertIsNone(result['annotation_any_defect_class']);self.assertTrue(result['unknown_source'])
    def test_other_part_is_not_door_good(self):
        a=self.annotation('양품');a['attributes']['part']='프레임'
        self.assertIsNone(self.inspect_label([a])['annotation_any_defect_class'])

if __name__=='__main__':unittest.main()
