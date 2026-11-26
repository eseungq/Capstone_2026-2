"""Create a future-only split proposal preserving duplicate and suspected-part boundaries."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from ai_api.duplicate_groups import ROOT, read_csv, components
from ai_api.prepare_split_candidate import allocate, ROLES, WEIGHTS


def load(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,data):Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def constrain(baseline, relations):
    by_group={r['group_id']:r for r in baseline}
    if len(by_group)!=len(baseline):raise ValueError('Duplicate representatives')
    endpoints={g for a,b in relations for g in (a,b)}
    if endpoints-set(by_group):raise ValueError('Suspected relation includes held or unknown group')
    sets=components(endpoints,relations)
    target=Counter(r['future_split'] for r in baseline);current=target.copy();assigned={g:r['future_split'] for g,r in by_group.items()}
    # Retain the original stratified allocation where possible. Do not separate a constraint to hit exact ratios.
    for items in sets:
        old=Counter(assigned[g] for g in items)
        def cost(role):
            after=current.copy();after.subtract(old);after[role]+=len(items)
            return (len(items)-old[role],sum((after[r]-target[r])**2 for r in ROLES),ROLES.index(role))
        role=min(ROLES,key=cost);current.subtract(old);current[role]+=len(items)
        for gid in items:assigned[gid]=role
    result=[dict(r,future_split=assigned[r['group_id']]) for r in baseline]
    return result,sets


def validate(groups, candidates, rows, relations):
    lookup={r['group_id']:r for r in candidates}
    if len(lookup)!=len(candidates) or len({r['image_path'] for r in candidates})!=len(candidates):raise ValueError('Duplicate assignment')
    if {r['image_path'] for r in rows}!={r['image_path'] for r in candidates}:raise ValueError('Coverage mismatch')
    membership={g['groupId']:set(g['members']) for g in groups}
    for gid,r in lookup.items():
        if gid not in membership or r['image_path'] not in membership[gid] or r['future_split'] not in ROLES:raise ValueError('Invalid assignment')
    for a,b in relations:
        if a not in lookup or b not in lookup or lookup[a]['future_split']!=lookup[b]['future_split']:raise ValueError('Suspected-part boundary crossed')
    return True


def scene_relation(evidence,member):
    if evidence.get('status')!='suspected_same_physical_scene_not_confirmed':raise ValueError('Unknown scene evidence status')
    rows=evidence.get('evidence',[])
    if len(rows)!=2 or any(r.get('imagePath') not in member for r in rows):raise ValueError('Scene relation outside known images')
    return tuple(member[r['imagePath']] for r in rows)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--group-dir',type=Path,required=True);p.add_argument('--draft-dir',type=Path,required=True);p.add_argument('--confirmation-dir',type=Path,required=True);p.add_argument('--seed',type=int,default=20261017);p.add_argument('--scene-evidence',type=Path,action='append',default=[]);a=p.parse_args()
    group_dir=a.group_dir.resolve();draft=a.draft_dir.resolve();confirmation=a.confirmation_dir.resolve()
    sources=[group_dir/'groups.json',group_dir/'grouped_manifest.csv',group_dir/'summary.json',draft/'candidate_manifest.csv',draft/'all_images_ledger.csv',draft/'summary.json',confirmation/'remaining_suspected_part_relations.json',confirmation/'confirmed_same_photo_supplemental.json',ROOT/'outputs/manifests/door_train.csv',ROOT/'outputs/manifests/door_internal_validation.csv',Path(__file__).resolve(),ROOT/'ai_api/prepare_split_candidate.py']
    hashes={str(p):sha(p) for p in sources}
    for summary in [load(group_dir/'summary.json'),load(draft/'summary.json')]:
        for path,expected in summary['sourceHashes'].items():
            if sha(path)!=expected:raise ValueError('Source evidence changed: '+path)
    groups=load(group_dir/'groups.json');rows=read_csv(draft/'candidate_manifest.csv');meta={r['image_path']:r for r in read_csv(group_dir/'grouped_manifest.csv')};member={x:g['groupId'] for g in groups for x in g['members']}
    if any(r['future_split'] for r in rows):raise ValueError('Representative draft already assigned')
    relations=[];suspects=load(confirmation/'remaining_suspected_part_relations.json')['records']
    for r in suspects:
        if r['decision']!='POSSIBLY_SAME_PART':raise ValueError('Expected suspected relation')
        relations.append((member[r['validation_image']],member[r['train_image']]))
    scene_sources=[]
    for path in a.scene_evidence:
        evidence=load(path);relations.append(scene_relation(evidence,member))
        for row in evidence['evidence']:
            if sha(row['imagePath'])!=row['fileSHA256']:raise ValueError('Scene image changed')
        hashes[str(path.resolve())]=sha(path);scene_sources.append(str(path.resolve()))
    categories={path:r['categories'] for path,r in meta.items()}
    baseline=allocate(rows,categories,a.seed);assigned,sets=constrain(baseline,relations)
    reverse,reverse_sets=constrain(allocate(list(reversed(rows)),categories,a.seed),list(reversed(relations)))
    if assigned!=reverse or sets!=reverse_sets:raise ValueError('Input order changes result')
    validate(groups,assigned,rows,relations)
    original={r['group_id']:r for r in baseline};changes=[dict(groupId=r['group_id'],before=original[r['group_id']]['future_split'],after=r['future_split']) for r in assigned if r['future_split']!=original[r['group_id']]['future_split']]
    candidate_ids={r['group_id'] for r in assigned};ledger=read_csv(draft/'all_images_ledger.csv');held={r['group_id'] for r in ledger if r['draft_action']=='hold_capture_or_label'}
    if candidate_ids|held!={g['groupId'] for g in groups} or candidate_ids&held:raise ValueError('Held coverage invalid')
    if len(ledger)!=13593 or len({r['image_path'] for r in ledger})!=13593:raise ValueError('Original ledger coverage invalid')
    by_id={r['group_id']:r['future_split'] for r in assigned}
    image_roles={path:by_id.get(g['groupId'],'HOLD') for g in groups for path in g['members']}
    for g in groups:
        if len({image_roles[path] for path in g['members']})!=1:raise ValueError('Known duplicate group crossed roles')
    confirmed=load(confirmation/'confirmed_same_photo_supplemental.json')
    for r in confirmed['records']:
        if image_roles[r['train_image']]!=image_roles[r['validation_image']]:raise ValueError('Confirmed same photo crossed roles')
    ranked_path=ROOT/'ai_api/verification/similarity_rank_20261016T183911_041173Z/ranked_candidates.json';ranked=load(ranked_path);hashes[str(ranked_path)]=sha(ranked_path)
    suspect_pairs={tuple(sorted((r['train_image'],r['validation_image']))) for r in suspects}
    review_path=Path(load(ROOT/'outputs/door_remaining_review_import/latest.json')['output'])/'original_user_export.json';review=load(review_path);hashes[str(review_path)]=sha(review_path)
    different_pairs={tuple(sorted((r['train_image'],r['validation_image']))) for r in review['records'] if r['decision']=='DIFFERENT'}
    pending=[]
    for pair in ranked:
        x,y=pair['validation_image'],pair['train_image'];key=tuple(sorted((x,y)))
        if member[x]==member[y] or key in suspect_pairs or key in different_pairs:continue
        if image_roles[x]!='HOLD' and image_roles[y]!='HOLD' and image_roles[x]!=image_roles[y]:pending.append(dict(pair,status='unresolved_heuristic_candidate_not_confirmed_duplicate',proposalRoles=[image_roles[x],image_roles[y]]))
    out=ROOT/'outputs/door_split_refresh'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    for name,items in [('candidate_roles.csv',assigned)]+[(role+'.csv',[r for r in assigned if r['future_split']==role]) for role in ROLES]:
        with (out/name).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(assigned[0]));w.writeheader();w.writerows(items)
    constraints=[dict(constraintId='suspected_part_'+hashlib.sha256('\n'.join(items).encode()).hexdigest(),duplicateGroupIds=items,role=by_id[items[0]],evidence='suspected_physical_part_or_scene_not_confirmed_photo_duplicate') for items in sets]
    dump(out/'suspected_part_constraints.json',constraints);dump(out/'changes_from_unconstrained_baseline.json',changes);dump(out/'remaining_cross_role_candidates.json',pending)
    distribution=Counter((r['future_split'],r['proposed_class_id'],r['source_categories']) for r in assigned)
    with (out/'role_class_category_distribution.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['future_split','proposed_class_id','source_categories','images']);w.writerows([(*k,v) for k,v in sorted(distribution.items())])
    counts=dict(Counter(r['future_split'] for r in assigned));target=dict(Counter(r['future_split'] for r in baseline))
    summary=dict(status='validated_future_proposal_not_frozen',groupDirectory=str(group_dir),representativeDirectory=str(draft),sourceHashes=hashes,seed=a.seed,planningWeights=dict(zip(ROLES,WEIGHTS)),representatives=len(rows),inputImages=len(ledger),heldGroups=len(held),knownDuplicateGroupCrossings=0,suspectedRelations=len(relations),suspectedConstraintComponents=len(sets),suspectedPartRoleCrossings=0,missingImages=0,duplicateRepresentatives=0,inputOrderInvariant=True,baselineTargets=target,roles=counts,roleDeviations={role:counts.get(role,0)-target.get(role,0) for role in ROLES},movedFromUnconstrainedBaseline=len(changes),remainingHeuristicCrossRolePairs=len(pending),originalSourcesUnchanged=all(sha(p)==v for p,v in hashes.items()),originalManifestsReplaced=False,originalLabelsModified=False,trainingStarted=False,calibrationFitted=False,policyThresholdChanged=False,finalTestRead=False,readyForTraining=False)
    if not summary['originalSourcesUnchanged']:raise ValueError('Sources changed during execution')
    summary['additionalSceneEvidenceSources']=scene_sources
    dump(out/'summary.json',summary)
    report=f'''# DOOR 차기 분할 초안 갱신\n\n현재 모델·원본 목록에 적용하지 않는 차기 실험 초안이다. 14번 동일 사진 확정을 반영한 최신 그룹의 대표 목록을 사용하고, 실물·촬영 장면 의심 {len(relations)}쌍을 별도 역할 제약으로 적용했다. 추가 촬영 장면 근거 {len(scene_sources)}개를 포함한다. 의심 사진은 중복 사본으로 제거하지 않고 각각 대표를 유지했다.\n\n| 역할 | 기존 설계 비율 | 기본 목표 | 제약 반영 초안 | 차이 |\n|---|---:|---:|---:|---:|\n'''
    for role,w in zip(ROLES,WEIGHTS):report+=f'|{role}|{w/2:g}%|{target[role]}|{counts.get(role,0)}|{counts.get(role,0)-target[role]:+d}|\n'
    report+=f'''\n대표 {len(rows):,}장, 보류 {len(held)}그룹. 원본 {len(ledger):,}행 전체는 대표·중복 사본·보류 기록으로 추적한다. 의심 제약을 지키기 위해 기본 층화 배정에서 대표 {len(changes)}장의 후보 역할을 이동했다. 비율은 이전 설계 초안의 계획값이며 통계적 충분성이나 최종 합의가 아니다.\n\n## 실제 확인\n\n- 알려진 같은 사진 그룹의 역할 교차 0\n- 실물·촬영 장면 의심 {len(relations)}쌍의 역할 교차 0\n- 대표 중복·누락 0, 보류 그룹과 포함 그룹 중첩 0\n- 원본 및 근거 파일 해시 유지\n- 입력 순서를 뒤집어도 같은 배정\n- 14번의 모델 선택/정책 개발 분리 문제 해소\n\n## 아직 확인되지 않은 부분\n\n추가 유사도 후보 중 이 초안의 역할을 넘는 관계가 {len(pending):,}쌍 남는다. 이는 확정 중복 수가 아니다. 알려진 제약 교차 0만으로 전체 자료 독립성을 주장하지 않는다. 7~10번 판단 근거 미입력과 구도·차종·배경 위주의 실물 의심 판단 한계도 남아 있다. 라벨 충돌 검토의 DEFECT 후보 7개는 차기 이미지 단위 라벨 제안이며 원본 정답 변경이 아니다. 촬영 부적합 보류 3그룹을 모든 근접 사진 제외 규칙으로 확대하지 않는다.\n\n현재 best.pt는 이 자료에 학습·모델 선택으로 이미 노출됐다. 새 분할만으로 현재 모델의 보정·정책·평가 자료가 독립적으로 바뀌지 않는다. 새 실험은 별도 승인과 데이터 설계 확정이 필요하며 기존 best.pt에서 이어 학습하지 않는 계획을 검토해야 한다. 최종 시험 1,700장은 읽지 않았고 독립성도 여기서 검증하지 않았다.\n\n모델 성능·판정 변경 없음. 실행 환경 변경 없음. 재현성 관리로 초안 CSV·제약·해시·분포·검사 결과를 새 버전으로 보존했다. GPU 학습·보정·정책 임계값 산정은 실행하지 않았다. 이 초안은 DOOR 개발 API 연결을 막는 선행 조건이 아니다.\n'''
    (out/'REPORT.md').write_text(report)
    dump(ROOT/'outputs/door_split_refresh/latest.json',dict(output=str(out),report=str(out/'REPORT.md'),readyForTraining=False))
    print(json.dumps(dict(output=str(out),**summary),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
