"""Future-only DOOR representatives and split; inspect every role boundary from cached hashes."""
import argparse,csv,hashlib,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from ai_api.prepare_experiment_draft import representative
from ai_api.prepare_split_candidate import allocate,ROLES
from ai_api.refresh_door_split import constrain,validate
from ai_api.similarity_review_history import load_imports

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def write(p,rows,fields=None):
 with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def key(a,b):return tuple(sorted((a,b)))
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence-dir',type=Path);args=parser.parse_args()
 root=Path(__file__).resolve().parents[1];proposal=load(root/'ai_api/verification/latest_data_proposal.json');imp=args.evidence_dir.resolve() if args.evidence_dir else Path(load(root/'outputs/door_triage_import/latest.json')['directory']);isummary=load(imp/'summary.json')
 if sha(imp/'original_user_export.json')!=isummary['sourceReviewSHA256']:raise ValueError('Review bytes changed')
 groups=load(imp/'future_groups.json');old_to_new=load(imp/'old_to_future_group.json');ledger_path=root/proposal['representativeDirectory']/'all_images_ledger.csv';oldledger=read(ledger_path);by_path={r['image_path']:r for r in oldledger};membership={p:g['groupId'] for g in groups for p in g['members']}
 if len(membership)!=13593 or set(membership)!=set(by_path):raise ValueError('Source ledger coverage differs')
 old_metadata_path=root/proposal['groupDirectory']/'grouped_manifest.csv';meta={r['image_path']:r for r in read(old_metadata_path)};dimensions={p:(int(r['width']),int(r['height'])) for p,r in by_path.items()};coordinate={p for p,r in by_path.items() if r['coordinate_review_needed']=='True'}
 candidates=[];ledger=[];held=[];unresolved=[]
 for g in groups:
  members=g['members'];prior=[by_path[p] for p in members];classes={r['proposed_class_id'] for r in prior};hold=any(r['draft_action']=='hold_capture_or_label' for r in prior)
  if len(classes)>1 and not hold:unresolved.append(g['groupId']);hold=True
  if hold:selected=None;label='';held.append(g['groupId'])
  else:
   label=next(iter(classes))
   if label not in ('0','1'):raise ValueError('Unresolved class')
   selected=representative(members,meta,dimensions,coordinate,int(label))
  for p in members:
   row=dict(by_path[p],group_id=g['groupId'],proposed_class_id=label,future_split='',representative_path=selected or '',draft_action='hold_capture_or_label' if hold else ('include_representative' if p==selected else 'omit_duplicate_copy'))
   ledger.append(row)
   if p==selected:candidates.append(row)
 if unresolved:raise ValueError('New label conflict needs review: '+str(unresolved))
 constraints=load(imp/'future_suspected_part_constraints.json');relations=[(c['duplicateGroupIds'][0],g) for c in constraints for g in c['duplicateGroupIds'][1:]]
 categories={p:r['categories'] for p,r in meta.items()};base=allocate(candidates,categories,20261017);assigned,sets=constrain(base,relations);validate(groups,assigned,candidates,relations)
 reversed_rows,reversed_sets=constrain(allocate(list(reversed(candidates)),categories,20261017),list(reversed(relations)))
 if assigned!=reversed_rows or sets!=reversed_sets:raise ValueError('Order changes assignment')
 roles={r['group_id']:r['future_split'] for r in assigned};paths={p:roles.get(g,'HOLD') for p,g in membership.items()};checks=load(imp/('all_confirmed_same_photo_links.json' if (imp/'all_confirmed_same_photo_links.json').exists() else 'confirmed_current_cross_role_pairs.json'))
 for r in checks:
  if paths[r['validation_image']]!=paths[r['train_image']]:raise ValueError('Confirmed same photo still crosses')
 if len({r['image_path'] for r in assigned})!=len(candidates):raise ValueError('Representative coverage differs')
 for row in ledger:row['future_split']=paths[row['image_path']]
 previous_roles={r['image_path']:r['future_split'] for r in read(root/proposal['splitDirectory']/'candidate_roles.csv')}
 for row in assigned:row['previous_run_role']=previous_roles.get(row['image_path'],'not_selected_representative')
 out=root/'outputs/door_revision_draft'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);print('[REVISION OUTPUT]',out,flush=True)
 dump(out/'groups.json',groups);dump(out/'held_groups.json',[g for g in groups if g['groupId'] in held]);dump(out/'suspected_part_constraints.json',[dict(c,role=roles[c['duplicateGroupIds'][0]]) for c in constraints])
 write(out/'all_images_ledger.csv',ledger);write(out/'candidate_roles.csv',assigned)
 for role in ROLES:write(out/(role+'.csv'),[r for r in assigned if r['future_split']==role])
 # Reuse historical features only; no final-test or reserved image decoding.
 fp_path=root/'ai_api/verification/audit_followup_20261016T182934_010033Z/fingerprints.json';fp={r['image_path']:r for r in load(fp_path)}
 for r in assigned:
  if r['image_path'] not in fp or 'dhash' not in fp[r['image_path']]:raise ValueError('Missing historical visual features')
 hash_audit_path=Path(load(root/'outputs/door_independence/latest.json')['directory'])/'current_file_hashes.json';checked={r['image_path']:r['sha256'] for r in load(hash_audit_path)}
 for p,digest in checked.items():
  if fp[p]['sha256']!=digest:raise ValueError('Cached image lineage differs')
 # Reuse all direct human judgments, accounting for pair direction and remapped groups.
 history={}
 sources=[root/'ai_api/verification/similarity_rank_20261016T183911_041173Z/user_similarity_review.json',root/'ai_api/verification/split_candidate_20261017T044724_629801Z/user_similarity_review_round2.json']
 for source in sources:
  obj=load(source)
  if sha(obj['source'])!=obj['sourceSHA256']:raise ValueError('Historical queue changed')
  for r in obj['records']:history[key(r['validation_image'],r['train_image'])]=r['judgment']
 summaries=[root/'outputs/door_remaining_review_import/20261027T185447_467114Z/summary.json',*[root/p for p in proposal.get('additionalSimilarityReviewImports',[])],Path(load(root/'outputs/door_independence_import/latest.json')['directory'])/'summary.json',Path(load(root/'outputs/door_triage_import/latest.json')['directory'])/'summary.json']
 imported,_=load_imports(summaries)
 for (a,b),v in imported.items():history[key(a,b)]=v['decision']
 auditpointer=load(root/'outputs/door_independence/latest.json');user=load(root/auditpointer['confirmationDirectory']/'user_confirmation.json')
 for r in user['records']:history[key(r['validation_image'],r['train_image'])]=r['judgment']
 for r in load(imp/'decisions.json')['records']:history[key(r['validation_image'],r['train_image'])]=r['decision']
 group_history={key(membership[a],membership[b]):v for (a,b),v in history.items()}
 unit={g:g for g in roles}
 for c in constraints:
  for g in c['duplicateGroupIds']:unit[g]=c['constraintId']
 counts=Counter();compared=Counter();decisions=Counter();affected=defaultdict(set);pool=[(r,fp[r['image_path']]['dhash']) for r in assigned];fields=['role_a','role_b','image_a','image_b','group_a','group_b','distance','previous_judgment','within_suspected_unit']
 with (out/'all_role_visual_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for i,(a,ha) in enumerate(pool):
   for b,hb in pool[i+1:]:
    if a['future_split']==b['future_split']:continue
    boundary='/'.join(sorted((a['future_split'],b['future_split'])));compared[boundary]+=1;distance=(ha^hb).bit_count()
    if distance>8:continue
    judgment=history.get(key(a['image_path'],b['image_path']),group_history.get(key(a['group_id'],b['group_id']),'UNREVIEWED'))
    sameunit=unit[a['group_id']]==unit[b['group_id']]
    w.writerow(dict(role_a=a['future_split'],role_b=b['future_split'],image_a=a['image_path'],image_b=b['image_path'],group_a=a['group_id'],group_b=b['group_id'],distance=distance,previous_judgment=judgment,within_suspected_unit=sameunit));counts[boundary]+=1;decisions[judgment]+=1;affected[a['future_split']].add(a['image_path']);affected[b['future_split']].add(b['image_path'])
   if i%2000==0 or i+1==len(pool):print('[ALL ROLE BOUNDARIES]',i+1,'/',len(pool),flush=True)
 expected={ '/'.join(sorted((a,b))):sum(r['future_split']==a for r in assigned)*sum(r['future_split']==b for r in assigned) for i,a in enumerate(ROLES) for b in ROLES[i+1:]}
 if dict(compared)!=expected:raise ValueError('Role-pair coverage gap')
 digest_roles=defaultdict(set)
 for r in assigned:digest_roles[fp[r['image_path']]['sha256']].add(r['future_split'])
 exact=sum(len(v)>1 for v in digest_roles.values());assert exact==0
 distribution={role:dict(Counter(r['proposed_class_id'] for r in assigned if r['future_split']==role)) for role in ROLES}
 source_files=[ledger_path,old_metadata_path,fp_path,imp/'summary.json',imp/'future_groups.json',imp/'old_to_future_group.json',imp/'future_suspected_part_constraints.json',root/'configs/door_image_label_policy_v2.json',Path(__file__).resolve()]
 report=dict(status='future_split_validated_visual_independence_open',sourceImport=str(imp),representatives=len(assigned),original_images=len(ledger),held_groups=len(held),held_images=sum(r['draft_action']=='hold_capture_or_label' for r in ledger),omitted_duplicate_copies=sum(r['draft_action']=='omit_duplicate_copy' for r in ledger),role_counts=dict(Counter(r['future_split'] for r in assigned)),role_class_counts=distribution,known_duplicate_group_crossings=0,known_suspected_part_crossings=0,confirmed_same_photo_links_checked=len(checks),cached_exact_file_crossings=exact,role_boundaries_checked=len(compared),comparison_counts=dict(compared),visual_candidate_counts=dict(counts),candidate_judgments=dict(decisions),candidate_affected_images_by_role={k:len(v) for k,v in affected.items()},input_order_invariant=True,original_data_or_manifests_modified=False,current_api_model_changed=False,training_started=False,final_test_read=False,reserved_image_pixels_read=False,independence_established=False,current_trained_model_valid_for_new_reserved_roles=False,hash_verification_scope='11236 files rehashed in previous audit; other representatives use historical SHA/dHash without reopening reserved image pixels',source_hashes={str(p):sha(p) for p in source_files},planning_seed=20261017)
 dump(out/'summary.json',report);dump(root/'outputs/door_revision_draft/latest.json',dict(directory=str(out),report=str(out/'REPORT.md'),trainingReady=False,independenceEstablished=False));print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
 (out/'REPORT.md').write_text(f'''# DOOR 중복 반영 대표·분할 초안

확정 같은 사진{len(checks)}개 연결과 기록된 실물·장면 의심{len(constraints)}개 제약 묶음을 반영했다. 대표{len(assigned):,}장, 보류{len(held)}그룹, 중복 사본{report['omitted_duplicate_copies']}장이다. 원본13593행은 ledger로 모두 추적한다. 기존 수동 라벨 수정·촬영 보류·07/11품질 확인을 이전 원장에서 그대로 승계했으며 다른 실물 의심 관계로 불량 라벨을 전파하지 않았다.

## 초안 분포

|역할|GOOD|DEFECT|합계|
|---|---:|---:|---:|
'''+''.join(f'|{role}|{distribution[role].get("0",0)}|{distribution[role].get("1",0)}|{report["role_counts"][role]}|\n' for role in ROLES)+f'''
## 경계 검사

확정 사진 그룹과 의심 제약의 역할 교차0, 입력 순서를 뒤집어도 배정 동일, 대표 중복·누락 없음이다. 새 역할6개 조합 전체에 대해 비교 수가 역할별 곱과 일치하는지 확인했다. 과거와 달리 옛 train/train·internal/internal 관계도 검색에서 빠지지 않는다. 모든 역할 경계의dHash거리8이하 후보는CSV로 보존했다. 캐시된 동일 파일SHA256 교차0건이다.

이 검사는 원래 학습/내부검증13593장의 과거 시각 지문을 재사용한다. 이번 독립성 감사에서 재계산된11236개 해시와 대응은 확인했지만, 보정·정책 예약 이미지 픽셀을 새로 열지는 않았다. 최종시험1700장은 접근하지 않았다. 지문상 후보는 동일 사진 확정 건수가 아니며 원본 크롭·각도·동일 실물 관계를 놓칠 수 있다.

## 아직 독립성을 확정할 수 없는 이유

전체 경계를 검색했어도 미검토 유사 후보가 남아 있다. 알려진 같은 사진 연결만 반영해 독립성이 해결됐다고 하지 않는다. 이전 사람판단과 구별되는 고위험 후보부터 점검한 뒤 다음실험을 결정한다. 기존 최고14회차 모델은 옛 역할에 노출되어 있으므로 이 새 분할의 보정·정책 예약 자료를 현재 모델에 대한 독립 자료로 취급할 수 없다.

현재 API·학습manifest·학습설정·모델은 그대로다. 이 초안은 학습진입점에 연결하지 않았고 재학습·보정·AUTO_PASS 기준 설정도 하지 않았다. 새 학습 전에는 원본 재확인과 버전 고정, 잔여 위험에 대한 판단이 필요하다.
''')
if __name__=='__main__':main()
