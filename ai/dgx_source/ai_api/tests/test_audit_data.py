import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from ai_api.audit_data import inspect,sha


class AuditData(unittest.TestCase):
    def test_detects_source_quality_and_size_mismatch_without_editing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);image=root/'a.png';Image.new('RGB',(20,10),'white').save(image)
            label=root/'a.json';label.write_text(json.dumps(dict(images=[dict(file_name='a.png',width=30,height=10)],
                annotations=[dict(attributes=dict(quality='不良',part='도어'),category_id=101)],categories=[dict(id=101,name='스크래치')])) )
            before=sha(image);result=inspect(dict(image_path=str(image),json_path=str(label),quality='양품',class_id='0'))
            self.assertIn('source_quality_manifest_mismatch',result['issues'])
            self.assertIn('label_image_size_mismatch',result['issues'])
            self.assertEqual(before,sha(image))
    def test_different_names_identical_content_have_same_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'first.bin';b=Path(folder)/'second.bin'
            a.write_bytes(b'identical raw image fixture');b.write_bytes(a.read_bytes())
            self.assertEqual(sha(a),sha(b));b.write_bytes(b'different');self.assertNotEqual(sha(a),sha(b))


if __name__=='__main__':unittest.main()
