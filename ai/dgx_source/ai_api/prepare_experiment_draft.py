"""Create representative-only future data draft, with no split assignment or training."""
import csv
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from ai_api.duplicate_groups import read_csv, dump

ROOT=Path(__file__).resolve().parents[1]
GROUP_DIR=ROOT/'ai_api/verification/duplicate_groups_20261017T033939_279895Z'
REVIEW=ROOT/'ai_api/verification/label_review_import_20261017T042134_367319Z/corrected_user_review.json'
COORDS=ROOT/'ai_api/verification/data_audit_20261016T181906_711013Z/priority_review/coordinate_evidence.json'


def representative(members, rows, dimensions, coordinate_issues, proposed_class):
    # Source label agreement is preferred only for explicitly reviewed groups.
    # Resolution is a reproducible tie-break, not proof of better framing.
    return min(members,key=lambda p:(int(rows[p]['class_id'])!=proposed_class,
                                    p in coordinate_issues,-dimensions[p][0]*dimensions[p][1],p))


def validate_draft(groups, candidates, ledger, held):
    expected={g['groupId']:set(g['members']) for g in groups}
    assert len(candidates)==len(expected)-len(held)
    assert len({r['group_id'] for r in candidates})==len(candidates)
    assert {r['group_id'] for r in candidates}==set(expected)-set(held)
    assert len(ledger)==sum(map(len,expected.values()))
    assert len({r['image_path'] for r in ledger})==len(ledger)
    for r in ledger:
        assert r['image_path'] in expected[r['group_id']]
        assert r['future_split']==''
    for r in candidates:
        assert r['image_path'] in expected[r['group_id']]
        assert r['future_split']=='' and r['proposed_class_id'] in (0,1)
    selected={r['image_path'] for r in candidates}
    assert {r['image_path'] for r in ledger if r['draft_action']=='include_representative'}==selected


def quality_overrides(groups,review_files):
    membership={g['groupId']:set(g['members']) for g in groups};result={}
    for path in review_files:
        document=json.loads(path.read_text())
        if document.get('schema')!='door-image-quality-clarification-v1' or document.get('applied') is not False:raise ValueError('Invalid quality clarification')
        if hashlib.sha256(Path(document['source']).read_bytes()).hexdigest()!=document['sourceSHA256']:raise ValueError('Quality clarification source changed')
        for row in document['records']:
            gid=row['groupId'];image=row['imagePath'];decision=row['decision'];cls=row['proposedClass']
            if gid not in membership or image not in membership[gid] or gid in result:raise ValueError('Unknown or repeated quality group')
            if decision not in ('GOOD_CANDIDATE','DEFECT_CANDIDATE') or cls!={'GOOD_CANDIDATE':0,'DEFECT_CANDIDATE':1}[decision]:raise ValueError('Quality decision/class mismatch')
            for key,digest_key in [('imagePath','imageSHA256'),('jsonPath','jsonSHA256')]:
                if hashlib.sha256(Path(row[key]).read_bytes()).hexdigest()!=row[digest_key]:raise ValueError('Quality evidence bytes changed')
            result[gid]=dict(row,qualityReviewSource=str(path.resolve()))
    return result


def main():
    global GROUP_DIR
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group-dir',type=Path,default=GROUP_DIR)
    parser.add_argument('--quality-review',type=Path,action='append',default=[])
    args=parser.parse_args();GROUP_DIR=args.group_dir.resolve()
    group_path=GROUP_DIR/'groups.json';manifest=GROUP_DIR/'grouped_manifest.csv'
    sources=[group_path,manifest,REVIEW,COORDS,ROOT/'outputs/manifests/door_train.csv',ROOT/'outputs/manifests/door_internal_validation.csv']+args.quality_review
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    previous=json.loads((GROUP_DIR/'summary.json').read_text())
    for p in sources[4:6]:
        if hashes[str(p)]!=previous['sourceHashes'][str(p)]:raise ValueError('Original manifest changed')
    groups=json.loads(group_path.read_text());rows={r['image_path']:r for r in read_csv(manifest)}
    review=json.loads(REVIEW.read_text());decisions={r['groupId']:r for r in review['records']}
    if review['applied'] is not False:raise ValueError('Expected unapplied review proposals')
    if review['sourceSHA256']!=hashlib.sha256(Path(review['source']).read_bytes()).hexdigest():
        raise ValueError('Review group evidence changed')
    assert set(decisions)=={g['groupId'] for g in groups if g['labelConflict']}
    overrides=quality_overrides(groups,args.quality_review)
    if set(overrides)&set(decisions):raise ValueError('Existing conflict decision needs explicit reconciliation before replacement')
    decisions.update(overrides)
    coordinates={r['image_path']:r for r in json.loads(COORDS.read_text())['records']}
    dimensions={}
    for p in rows:
        with Image.open(p) as im: dimensions[p]=im.size
    candidates=[];ledger=[];held=[]
    for g in groups:
        gid=g['groupId'];decision=decisions.get(gid)
        if decision and decision['decision'] in ('CAPTURE_UNSUITABLE','HOLD'):
            held.append(gid);selected=None;proposed=None
        else:
            proposed=decision['proposedClass'] if decision else int(rows[g['members'][0]]['class_id'])
            assert proposed in (0,1)
            if not decision:assert {int(rows[p]['class_id']) for p in g['members']}=={proposed}
            selected=representative(g['members'],rows,dimensions,coordinates,proposed)
        for p in g['members']:
            r=rows[p]
            action='hold_capture_or_label' if selected is None else 'include_representative' if p==selected else 'omit_duplicate_copy'
            record=dict(group_id=gid,image_path=p,json_path=r['json_path'],original_split=r['originalSplit'],
                        original_class_id=int(r['class_id']),proposed_class_id=proposed,future_split='',
                        draft_action=action,representative_path=selected or '',
                        label_basis='user_target_quality_clarification' if gid in overrides else 'user_review_corrected' if decision else 'inherited_source_unreviewed',
                        review_decision=decision['decision'] if decision else '',review_reason=decision['reason'] if decision else '',
                        coordinate_review_needed=p in coordinates,width=dimensions[p][0],height=dimensions[p][1],
                        quality_review_source=overrides.get(gid,{}).get('qualityReviewSource',''),
                        quality_evidence_scope=overrides.get(gid,{}).get('evidenceScope',''),
                        quality_full_scope_certified=overrides.get(gid,{}).get('fullScopeCertified',False))
            ledger.append(record)
            if p==selected:candidates.append(record)
    validate_draft(groups,candidates,ledger,held)
    output=ROOT/'ai_api/verification'/('experiment_draft_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    for name,records in [('candidate_manifest.csv',candidates),('all_images_ledger.csv',ledger),
                         ('omitted_or_held.csv',[r for r in ledger if r['draft_action']!='include_representative'])]:
        with (output/name).open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(ledger[0]));writer.writeheader();writer.writerows(records)
    dump(output/'held_groups.json',[g for g in groups if g['groupId'] in held])
    unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[str(p)] for p in sources)
    assert unchanged
    summary=dict(status='draft_validated',sourceHashes=hashes,scriptSHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 inputImages=len(rows),candidateRepresentatives=len(candidates),heldGroups=len(held),
                 actionCounts=dict(Counter(r['draft_action'] for r in ledger)),
                 proposedClasses=dict(Counter(r['proposed_class_id'] for r in candidates)),
                 reviewedDefectGroups=sum(d['decision']=='DEFECT_CANDIDATE' for d in decisions.values()),
                 qualityClarificationGroups=len(overrides),
                 coordinateFlaggedRepresentatives=sum(r['coordinate_review_needed'] for r in candidates),
                 originalSourceHashesUnchanged=unchanged,finalTestUsed=False,splitAssigned=False,trainingStarted=False,
                 originalLabelsModified=False,checks='one representative per non-held group; complete ledger; no split assigned',
                 representativeRule='matching reviewed class, no known coordinate issue, greater pixel count, lexical path',
                 limitations='Only known duplicates grouped. Inherited labels remain unreviewed. Group selection does not establish independent evaluation.')
    dump(output/'summary.json',summary);print(json.dumps(dict(output=str(output),**summary),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
