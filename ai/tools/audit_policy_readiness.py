"""Audit frozen role metadata only. Does not fit calibration or release a policy."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

VERSION='door-swin-tiny-e02-28a2dd1cb40b-dev'
CONFIG='configs/door_visible_region_experiment_v3_10epochs.json'
EXPECTED_CONFIG_SHA256='2ba6443ab8095d81280ca115230d156f219ef54b2fb2f8fff10f4c32bd121114'


def audit(root,config_path=None):
    root=Path(root).resolve();config_path=Path(config_path) if config_path else root/CONFIG
    cfg=json.loads(config_path.read_text())
    paths={**cfg['manifests'],**cfg['reserved_manifests']}
    tables={};roles={};errors=[]
    if hashlib.sha256(config_path.read_bytes()).hexdigest()!=EXPECTED_CONFIG_SHA256:errors.append('Frozen experiment configuration changed')
    metadata_hash_checks=[]
    for name,expected in cfg['sha256'].items():
        match=hashlib.sha256((root/name).read_bytes()).hexdigest()==expected
        metadata_hash_checks.append(dict(relativePath=name,hashMatches=match))
        if not match:errors.append('Frozen metadata changed: '+name)
    for role in ('train','model_selection','calibration_fit','policy_development'):
        p=root/paths[role];actual=hashlib.sha256(p.read_bytes()).hexdigest();expected=cfg['sha256'][paths[role]]
        if actual!=expected:errors.append('manifest hash changed: '+role)
        with p.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        if any(row['future_split']!=role or row['proposed_class_id'] not in ('0','1') for row in rows):errors.append('role/label mismatch: '+role)
        if len({row['group_id'] for row in rows})!=len(rows):errors.append('repeated group: '+role)
        tables[role]=rows;roles[role]=dict(rows=len(rows),classCounts=dict(Counter(row['proposed_class_id'] for row in rows)),manifestSHA256=actual,hashMatches=actual==expected)
    overlaps=[]
    for i,a in enumerate(tables):
        for b in list(tables)[i+1:]:
            groups=len({x['group_id'] for x in tables[a]}&{x['group_id'] for x in tables[b]})
            paths_count=len({x['image_path'] for x in tables[a]}&{x['image_path'] for x in tables[b]})
            overlaps.append(dict(roles=[a,b],sharedGroupIds=groups,sharedImagePaths=paths_count))
            if groups or paths_count:errors.append('known role overlap: '+a+'/'+b)
    assignment={row['group_id']:role for role,rows in tables.items() for row in rows}
    constraints=json.loads((root/cfg['constraints']).read_text());violations=[]
    for constraint in constraints:
        present={assignment[g] for g in constraint['duplicateGroupIds'] if g in assignment}
        if len(present)>1 or present and present!={constraint['role']}:violations.append(constraint['constraintId'])
    if violations:errors.append('known risk component crosses roles')
    n=int(roles['policy_development']['classCounts'].get('1',0))
    reasons=[]
    if not cfg.get('independence_established',False):reasons.append('Unreviewed similarity/physical-part independence remains unresolved; metadata non-overlap is not proof of independence.')
    reasons.append('policy_development is a development role; threshold selection on this set is not an independent final policy test.')
    reasons.append('Accepted risk target, confidence rule and release/adjustment criteria must be supplied before ready policy registration.')
    return dict(schema='e02-policy-readiness-audit-v1',createdAt=datetime.now(timezone.utc).isoformat(),modelVersion=VERSION,
                metadataChecksPassed=not errors,errors=errors,roles=roles,overlaps=overlaps,metadataHashChecks=metadata_hash_checks,
                knownConstraintsChecked=len(constraints),knownConstraintViolations=len(violations),
                independenceEstablished=cfg.get('independence_established',False),
                remainingHeuristicCandidateCounts=cfg.get('remainingHeuristicCandidateCounts',{}),
                zeroMissOneSided95UpperIllustration=1-.05**(1/n) if n else None,
                boundAssumptions='Fixed policy and independent representative defect observations; assumptions NOT certified here.',
                zeroMissRequiredDefectsIllustration={str(goal):math.ceil(math.log(.05)/math.log(1-goal)) for goal in [.005,.01,.05]},
                releaseReady=False,calibratorVersion=None,passThreshold=None,validatedMin=None,validatedMax=None,
                releaseBlockers=reasons,imagesRead=False,finalTestRead=False,calibrationFitted=False,productionModified=False,
                notAnAdminPolicyRegistrationPayload=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--config',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report=audit(a.root,a.config);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(output=str(a.output),metadataChecksPassed=report['metadataChecksPassed'],releaseReady=False),ensure_ascii=False))
    if report['errors']:raise SystemExit(2)


if __name__=='__main__':main()
