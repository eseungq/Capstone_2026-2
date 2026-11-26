import unittest
from ai_api.focused_cam import roi_to_input,controls,matched_control,validate_roi


class FocusedGeometry(unittest.TestCase):
    def test_roi_respects_padding_and_pixel_area(self):
        rect,valid=roi_to_input([.25,.25,.5,.5],[400,200])
        self.assertEqual(valid,(0,56,224,168));self.assertEqual(rect,(56,84,112,112))
        candidates=controls(rect,valid)
        self.assertEqual(candidates,controls(rect,valid))
        for x,y,r,b in candidates:
            self.assertEqual((r-x,b-y),(56,28))
            self.assertTrue(r<=rect[0] or x>=rect[2] or b<=rect[1] or y>=rect[3])
            self.assertTrue(valid[0]<=x<r<=valid[2] and valid[1]<=y<b<=valid[3])
    def test_invalid_and_unmatchable_roi(self):
        for box in ([0,0,0,1],[-1,0,1,1],[0,0,float('nan'),1]):
            with self.assertRaises(ValueError):roi_to_input(box,[400,200])
        rect,valid=roi_to_input([0,0,1,1],[400,200])
        with self.assertRaises(ValueError):controls(rect,valid)
    def test_human_control_equal_size_and_no_overlap(self):
        rect=(0,56,56,84);valid=(0,56,224,168)
        control=matched_control(rect,valid,[.75,.5])
        self.assertEqual((control[2]-control[0],control[3]-control[1]),(56,28))
        with self.assertRaises(ValueError):matched_control(rect,valid,[.125,.125])
        with self.assertRaises(ValueError):matched_control(rect,valid,[1,1])
    def test_v2_accepts_observed_non_defect_regions(self):
        import hashlib,json
        from pathlib import Path
        p=Path('/path/to/private/validated-project/ai_api/verification/diagnose_20261016T174308_543960Z/diagnostic.json')
        if not p.exists():self.skipTest('Host diagnostic not present')
        source=json.loads(p.read_text());cases=[]
        for s in source['samples']:
            if s['id'] in ('sample_08','sample_09','sample_13'):
                cases.append(dict(id=s['id'],imageSha256=s['imageSha256'],regions=[dict(type='structure',box=[.1,.1,.2,.2],controlCenter=[.7,.7],controlContent='flat')]))
        payload=dict(schema='door-cam-regions-v2',sourceReport=str(p),sourceReportSha256=hashlib.sha256(p.read_bytes()).hexdigest(),cases=cases)
        result=validate_roi(payload)
        self.assertEqual(len(result),3)
        self.assertTrue(all(s['_regionType']=='structure' for s,_,_ in result))
        self.assertEqual({s['savedKind'] for s,_,_ in result},{'FP','FN'})


if __name__=='__main__':unittest.main()
