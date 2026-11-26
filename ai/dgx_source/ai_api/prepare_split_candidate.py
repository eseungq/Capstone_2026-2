"""Versioned group-based split proposal; no replacement of live manifests."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from ai_api.duplicate_groups import read_csv, dump

ROOT=Path(__file__).resolve().parents[1]
DRAFT=ROOT/'ai_api/verification/experiment_draft_20261017T044029_304767Z'
GROUPS=ROOT/'ai_api/verification/duplicate_groups_20261017T033939_279895Z'
RANK=ROOT/'ai_api/verification/similarity_rank_20261016T183911_041173Z'
ROLES=('train','model_selection','calibration_fit','policy_development')
WEIGHTS=(140,30,15,15)


def allocate(rows, categories, seed):
    if len({r['group_id'] for r in rows})!=len(rows):raise ValueError('Repeated group')
    target={role:len(rows)*weight//200 for role,weight in zip(ROLES,WEIGHTS)}
    for role in sorted(ROLES,key=lambda r:(-(len(rows)*WEIGHTS[ROLES.index(r)]%200),ROLES.index(r)))[:len(rows)-sum(target.values())]:target[role]+=1
    strata=defaultdict(list)
    for row in rows:strata[(str(row['proposed_class_id']),categories[row['image_path']])].append(row)
    quotas={};remainders={};allocated=Counter()
    for key,items in sorted(strata.items()):
        quotas[key]={r:len(items)*w//200 for r,w in zip(ROLES,WEIGHTS)}
        remainders[key]=len(items)-sum(quotas[key].values())
        allocated.update(quotas[key])
    while sum(remainders.values()):
        choices=[(len(strata[k])*WEIGHTS[ROLES.index(r)]/200-quotas[k][r],k,r)
                 for k in sorted(strata) if remainders[k] for r in ROLES if allocated[r]<target[r]]
        _,key,role=max(choices,key=lambda v:(v[0],v[1],-ROLES.index(v[2])))
        quotas[key][role]+=1;allocated[role]+=1;remainders[key]-=1
    result=[]
    for key,items in sorted(strata.items()):
        ordered=sorted(items,key=lambda r:hashlib.sha256(f'{seed}:{r["group_id"]}'.encode()).hexdigest())
        start=0
        for role in ROLES:
            count=quotas[key][role]
            result.extend(dict(r,future_split=role,source_categories=key[1]) for r in ordered[start:start+count]);start+=count
    assert Counter(r['future_split'] for r in result)==target
    return result


def main():
    global DRAFT,GROUPS
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--seed',type=int,default=20261017)
    parser.add_argument('--draft-dir',type=Path,default=DRAFT)
    parser.add_argument('--group-dir',type=Path,default=GROUPS)
    parser.add_argument('--supplemental-review',type=Path,action='append',default=[])
    args=parser.parse_args();DRAFT=args.draft_dir.resolve();GROUPS=args.group_dir.resolve()
    source=DRAFT/'candidate_manifest.csv';rows=read_csv(source)
    expected=json.loads((DRAFT/'summary.json').read_text())['candidateRepresentatives']
    if len(rows)!=expected or any(r['future_split'] for r in rows):raise ValueError('Unexpected candidate input')
    metadata={r['image_path']:r for r in read_csv(GROUPS/'grouped_manifest.csv')}
    categories={p:r['categories'] for p,r in metadata.items()}
    candidates=allocate(rows,categories,args.seed)
    assert {r['image_path'] for r in candidates}=={r['image_path'] for r in rows}
    assert candidates==allocate(list(reversed(rows)),categories,args.seed)
    groups=json.loads((GROUPS/'groups.json').read_text());group_roles={r['group_id']:r['future_split'] for r in candidates}
    image_roles={p:group_roles[g['groupId']] for g in groups if g['groupId'] in group_roles for p in g['members']}
    for g in groups:assert len({image_roles[p] for p in g['members'] if p in image_roles})<=1
    review=json.loads((RANK/'user_similarity_review.json').read_text())
    reviewed={(r['validation_image'],r['train_image']) for r in review['records']}
    supplemental_confirmed=[]
    for path in args.supplemental_review:
        extra=json.loads(path.read_text())
        if hashlib.sha256(Path(extra['source']).read_bytes()).hexdigest()!=extra['sourceSHA256']:raise ValueError('Review source changed')
        reviewed.update((r['validation_image'],r['train_image']) for r in extra['records'] if r['judgment']=='user_confirmed_same_photo')
        supplemental_confirmed.extend(r for r in extra['records'] if r['judgment']=='user_confirmed_same_photo')
    for r in supplemental_confirmed:
        if r['validation_image'] in image_roles and r['train_image'] in image_roles:
            assert image_roles[r['validation_image']]==image_roles[r['train_image']]
    pending=[]
    for pair in json.loads((RANK/'ranked_candidates.json').read_text()):
        a,b=pair['validation_image'],pair['train_image']
        if (a,b) in reviewed:continue
        if a in image_roles and b in image_roles and image_roles[a]!=image_roles[b]:
            pending.append(dict(**pair,validationFutureRole=image_roles[a],trainFutureRole=image_roles[b],status='unreviewed_similarity_candidate_not_confirmed_duplicate'))
    output=ROOT/'ai_api/verification'/('split_candidate_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    for name,items in [('candidate_roles.csv',candidates)]+[(r+'.csv',[x for x in candidates if x['future_split']==r]) for r in ROLES]:
        with (output/name).open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(candidates[0]));writer.writeheader();writer.writerows(items)
    dump(output/'pending_cross_role_candidates.json',pending)
    queue=[];seen=set()
    for p in pending:
        if p['validation_image'] not in seen:queue.append(p);seen.add(p['validation_image'])
        if len(queue)==30:break
    dump(output/'next_review_queue.json',queue)
    counts=Counter((r['future_split'],r['proposed_class_id'],r['source_categories']) for r in candidates)
    with (output/'role_distribution.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream);writer.writerow(['future_split','proposed_class_id','source_categories','images']);writer.writerows([(*k,v) for k,v in sorted(counts.items())])
    sources=[source,GROUPS/'groups.json',GROUPS/'grouped_manifest.csv',RANK/'ranked_candidates.json',RANK/'user_similarity_review.json']+args.supplemental_review
    dump(output/'summary.json',dict(status='proposal_validated_not_frozen',seed=args.seed,roles=dict(Counter(r['future_split'] for r in candidates)),
         knownGroupCrossings=0,missingImages=0,duplicateRepresentatives=0,inputOrderInvariant=True,
         pendingUnreviewedCrossRolePairs=len(pending),nextReviewQueue=len(queue),
         sourceHashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
         scriptSHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         finalTestUsed=False,existingManifestsReplaced=False,trainingStarted=False,calibrationFitted=False,readyForTraining=False,
         limitations='Known group crossings zero does not establish independence; unreviewed similarities and inherited labels remain. Ratios are planning targets, not statistical adequacy evidence.'))
    print('[SPLIT CANDIDATE]',output);print('roles',Counter(r['future_split'] for r in candidates));print('unreviewed cross-role candidate pairs',len(pending))


if __name__=='__main__':main()
