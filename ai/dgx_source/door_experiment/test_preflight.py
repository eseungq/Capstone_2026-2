import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from door_experiment.preflight import audit_manifests

class PreflightTests(unittest.TestCase):
    def fixture(self, root, mutation=None):
        (root/'configs').mkdir()
        config={'manifests':{},'expected_counts':{},'constraints':'constraints.json','sha256':{}}
        for role in ('train','model_selection'):
            image=root/'data/images/Training'/f'{role}.jpg'
            image.parent.mkdir(parents=True,exist_ok=True);image.touch()
            row=dict(group_id=role,image_path=str(image),proposed_class_id='1',future_split=role,draft_action='include_representative')
            if mutation: mutation(role,row)
            name=role+'.csv'
            with (root/name).open('w') as f:
                writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader();writer.writerow(row)
            config['manifests'][role]=name;config['expected_counts'][role]={'1':1}
        (root/'constraints.json').write_text('[]')
        for name in [*config['manifests'].values(),'constraints.json']:
            config['sha256'][name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
        (root/'configs/door_visible_region_experiment_v1.json').write_text(json.dumps(config))
    def test_maps_proposed_class_without_final_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            tables,report=audit_manifests(root)
            self.assertEqual(tables['train'][0]['class_id'],1)
            self.assertFalse(report['provenance']['final_test_read'])
    def test_cross_role_group_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root,lambda role,row:row.update(group_id='same'))
            with self.assertRaises(ValueError):audit_manifests(root)
    def test_held_row_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root,lambda role,row:row.update(draft_action='hold_capture_or_label'))
            with self.assertRaises(ValueError):audit_manifests(root)
    def test_changed_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root);(root/'train.csv').write_text('changed')
            with self.assertRaises(ValueError):audit_manifests(root)
    def test_cross_role_suspected_part_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            p=root/'constraints.json';p.write_text(json.dumps([dict(duplicateGroupIds=['train','model_selection'],role='train')]))
            c=root/'configs/door_visible_region_experiment_v1.json';cfg=json.loads(c.read_text());cfg['sha256']['constraints.json']=hashlib.sha256(p.read_bytes()).hexdigest();c.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):audit_manifests(root)

class ExplicitConfigTests(unittest.TestCase):
    fixture = PreflightTests.fixture
    def test_explicit_versioned_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            old=root/'configs/door_visible_region_experiment_v1.json'
            alternate=root/'configs/locked.json';alternate.write_bytes(old.read_bytes())
            old.unlink()
            tables,report=audit_manifests(root,alternate)
            self.assertEqual(len(tables['train']),1)
            self.assertEqual(report['provenance']['config_path'],str(alternate))
    def test_changed_frozen_code_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            code=root/'execution.py';code.write_text('initial')
            p=root/'configs/door_visible_region_experiment_v1.json';cfg=json.loads(p.read_text())
            cfg['code_sha256']={'execution.py':hashlib.sha256(code.read_bytes()).hexdigest()};p.write_text(json.dumps(cfg))
            code.write_text('changed')
            with self.assertRaisesRegex(ValueError,'Frozen execution code changed'):
                audit_manifests(root)

class SmokeSelectionTests(unittest.TestCase):
    def test_balanced_deterministic_and_disjoint(self):
        from door_experiment.train import smoke_subset
        tables = {role: [dict(class_id=label, image_path=f'{role}/{label}/{i}')
                         for label in (0, 1) for i in range(40)]
                  for role in ('train', 'model_selection')}
        result = smoke_subset(tables)
        self.assertEqual(result, smoke_subset(tables))
        self.assertEqual(len(result['train']), 64)
        self.assertEqual(len(result['model_selection']), 32)
        for role, n in [('train',32), ('model_selection',16)]:
            self.assertEqual(sum(r['class_id']==1 for r in result[role]), n)
            self.assertEqual(len({r['image_path'] for r in result[role]}), 2*n)
        self.assertEqual(len(tables['train']), 80)

if __name__=='__main__':unittest.main()
