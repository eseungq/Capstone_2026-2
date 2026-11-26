"""Prepare a 12-pair neighborhood review, reusing the previous working offline UI."""
import csv,hashlib,html,json
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
from ai_api.import_door_remaining_review import validate

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 root=Path(__file__).resolve().parents[1];near=Path(load(root/'outputs/door_group_neighborhoods/latest.json')['directory']);summary=load(near/'summary.json');draft=Path(summary['sourceDraft']);selected=load(near/'next_priority_pairs_proposal.json');previous=Path(load(root/'outputs/door_triage_review/latest.json')['directory']);template=previous/'index.html';prior=load(previous/'review_queue.json')
 if len(selected)!=12:raise ValueError('Expected exactly 12 proposals')
 expected={r['image_path']:r['sha256'] for r in load(root/'ai_api/verification/audit_followup_20261016T182934_010033Z/fingerprints.json')};prior_keys={tuple(sorted((r['validation_image'],r['train_image']))) for r in prior};queue=[]
 for i,r in enumerate(selected,1):
  if r['previous_judgment']!='UNREVIEWED' or {r['role_a'],r['role_b']}!={'train','model_selection'}:raise ValueError('Reviewed or out-of-scope row')
  vi,ti,vg,tg=(r['image_a'],r['image_b'],r['group_a'],r['group_b']) if r['role_a']=='model_selection' else (r['image_b'],r['image_a'],r['group_b'],r['group_a'])
  if tuple(sorted((vi,ti))) in prior_keys:raise ValueError('Repeats previous 24-pair review')
  queue.append(dict(r,caseId=f'candidate_{i:02d}',displayNumber=i+0,validation_image=vi,train_image=ti,validationGroup=vg,trainGroup=tg,proposalRoles=['model_selection','train'],priorityMeaning='confirmed-group neighborhood review only; not identity evidence'))
 if len({r[k] for r in queue for k in ['validationGroup','trainGroup']})!=24:raise ValueError('Repeated groups')
 out=root/'outputs/door_neighborhood_review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);dump(out/'review_queue.json',queue)
 cards=[];contact=Image.new('RGB',(1000,220*12),'white');draw=ImageDraw.Draw(contact)
 for i,r in enumerate(queue):
  cards.append(f'<article id="case_{i+1}"><h3>주변 관계 검토 {i+1}/12</h3><p>왼쪽: 새 초안 모델 선택 / 오른쪽: 새 초안 학습</p><div class="pair">');draw.text((8,i*220+4),f'NEIGHBOR {i+1}: selection / train',fill='black')
  for j,key in enumerate(['validation_image','train_image']):
   path=Path(r[key])
   if sha(path)!=expected[str(path)]:raise ValueError('Original changed')
   with Image.open(path) as im:display=ImageOps.exif_transpose(im).convert('RGB')
   preview=display.copy();preview.thumbnail((1000,760));name=f'pair_{i+1:02d}_{j}.jpg';preview.save(out/name,quality=92);preview.thumbnail((490,185));contact.paste(preview,(j*500,i*220+25))
   cards.append(f'<a target="_blank" rel="noopener" href="{html.escape(path.as_uri(),quote=True)}"><img loading="lazy" src="{name}"><p>사진 클릭: 원본 크게 보기</p></a>')
  cards.append(f'</div><label for="decision_{i}">판단 </label><select id="decision_{i}"><option value="UNREVIEWED">미검토</option><option value="SAME_PHOTO">같은 사진</option><option value="POSSIBLY_SAME_PART">같은 실물·다른 촬영 의심</option><option value="DIFFERENT">다른 사진·동일 실물 근거 없음</option><option value="UNSURE">판단 불가</option></select><label for="reason_{i}">근거</label><textarea id="reason_{i}" placeholder="흠집·경계·반사 등 판단 근거를 짧게 적어주세요."></textarea></article>')
 contact.save(out/'contact_sheet.jpg',quality=92)
 page=template.read_text();start=page.index('<h2>A. 높은 우선순위');end=page.index('<script>',start);page=page[:start]+'\n'.join(cards)+'\n'+page[end:]
 begin=page.index('const queue=');end=page.index(", key='door-priority-'",begin);page=page[:begin]+'const queue='+json.dumps(queue,ensure_ascii=True).replace('<','\\u003c')+', sourceHash='+json.dumps(sha(out/'review_queue.json'))+page[end:]
 page=page.replace('24쌍','12쌍').replace('총24','총12').replace("a.download='door_triage_review_draft.json'","a.download='door_neighborhood_review_draft.json'")
 start=page.index('<p>이번 화면은');end=page.index('</p>',start)+4
 page=page[:start]+'<p>이번 화면은 확인된 중복 그룹 주변의 새로운 12쌍입니다. 이전 24쌍과 번호가 다릅니다. 왼쪽은 새 분할 초안의 모델 선택 사진, 오른쪽은 학습 사진입니다. 같은 흠집·경계·반사 등을 비교하고, 구도·차종·색만 같다는 이유로 같은 실물을 확정하지 마세요. 불확실하면 판단 불가를 선택해도 됩니다.</p>'+page[end:]
 (out/'index.html').write_text(page)
 test=dict(schema='door-remaining-candidate-review-v1',sourceQueueSHA256=sha(out/'review_queue.json'),applied=False,originalsModified=False,reviewer='SCHEMA_TEST_NOT_HUMAN_REVIEW',reviewedAt=datetime.now(timezone.utc).isoformat(),records=[dict(r,decision='UNSURE',reason='synthetic schema check only') for r in queue]);assert len(validate(test,queue,sha(out/'review_queue.json')))==12
 assert page.count('<article ')==12 and all(f'id="decision_{i}"' in page for i in range(12))
 assert 'reviewed.length!==queue.length' in page and '24쌍' not in page.replace('이전 24쌍','')
 result=dict(status='12_pair_neighborhood_review_ready_not_reviewed',sourceNeighborhood=str(near),sourceDraft=str(draft),queueCount=12,previous24PairOverlap=0,repeatedGroups=0,sourceImageHashesMatch=True,syntheticExportSchemaValidated=True,browserInteractionVerified=False,trainingStarted=False,currentModelChanged=False,manifestsChanged=False,finalTestRead=False,reservedPixelsRead=False,sourceHashes={str(p):sha(p) for p in [near/'summary.json',near/'next_priority_pairs_proposal.json',draft/'groups.json',draft/'suspected_part_constraints.json',template,Path(__file__).resolve()]})
 dump(out/'summary.json',result);dump(root/'outputs/door_neighborhood_review/latest.json',dict(directory=str(out),reviewPage=str(out/'index.html'),queue=str(out/'review_queue.json'),reviewed=False,trainingReady=False))
 dump(out/'work_order.json',dict(steps=[dict(order=1,task='human review of these12 pairs',status='awaiting_user_export'),dict(order=2,task='import confirmed groups; retain suspected/unsure separately; recalculate conservative role-block option',status='pending_step1'),dict(order=3,task='document residual risk and version final experiment split; validate all role boundaries',status='pending_step2'),dict(order=4,task='retraining from ImageNet only after split freeze and run configuration readiness',status='not_started')],current_training_or_api_model_changed=False))
 (out/'README.md').write_text('''# 우선 주변 관계 12쌍 검토

index.html에서왼쪽(새초안모델선택)과오른쪽(학습)을비교한다. 이전24쌍과별도번호1~12번이다. 같은사진/같은실물의심/다른사진/판단불가를선택하고근거를짧게적는다. 원본은사진을클릭해연다.

검토자를입력하고12쌍완료후검토완료JSON내보내기를누른다. 중간입력은자동저장되며백업JSON저장·불러오기도가능하다. 완료내보내기와중간백업은구분한다.

이결과를받은뒤확정그룹을갱신하고불확실한관계의보수적같은역할처리범위와자료손실·균형영향을다시계산한다. 그기준과잔여위험을기록한후분할고정으로진행하며12쌍만으로전체독립성을확정하지않는다. 새분할을고정하기전학습을시작하지않는다.

원본SHA·사례대응·이전24쌍미중복·그룹반복없음·12개입력·24개미리보기·합성내보내기스키마를확인했다. 실제브라우저클릭·다운로드는미검증이다. 합성판단은사람검토결과로저장하지않았다.
''')
 print('[12-PAIR NEIGHBOR REVIEW]',out/'index.html')
if __name__=='__main__':main()
