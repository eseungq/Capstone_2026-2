"""Validate future experiment inputs without opening reserved/test image data."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def audit_manifests(root, config_path=None):
    root = Path(root).resolve()
    config_path = Path(config_path) if config_path is not None else root / 'configs/door_visible_region_experiment_v1.json'
    if not config_path.is_absolute():
        config_path = root / config_path
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text())
    if set(config['manifests']) != {'train', 'model_selection'}:
        raise ValueError('Only train and model_selection inputs are allowed')
    for name, expected in config['sha256'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Input changed; review and version inputs: {name}')
    for name, expected in config.get('code_sha256', {}).items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen execution code changed: ' + name)
    tables, report, groups, images = {}, {}, {}, set()
    for role, name in config['manifests'].items():
        path = root / name
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        counts = Counter()
        for row in rows:
            gid = row['group_id']
            image = Path(row['image_path']).resolve()
            if gid in groups or image in images:
                raise ValueError('Repeated group or image, including across roles')
            if row['future_split'] != role or row['draft_action'] != 'include_representative':
                raise ValueError('Unexpected role or held/duplicate row')
            if row['proposed_class_id'] not in ('0', '1'):
                raise ValueError('Invalid proposed class')
            if not image.is_relative_to(root / 'data/images/Training'):
                raise ValueError('Only original Training images may enter this experiment')
            if not image.is_file():
                raise FileNotFoundError(image)
            groups[gid] = role
            images.add(image)
            counts[row['proposed_class_id']] += 1
            row['class_id'] = int(row['proposed_class_id'])
            row['quality'] = {0: '양품', 1: '불량품'}[row['class_id']]
            row['image_path'] = str(image)
        if dict(counts) != config['expected_counts'][role]:
            raise ValueError(f'Class counts changed: {role}')
        tables[role] = rows
        report[role] = dict(path=str(path), rows=len(rows), class_counts=dict(counts), sha256=config['sha256'][name])
    constraints = json.loads((root / config['constraints']).read_text())
    for c in constraints:
        ids = c['duplicateGroupIds']
        present = [g for g in ids if g in groups]
        if present and (len(present) != len(ids) or {groups[g] for g in present} != {c['role']}):
            raise ValueError('Suspected physical-part component crosses roles')
    report['provenance'] = dict(config_path=str(config_path), config=config, config_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(), final_test_read=False, reserved_images_read=False, all_visual_duplicates_resolved=False)
    return tables, report
