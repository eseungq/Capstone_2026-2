import hashlib,json,tempfile,unittest
from pathlib import Path
from ai_api.prepare_experiment_draft import quality_overrides

class QualityClarificationTests(unittest.TestCase):
    def fixture(self,folder):
        a=folder/'a.jpg';b=folder/'b.jpg';c=folder/'c.jpg';label=folder/'a.json';source=folder/'source.json'
        for p in [a,b,c,label,source]:p.write_text(p.name)
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        groups=[dict(groupId='g1',members=[str(a),str(b)]),dict(groupId='g2',members=[str(c)])]
        row=dict(groupId='g1',imagePath=str(a),imageSHA256=sha(a),jsonPath=str(label),jsonSHA256=sha(label),decision='DEFECT_CANDIDATE',proposedClass=1,reason='user confirmed door damage')
        review=folder/'review.json';document=dict(schema='door-image-quality-clarification-v1',source=str(source),sourceSHA256=sha(source),applied=False,records=[row]);review.write_text(json.dumps(document));return groups,review,document,a
    def test_explicit_target_quality_only_updates_confirmed_photo_group(self):
        with tempfile.TemporaryDirectory() as temp:
            groups,p,d,_=self.fixture(Path(temp));result=quality_overrides(groups,[p]);self.assertEqual(set(result),{'g1'});self.assertEqual(result['g1']['proposedClass'],1)
    def test_changed_source_image_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            groups,p,d,a=self.fixture(Path(temp));a.write_text('changed')
            with self.assertRaises(ValueError):quality_overrides(groups,[p])
    def test_foreign_group_or_class_mismatch_rejected(self):
        for change in [dict(groupId='g2'),dict(proposedClass=0)]:
            with tempfile.TemporaryDirectory() as temp:
                groups,p,d,a=self.fixture(Path(temp));d['records'][0].update(change);p.write_text(json.dumps(d))
                with self.assertRaises(ValueError):quality_overrides(groups,[p])

if __name__=='__main__':unittest.main()
