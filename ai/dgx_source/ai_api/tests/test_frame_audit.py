import io,tarfile,tempfile,unittest
from pathlib import Path
from ai_api.audit_frame import prefetched_images,label_info

class FrameAuditTests(unittest.TestCase):
 def test_prefetch_preserves_member_correspondence(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'fixture.tar';expected={f'frame/{i}.jpg':bytes([i])*8193 for i in range(20)}
   with tarfile.open(path,'w') as archive:
    for name,data in expected.items():
     member=tarfile.TarInfo(name);member.size=len(data);archive.addfile(member,io.BytesIO(data))
   with tarfile.open(path,'r:') as archive:actual={member.name:data for member,data in prefetched_images(archive)}
   self.assertEqual(actual,expected)
 def test_mixed_quality_is_not_silently_binarized(self):
  label=dict(images=[{}],categories=[dict(id=204,name='실링 불량')],annotations=[dict(category_id=204,attributes=dict(quality=q,part='프레임')) for q in ['양품','불량품']])
  result=label_info(label,'frame.json');self.assertIn('mixed_or_unknown_quality',result['issues'])
if __name__=='__main__':unittest.main()
