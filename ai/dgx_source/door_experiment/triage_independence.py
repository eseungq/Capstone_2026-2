"""Rank every current train/model-selection candidate; never infer identity from heuristic score."""
import base64,csv,hashlib,json,math,random
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageFilter,ImageDraw
from ai_api.rank_similarity import features,metrics
from ai_api.duplicate_groups import components

def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def load(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def fingerprint(path):
 with Image.open(path) as source:im=ImageOps.exif_transpose(source).convert('RGB')
 rgb,edge,aspect=features(im)
 pixel=hashlib.sha256(im.tobytes()).hexdigest()
 return path,dict(rgb=rgb,edge=edge,aspect=aspect,size=list(im.size),pixel_sha256=pixel,file_sha256=sha(path))
def rankkey(r):return (r['rankScore'],int(r['distance']),r['selection_image'],r['train_image'])
def main():
 root=Path(__file__).resolve().parents[1];draft=Path(load(root/'outputs/door_revision_draft/latest.json')['directory']);rows=read(draft/'all_role_visual_candidates.csv');roles=read(draft/'candidate_roles.csv');role_by_path={r['image_path']:r['future_split'] for r in roles};labels={r['image_path']:r['proposed_class_id'] for r in roles}
 out=root/'outputs/door_independence_triage'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);print('[TRIAGE OUTPUT]',out,flush=True)
 scoped=[]
 for r in rows:
  if {r['role_a'],r['role_b']}!={'train','model_selection'}:continue
  a,b=(r['image_a'],r['image_b']) if r['role_a']=='model_selection' else (r['image_b'],r['image_a'])
  ga,gb=(r['group_a'],r['group_b']) if r['role_a']=='model_selection' else (r['group_b'],r['group_a'])
  if role_by_path[a]!='model_selection' or role_by_path[b]!='train':raise ValueError('Unexpected scope')
  scoped.append(dict(selection_image=a,train_image=b,selection_group=ga,train_group=gb,distance=int(r['distance']),previous_judgment=r['previous_judgment']))
 known=[r for r in scoped if r['previous_judgment']!='UNREVIEWED'];pending=[r for r in scoped if r['previous_judgment']=='UNREVIEWED']
 paths=sorted({r[k] for r in pending for k in ['selection_image','train_image']});fps={}
 old=load(root/'ai_api/verification/audit_followup_20261016T182934_010033Z/fingerprints.json');expected={r['image_path']:r['sha256'] for r in old}
 dump(out/'status.json',dict(status='running',total_images=len(paths),final_test_read=False,training_started=False))
 cache=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  for i,(path,v) in enumerate(pool.map(fingerprint,paths),1):
   if v['file_sha256']!=expected[path]:raise ValueError('Image changed since historical visual features')
   fps[path]=v;cache.append(dict(path=path,display_size=v['size'],display_rgb_sha256=v['pixel_sha256'],file_sha256=v['file_sha256'],rgb64_b64=base64.b64encode(v['rgb'].tobytes()).decode(),edge62_b64=base64.b64encode(v['edge'].tobytes()).decode()))
   if i%250==0 or i==len(paths):print('[FULL PIXEL FEATURES]',i,'/',len(paths),flush=True)
 dump(out/'pixel_feature_cache.json',cache)
 exact=[]
 for r in pending:
  a,b=fps[r['selection_image']],fps[r['train_image']]
  r.update(metrics((a['rgb'],a['edge'],a['aspect']),(b['rgb'],b['edge'],b['aspect'])))
  r['exact_display_pixels']=a['size']==b['size'] and a['pixel_sha256']==b['pixel_sha256']
  r['label_disagreement']=labels[r['selection_image']]!=labels[r['train_image']]
  if r['exact_display_pixels']:exact.append(r)
 ranked=sorted(pending,key=rankkey);top_selection={};top_train={}
 for r in ranked:
  top_selection.setdefault(r['selection_group'],r);top_train.setdefault(r['train_group'],r)
 for r in ranked:r['mutual_best_candidate']=top_selection[r['selection_group']] is r and top_train[r['train_group']] is r
 # Fractional bands schedule review only; they are neither identity nor exclusion thresholds.
 n=len(ranked)
 for i,r in enumerate(ranked):r.update(priority_band='high' if i<math.ceil(n*.1) else 'uncertain' if i<math.ceil(n*.5) else 'lower',rank=i+1)
 dump(out/'ranked_candidates.json',ranked);dump(out/'previously_reviewed_pairs.json',known);dump(out/'exact_display_pixel_evidence.json',exact);dump(out/'best_per_selection_group.json',list(top_selection.values()))
 nodes={r[k] for r in ranked for k in ['selection_group','train_group']};comps=components(nodes,[(r['selection_group'],r['train_group']) for r in ranked]);sizes=sorted([len(c) for c in comps],reverse=True)
 # A bounded first-pass estimate: 16 high-priority diverse pairs, 4 middle + 4 lower audit samples.
 selected=[];used=set()
 for r in sorted([r for r in ranked if r['priority_band']=='high' and not r['exact_display_pixels']],key=lambda r:(not r['mutual_best_candidate'],*rankkey(r))):
  ends={r['selection_group'],r['train_group']}
  if used&ends:continue
  selected.append(dict(r,selection_reason='high_priority_mutual_or_best'));used.update(ends)
  if len(selected)==16:break
 rng=random.Random(20261030)
 for band in ['uncertain','lower']:
  options=[r for r in ranked if r['priority_band']==band and not r['exact_display_pixels']];rng.shuffle(options);added=0
  for r in options:
   ends={r['selection_group'],r['train_group']}
   if used&ends:continue
   selected.append(dict(r,selection_reason='priority_band_audit_sample'));used.update(ends);added+=1
   if added==4:break
 for i,r in enumerate(selected,1):r['caseId']=f'triage_{i:02d}'
 assert len({(r['selection_image'],r['train_image']) for r in selected})==len(selected)
 dump(out/'proposed_first_pass_24.json',selected)
 # Representative-image hold option, computed only as a conservative trade-off, never applied.
 affected={r['selection_image'] for r in ranked};held_counts=Counter(labels[p] for p in affected);remaining=[r for r in roles if r['future_split']=='model_selection' and r['image_path'] not in affected]
 bands={band:[r for r in ranked if r['priority_band']==band] for band in ['high','uncertain','lower']}
 summary=dict(status='automatic_triage_complete_no_identity_auto_decisions',sourceDraft=str(draft),sourcePairs=len(scoped),priorReviewedPairs=len(known),pendingPairs=len(pending),uniqueGroupPairs=len({tuple(sorted((r['selection_group'],r['train_group']))) for r in pending}),pixelImagesChecked=len(paths),filesChanged=0,exactDisplayPixelPairs=len(exact),bestCounterpartsBySelectionGroup=len(top_selection),mutualBestPairs=sum(r['mutual_best_candidate'] for r in ranked),reviewSchedulingComponents=len(comps),largestHeuristicComponent=sizes[0],componentTopSizes=sizes[:10],priorityBandCounts={k:len(v) for k,v in bands.items()},priorityBandScoreRanges={k:[v[0]['rankScore'],v[-1]['rankScore']] for k,v in bands.items() if v},firstPassSuggestedPairs=len(selected),firstPassComposition=dict(Counter(r['priority_band'] for r in selected)),firstPassIsCompletionGuarantee=False,uniformSamplingGuarantee=False,allCandidateHoldOption=dict(affectedValidationImages=len(affected),affectedClasses=dict(held_counts),remainingValidationImages=len(remaining),remainingClasses=dict(Counter(r['proposed_class_id'] for r in remaining)),applied=False,independenceGuaranteed=False,limitations='Remaining subset is selected by a similarity heuristic and can be easier/different; not a repaired independent score.'),sourceSHA256=sha(draft/'all_role_visual_candidates.csv'),scriptSHA256=sha(Path(__file__)),currentModelChanged=False,currentManifestsChanged=False,finalTestRead=False,reservedPixelsRead=False,trainingStarted=False,readyForTraining=False,limitations=['No candidate was declared different merely by score.','A low-priority band can contain same physical parts or duplicates.','Mutual best is a review priority, never proof of identity.','Feature search does not cover all crops/angles/physical-part identity.'])
 dump(out/'summary.json',summary);dump(out/'status.json',dict(status='completed',final_test_read=False,training_started=False));dump(root/'outputs/door_independence_triage/latest.json',dict(directory=str(out),report=str(out/'REPORT.md'),readyForTraining=False))
 print('[TRIAGE RESULT]',json.dumps(summary,ensure_ascii=False),flush=True)
 report=f'''# DOOR 유사 후보 자동 선별과 사람 검토량

## 실제 자동 처리

현재 새 초안의 학습/모델 선택 경계{len(scoped):,}쌍에서 이전 판단{len(known)}쌍을 재사용해 제외했다. 미검토{len(pending):,}쌍은 이미 서로 다른 그룹 쌍으로, 단순 중복 관계 제거만으로는 더 줄지 않는다.

관련 원본{len(paths):,}장의 파일SHA256을 재확인하고 EXIF 보정RGB 픽셀 해시·64픽셀RGB/경계·구도를 계산했다. 현재 새 초안의 학습/모델 선택 이미지만 열었으며 그 초안의 보정·정책 예약 이미지와 최종시험은 열지 않았다. RGB표시 픽셀 완전 일치{len(exact)}쌍은 별도 근거로 보존했다. 유사도만으로 사진을 자동 병합·제외하지 않았다.

검증 사진별 가장 가까운 상대1개로 검토 일정을 줄이면{len(top_selection)}개 대표 관계가 된다. 양쪽이 서로의 최우선 후보인 관계는{summary['mutualBestPairs']}쌍이다. 최우선 상대만 확인해도 다른 상대 관계가 모두 해결되는 것은 아니다.

## 왜 전부 그룹으로 묶으면 안 되는가

미검토 유사관계 그래프는{len(comps)}개 연결 묶음이며 최대{sizes[0]}개 그룹이 한 묶음으로 이어진다. 이는 연쇄적인 비슷한 표면 때문일 수 있고 같은 실물 확정 그룹이 아니다. 전체 연결 묶음을 한 부품으로 자동 간주하면 데이터 다양성과 분할 균형을 크게 해칠 수 있다.

## 사람에게 요청할 분량 제안

우선24쌍: 높은 우선순위16쌍 + 중간4쌍 + 낮은 우선순위4쌍이다. 양쪽의 그룹이 반복되지 않도록 골랐다. 높은순위는 미검토 후보의 상위10%, 중간은다음40%, 낮은순위는나머지50%로 일정상 나눴다. 이 비율과 점수 경계는 동일/다름의 판정기준이 아니다. 이번에는 새 검토 화면을 반복 생성하지 않고 대기열JSON만 준비했다.

24쌍은 전수점검 완료 약속이 아니다. 결과에 따라 같은사진이 여전히 많이 나오면 확인된 그룹 주변의관계를 더 조사하고, 낮은순위에서도 발견되면 선별규칙의 한계를 다시 검토한다. 4장씩의 점검표본은 놓침이 없다는 통계적 보증을 제공하지 않는다. 사람이 적은 사례만 본 뒤 나머지를 자동으로 다른사진 처리하지 않는다.

## 검토 부담을 줄이는 대안과 비용

모든 미검토 관계에 연결된 검증 사진을 보수적으로 보류하면 검증{len(affected)}장이 빠지고{len(remaining)}장이 남는다. 남은클래스는{dict(Counter(r['proposed_class_id'] for r in remaining))}다. 실제 적용하지 않았다. 이 방법은 일부자료를 많이 버리고 촬영조건분포를 바꿀수 있으며 남은자료 독립성도 보증하지 않으므로 모델점수 개선방법으로 쓰지 않는다. 현재모델은 이미 원래검증자료로 선택했으므로 이부분집합의 점수도 사후 독립성능이 아니다.

## 보존과 다음 판단

기존모델·현재학습CSV·새분할초안·라벨·DB·API를 바꾸지 않았다. 재학습은하지 않았다. 모든후보와픽셀특징·원본해시·정렬·이전판단을보존했다. 다음한작업은24쌍의확인방식과 결과에따른 중단/확대 기준을 정리한 검토페이지 준비다. 새 초안을 곧바로 학습진입점에 연결하지 않는다.
'''
 (out/'REPORT.md').write_text(report)
if __name__=='__main__':main()
