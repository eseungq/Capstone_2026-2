"""Audit future DOOR image labels and prioritize similarities; never train or rewrite source labels."""
import csv
import hashlib
import json
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from ai_api.duplicate_groups import ROOT,read_csv
from ai_api.prepare_experiment_draft import quality_overrides
from ai_api.similarity_review_history import load_imports


def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def write(path,rows,fields):
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def inspect(row):
    raw=Path(row['json_path']).read_bytes();label=json.loads(raw.decode('utf-8-sig'));anns=label.get('annotations',[]);cats={c['id']:c['name'] for c in label.get('categories',[])}
    qualities={a.get('attributes',{}).get('quality') for a in anns}
    parts={a.get('attributes',{}).get('part') for a in anns}
    unknown=not anns or not qualities<= {'양품','불량품'} or parts!={'도어'} or any(a.get('category_id') not in cats for a in anns)
    proposed=1 if any(a.get('attributes',{}).get('quality')=='불량품' and a.get('attributes',{}).get('part')=='도어' for a in anns) else None if unknown else 0
    return dict(image_path=row['image_path'],json_path=row['json_path'],json_sha256=hashlib.sha256(raw).hexdigest(),source_qualities=';'.join(sorted(str(x) for x in qualities)),source_annotation_categories=';'.join(sorted({cats.get(a.get('category_id'),'UNKNOWN') for a in anns})),original_class_id=int(row['class_id']),annotation_any_defect_class=proposed,source_quality_manifest_match=qualities=={row['quality']},class_mapping_match={'양품':0,'불량품':1}.get(row['quality'])==int(row['class_id']),unknown_source=unknown)


def main():
    policy=ROOT/'configs/door_image_label_policy_v1.json';pointer_path=ROOT/'ai_api/verification/latest_data_proposal.json';pointer=load(pointer_path);group_dir=ROOT/pointer['groupDirectory'];draft=ROOT/pointer['representativeDirectory'];split=ROOT/pointer['splitDirectory']
    confirm=Path(load(ROOT/'outputs/door_remaining_review_confirmation/latest.json')['output']);imported=Path(load(ROOT/'outputs/door_remaining_review_import/latest.json')['output'])
    label_review=ROOT/'ai_api/verification/label_review_import_20261017T042134_367319Z/corrected_user_review.json';rank_path=ROOT/'ai_api/verification/similarity_rank_20261016T183911_041173Z/ranked_candidates.json'
    sources=[policy,pointer_path,group_dir/'groups.json',group_dir/'summary.json',draft/'candidate_manifest.csv',draft/'summary.json',split/'summary.json',split/'candidate_roles.csv',label_review,rank_path,imported/'original_user_export.json',confirm/'confirmed_same_photo_supplemental.json',confirm/'remaining_suspected_part_relations.json',ROOT/'outputs/manifests/door_train.csv',ROOT/'outputs/manifests/door_internal_validation.csv',Path('/path/to/private-user/다운로드/도어_SwinTiny_DGX_학습_20261009/train_door_swin.py'),Path(__file__).resolve()]
    quality_files=[ROOT/Path(p) for p in pointer.get('qualityReviewFiles',[])]
    sources+=quality_files+[ROOT/'ai_api/similarity_review_history.py',ROOT/'ai_api/import_door_remaining_review.py']
    hashes={str(p):sha(p) for p in sources}
    suspected_relation_count=load(split/'summary.json')['suspectedRelations']
    for path in [group_dir/'summary.json',draft/'summary.json',split/'summary.json']:
        for name,expected in load(path)['sourceHashes'].items():
            if sha(name)!=expected:raise ValueError('Evidence changed: '+name)
    tables=[]
    for role,path,count in [('train',ROOT/'outputs/manifests/door_train.csv',11554),('internal_validation',ROOT/'outputs/manifests/door_internal_validation.csv',2039)]:
        rows=read_csv(path)
        if len(rows)!=count:raise ValueError('Manifest count changed')
        tables.extend(dict(r,originalSplit=role) for r in rows)
    if len({r['image_path'] for r in tables})!=13593:raise ValueError('Duplicate source paths')
    out=ROOT/'outputs/door_data_readiness'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    print('[READINESS OUTPUT]',out,flush=True)
    inspected=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,row in enumerate(pool.map(inspect,tables),1):
            inspected.append(row)
            if i%2000==0:print('[LABEL JSON]',i,'/ 13593',flush=True)
    groups=load(group_dir/'groups.json');member={p:g for g in groups for p in g['members']};by_path={r['image_path']:r for r in inspected};decisions={r['groupId']:r for r in load(label_review)['records']}
    overrides=quality_overrides(groups,quality_files)
    if set(decisions)&set(overrides):raise ValueError('Conflicting quality review versions')
    decisions.update(overrides)
    ledger=[]
    for g in groups:
        decision=decisions.get(g['groupId']);source_positive=any(by_path[p]['annotation_any_defect_class']==1 for p in g['members']);unknown=any(by_path[p]['unknown_source'] for p in g['members'])
        held=bool(decision and decision['decision'] in ('HOLD','CAPTURE_UNSUITABLE'))
        proposed=None if held or (unknown and not source_positive) else 1 if source_positive or (decision and decision['decision']=='DEFECT_CANDIDATE') else 0
        basis='HOLD_CAPTURE_OR_SOURCE_UNCERTAINTY' if proposed is None else 'DEFECT_CONFIRMED_GROUP_OR_REVIEW_EVIDENCE' if proposed else 'GOOD_USER_SCOPED_OBSERVATION_NOT_FULL_SCOPE_CERTIFIED' if g['groupId'] in overrides else 'GOOD_SOURCE_ONLY_FULL_DAMAGE_SCOPE_NOT_VERIFIED'
        for p in g['members']:
            r=by_path[p];ledger.append(dict(r,group_id=g['groupId'],proposed_image_class=proposed,proposal_basis=basis,original_label_change_candidate=proposed is not None and proposed!=r['original_class_id'],originals_modified=False))
    representatives=read_csv(draft/'candidate_manifest.csv');rep_disagreements=[]
    proposal={r['image_path']:r for r in ledger}
    for r in representatives:
        proposed=proposal[r['image_path']]['proposed_image_class']
        if proposed is None or proposed!=int(r['proposed_class_id']):rep_disagreements.append(dict(image_path=r['image_path'],draftClass=r['proposed_class_id'],policyClass=proposed))
    write(out/'label_proposal_ledger.csv',ledger,list(ledger[0]))
    changes=[r for r in ledger if r['original_label_change_candidate']];write(out/'label_change_candidates.csv',changes,list(ledger[0]));dump(out/'representative_policy_disagreements.json',rep_disagreements)
    # Merge chronological human evidence without treating suspicion as positive identity.
    base=ROOT/'ai_api/verification/similarity_rank_20261016T183911_041173Z/user_similarity_review.json';round2=ROOT/'ai_api/verification/split_candidate_20261017T044724_629801Z/user_similarity_review_round2.json';human={}
    for path in [base,round2]:
        rev=load(path)
        if sha(rev['source'])!=rev['sourceSHA256']:raise ValueError('Human review source changed')
        hashes[str(path)]=sha(path)
        for r in rev['records']:human[(r['validation_image'],r['train_image'])]=dict(decision='SAME_PHOTO' if r['judgment']=='user_confirmed_same_photo' else 'UNSURE',reason='previous_review')
    for r in load(imported/'original_user_export.json')['records']:human[(r['validation_image'],r['train_image'])]=dict(decision=r['decision'],reason=r['reason'])
    additional_imports=[ROOT/Path(p) for p in pointer.get('additionalSimilarityReviewImports',[])]
    extra_judgments,extra_hashes=load_imports(additional_imports)
    human.update(extra_judgments);hashes.update(extra_hashes)
    for r in load(confirm/'confirmed_same_photo_supplemental.json')['records']:human[(r['validation_image'],r['train_image'])]=dict(decision='SAME_PHOTO',reason=r['reason'])
    ranked=load(rank_path);rank_lookup={(r['validation_image'],r['train_image']):r for r in ranked};distributions={}
    for decision in ('SAME_PHOTO','DIFFERENT','POSSIBLY_SAME_PART','UNSURE'):
        values=sorted(rank_lookup[key]['rankScore'] for key,h in human.items() if h['decision']==decision and key in rank_lookup)
        distributions[decision]=dict(n=len(values),min=values[0] if values else None,median=values[len(values)//2] if values else None,max=values[-1] if values else None)
    dump(out/'human_rank_distributions.json',dict(distributions=distributions,meaning='Descriptive only; selected human sample, no independent threshold validation; no identity classifier fitted'))
    roles={r['group_id']:r['future_split'] for r in read_csv(split/'candidate_roles.csv')};remaining=[];excluded=Counter()
    for r in ranked:
        x,y=r['validation_image'],r['train_image'];gx,gy=member[x]['groupId'],member[y]['groupId'];h=human.get((x,y))
        if gx==gy:excluded['already_same_confirmed_group']+=1;continue
        if h and h['decision'] in ('SAME_PHOTO','DIFFERENT','POSSIBLY_SAME_PART'):excluded['already_reviewed_relation']+=1;continue
        if gx not in roles or gy not in roles:excluded['held_group_relation']+=1;continue
        if roles[gx]==roles[gy]:excluded['same_current_proposal_role']+=1;continue
        conflict=by_path[x]['original_class_id']!=by_path[y]['original_class_id']
        remaining.append(dict(r,validationGroup=gx,trainGroup=gy,proposalRoles=[roles[gx],roles[gy]],sourceLabelDisagreement=conflict,previousHumanDecision=h['decision'] if h else 'UNREVIEWED',status='candidate_only_not_identity_decision'))
    remaining.sort(key=lambda r:(not r['sourceLabelDisagreement'],r['rankScore'],r['validation_image'],r['train_image']))
    # Collapse repeated group-pair suggestions for review scheduling only, not data deletion.
    group_pairs=[];seen_pairs=set()
    for r in remaining:
        k=tuple(sorted((r['validationGroup'],r['trainGroup'])))
        if k not in seen_pairs:seen_pairs.add(k);group_pairs.append(r)
    shortlist=[];seen_validation=set()
    for r in group_pairs:
        if r['validationGroup'] in seen_validation:continue
        seen_validation.add(r['validationGroup']);shortlist.append(r)
    dump(out/'remaining_cross_role_candidates.json',remaining);dump(out/'best_per_group_pair.json',group_pairs);dump(out/'priority_per_validation_group.json',shortlist);dump(out/'priority_first_25.json',shortlist[:25])
    source_mismatch=sum(not r['source_quality_manifest_match'] or not r['class_mapping_match'] for r in inspected)
    summary=dict(status='audited_design_not_training_ready',policyVersion=load(policy)['policyVersion'],jsonFilesRead=len(inspected),sourceQualityClassMismatchImages=source_mismatch,unknownSourceImages=sum(r['unknown_source'] for r in inspected),sourceAnnotationCategoryImageCounts=dict(Counter(r['source_annotation_categories'] for r in inspected)),imageLabelChangeCandidates=len(changes),proposalClassCounts=dict(Counter('HOLD' if r['proposed_image_class'] is None else str(r['proposed_image_class']) for r in ledger)),sourceOnlyGoodImages=sum(r['proposal_basis']=='GOOD_SOURCE_ONLY_FULL_DAMAGE_SCOPE_NOT_VERIFIED' for r in ledger),representativePolicyDisagreements=len(rep_disagreements),rankedPairs=len(ranked),reviewSchedulingExclusions=dict(excluded),remainingCrossRolePairs=len(remaining),distinctGroupPairCandidates=len(group_pairs),priorityValidationGroups=len(shortlist),initialPriorityPairs=min(25,len(shortlist)),humanRankDistributions=distributions,sourceHashes=hashes,originalSourceFilesUnchanged=all(sha(p)==v for p,v in hashes.items()),originalLabelsModified=False,originalManifestsReplaced=False,modelChanged=False,finalTestRead=False,trainingStarted=False,calibrationFitted=False,readyForTraining=False)
    summary['knownSuspectedRelations']=suspected_relation_count
    summary['additionalHumanReviewImports']=[str(p) for p in additional_imports]
    summary['additionalHumanReviewPairs']=len(extra_judgments)
    dump(out/'summary.json',summary)
    gates=[dict(item='손상 하나라도 DEFECT 규칙',status='agreed_and_versioned'),dict(item='원본 quality와 기존 manifest 연결',status='passed' if source_mismatch==0 else 'blocked',affected=source_mismatch),dict(item='이미지 단위 정책과 대표 제안 정합성',status='passed' if not rep_disagreements else 'blocked',affected=len(rep_disagreements)),dict(item='GOOD 사진의 전체 검사 범위 무손상 근거',status='not_established',affected=summary['sourceOnlyGoodImages']),dict(item='잔여 유사 관계 및 같은 실물 독립성',status='not_established',candidatePairs=len(remaining)),dict(item='보정·정책·독립 평가 표본 충분성과 설계 잠금',status='not_established'),dict(item='기존 모델 및 원본 보존',status='passed')]
    dump(out/'training_readiness_gates.json',gates)
    report=f'''# DOOR 이미지 단위 라벨·유사 후보·차기 실험 준비\n\n## 1. 합의한 라벨 방향\n\n검사 대상 손상이 하나라도 확인되면 DEFECT다. 손상이 보이지 않는 것과 검사 범위에 손상이 없는 것은 다르다. 촬영 범위·가림·해상도가 불충분하면 GOOD 확정 대신 보류한다. 원본 JSON category 목록이나 폴더명만으로 정답을 만들지 않는다. 정책은 configs/door_image_label_policy_v1.json에 버전으로 기록했다. 실제 검사 범위는 현재 도어 손상 자료에 한정하며 보이지 않는 영역·기능적 결함까지 보장하지 않는다.\n\n기존 train_door_swin.py는 manifest의 quality/class_id를 읽어 양품=0·불량품=1 일치 여부를 검사한다. 다른 JSON/동일 사진에 있는 모든 손상을 합치는 코드가 아니다. 해당 학습 스크립트 전체를 실행하지 않았고 원본 학습 audit()도 호출하지 않았다. 최종 시험을 읽는 경로를 실행하지 않았다.\n\n원래 학습·내부 검증 13,593개 JSON을 새로 읽었고 quality/class 연결 불일치는 {source_mismatch}장이다. source JSON의 품질을 정확히 복사한 것과 이미지 전체 무손상의 정답은 별개다.\n\n현재 알려진 동일 사진 그룹·기존 수동 판단을 이미지 단위로 반영할 때 원래 class와 달라지는 후보는 {len(changes)}행이다. 보류는 {summary['proposalClassCounts'].get('HOLD',0)}행이다. 실제 원본 라벨은 수정하지 않았다. 기존 차기 대표 목록과 새 정책 제안의 클래스 불일치는 {len(rep_disagreements)}장이다. GOOD 원본 근거만 있고 전체 손상 검사 범위의 무손상까지 확인되지 않은 행은 {summary['sourceOnlyGoodImages']:,}장이다. 이 숫자가 모두 오라벨이라는 뜻은 아니다.\n\n## 2. 유사 후보 자동 정리\n\n기존 수동 판단과 순위 점수의 분포를 대조했다. 선택된 소수 표본이므로 자동 동일 판정 임계값이나 새 분류기를 학습하지 않았다. 낮은 유사도 점수로 관계를 확정하거나 높은 점수로 영구 제외하지 않았다.\n\n원래 순위 {len(ranked):,}쌍에서 확정 같은 그룹·이미 검토한 관계·보류 그룹·현재 초안상 같은 역할을 구분했다. 남은 역할 교차 후보는 {len(remaining):,}쌍이다. 반복된 그룹 쌍을 검토 일정상 1쌍으로 묶으면 {len(group_pairs):,}쌍이며, 검증 그룹별 우선 후보는 {len(shortlist):,}개다. 전체 목록을 보존하고 우선 25쌍을 별도 JSON으로 만들었다. 추가 사람 검토를 당장 요구하는 새 화면은 만들지 않았다. 같은 역할 후보도 원본에서 삭제하거나 무관계로 판정하지 않았다.\n\n정렬은 원래 라벨 충돌 후보를 먼저, 이후 기존 RGB·경계·종횡비 점수 순으로 둔다. 이는 우선순위 규칙이며 동일 사진·동일 실물 자동 판정 규칙이 아니다. 이미 알려진 실물·촬영 장면 의심 {suspected_relation_count}쌍은 기존 분할 제약으로 보존하며 이 관계에 양성 정답을 전파하지 않았다.\n\n## 3. 차기 실험 범위와 시작 조건\n\n현재 Swin-Tiny·224 전처리·클래스·0.5 기준을 기준 설계로 유지한다. 새 가중치 학습은 별도 실험에서 원래 사전학습 초기화로 시작하는 계획이며 현재 best.pt에서 이어 학습하지 않는다. 차기 역할은 학습·모델 선택·보정 학습·정책 개발로 구분하고 기존 비율은 계획 초안으로만 유지한다. 최종 시험 1,700장은 이번 작업에서 열지 않았다. 독립성 확인과 평가 프로토콜 고정 없이 사용하지 않는다.\n\n시작 전 부족한 것은 GOOD 자료의 실제 검사 범위 적합성, 미확인 유사·실물 관계를 처리하는 검토 경계, 보정·정책·독립 평가의 표본 충분성이다. 이를 숨기고 ready를 true로 바꾸지 않는다. 과거 내부 검증의 모델 선택 사용 이력은 현재 모델에 남아 있다. 재분할만으로 독립성이 복구되지 않는다.\n\n다음은 이 결과를 바탕으로 GOOD 후보의 촬영 범위·손상 가시성 점검을 기존 검토 자료와 대조해 부족한 근거를 좁히는 일이다. 모든 사진을 처음부터 다시 검토하거나 현재 DOOR API 연결을 중단하는 선행 작업으로 확대하지 않는다.\n\n모델 성능·판정 결과 변경 없음. 실행 환경 변경 없음. 재현성 관리: 정책 버전·현재 JSON 해시·전체 제안 원장·변경 후보·유사 관계 우선순위·학습 준비 조건을 새 폴더에 보존했다.\n'''
    (out/'REPORT.md').write_text(report)
    dump(ROOT/'outputs/door_data_readiness/latest.json',dict(output=str(out),report=str(out/'REPORT.md'),readyForTraining=False))
    print('[READINESS REPORT]',out/'REPORT.md',flush=True)

if __name__=='__main__':main()
