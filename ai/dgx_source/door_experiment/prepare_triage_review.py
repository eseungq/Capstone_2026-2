"""Build an offline 24-pair review page from versioned independence triage."""
import hashlib,html,json
from datetime import datetime,timezone
from collections import Counter
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
from ai_api.import_door_remaining_review import validate

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 root=Path(__file__).resolve().parents[1];triage=Path(load(root/'outputs/door_independence_triage/latest.json')['directory']);summary=load(triage/'summary.json');draft=Path(summary['sourceDraft']);selected=load(triage/'proposed_first_pass_24.json');cache={r['path']:r for r in load(triage/'pixel_feature_cache.json')};template=root/'ai_api/similarity_priority_template.html'
 if len(selected)!=24 or summary['firstPassComposition']!={'high':16,'uncertain':4,'lower':4}:raise ValueError('Unexpected review size or bands')
 queue=[]
 for i,r in enumerate(selected,1):
  queue.append(dict(r,caseId=f'candidate_{i:02d}',validation_image=r['selection_image'],validationGroup=r['selection_group'],trainGroup=r['train_group'],proposalRoles=['model_selection','train'],displayNumber=i,scope='current_future_draft_not_independent_evaluation',priorityMeaning='review scheduling only, never identity judgment'))
 known=load(triage/'previously_reviewed_pairs.json');pair=lambda r:tuple(sorted((r['selection_image'],r['train_image'])))
 if {pair(r) for r in selected}&{pair(r) for r in known}:raise ValueError('Previously reviewed pair selected')
 if len({r[k] for r in selected for k in ['selection_group','train_group']})!=48:raise ValueError('Repeated review groups')
 out=root/'outputs/door_triage_review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);dump(out/'review_queue.json',queue)
 cards=[];contacts=[Image.new('RGB',(1000,220*12),'white') for _ in range(2)];draws=[ImageDraw.Draw(c) for c in contacts]
 for i,r in enumerate(queue):
  if i in (0,16,20):cards.append('<h2>'+{0:'A. 높은 우선순위 16쌍',16:'B. 중간 우선순위 점검 표본 4쌍',20:'C. 낮은 우선순위 점검 표본 4쌍'}[i]+'</h2>')
  cards.append(f'<article id="case_{i+1}"><h3>이번 24쌍 중 {i+1}번</h3><p>왼쪽: 새 초안의 모델 선택 사진 / 오른쪽: 새 초안의 학습 사진</p><div class="pair">')
  sheet=i//12;slot=i%12;draws[sheet].text((8,slot*220+4),f'NEW {i+1}: selection / train',fill='black')
  for j,key in enumerate(['validation_image','train_image']):
   path=Path(r[key])
   if sha(path)!=cache[str(path)]['file_sha256']:raise ValueError('Source image changed')
   with Image.open(path) as im:display=ImageOps.exif_transpose(im).convert('RGB')
   preview=display.copy();preview.thumbnail((1000,760));name=f'pair_{i+1:02d}_{j}.jpg';preview.save(out/name,quality=92)
   small=display.copy();small.thumbnail((490,185));contacts[sheet].paste(small,(j*500,slot*220+25))
   cards.append(f'<a target="_blank" rel="noopener" href="{html.escape(path.as_uri(),quote=True)}"><img loading="lazy" src="{name}" alt="{i+1}번 '+('모델 선택' if j==0 else '학습')+' 원본 미리보기"><p>사진 클릭: 원본 크게 보기</p></a>')
  cards.append(f'</div><label for="decision_{i}">판단 </label><select id="decision_{i}"><option value="UNREVIEWED">미검토</option><option value="SAME_PHOTO">같은 사진</option><option value="POSSIBLY_SAME_PART">같은 실물·다른 촬영 의심</option><option value="DIFFERENT">다른 사진·동일 실물 근거 없음</option><option value="UNSURE">판단 불가</option></select><label for="reason_{i}">근거</label><textarea id="reason_{i}" placeholder="흠집·경계·반사 등 판단 근거를 짧게 적어주세요. 불확실하면 판단 불가를 선택하세요."></textarea></article>')
 for i,c in enumerate(contacts,1):c.save(out/f'contact_sheet_{i}.jpg',quality=92)
 page=template.read_text();start=page.index('<p>왼쪽은');end=page.index('</p>',start)+4
 page=page[:start]+'''<p>이번 화면은 새로운 24쌍입니다. 이전 8쌍·10쌍과 번호가 다릅니다. 왼쪽은 새 분할 초안의 모델 선택, 오른쪽은 학습 사진입니다. 높은 우선순위16쌍과 중간·낮은 우선순위 각4쌍을 같은 기준으로 판단하세요. 낮은 우선순위도 다른 사진으로 미리 간주하면 안 됩니다.</p><p>흠집의 모양·끝·위치, 부품 경계, 손잡이·스티커·반사·배경을 비교하세요. 차종·색상·구도만 같다는 이유로 같은 실물을 확정하지 마세요. 원본은 사진을 누르면 열립니다. 중간 입력은 현재 브라우저에 자동 저장되므로 같은 화면에서 이어 할 수 있습니다. 브라우저 저장이 제한된 환경에서는 보장이 안 되므로 중간 백업도 가능합니다.</p>'''+page[end:]
 page=page.replace('__CARDS__','\n'.join(cards)).replace('__COUNT__','24').replace('__QUEUE_JSON__',json.dumps(queue,ensure_ascii=True).replace('<','\\u003c')).replace('__QUEUE_SHA_JSON__',json.dumps(sha(out/'review_queue.json')))
 # Require all records only for final export; a separate draft backup preserves partial work.
 page=page.replace("if(!reviewed.length){msg.textContent='한 건 이상의 판단을 선택해 주세요.';return}","if(reviewed.length!==queue.length){msg.textContent='완료 내보내기는 24쌍 모두 판단해야 합니다. 미완료 상태는 중간 백업으로 저장할 수 있습니다.';return}")
 page=page.replace('<button id="export">검토 JSON 내보내기</button>','<button id="export">검토 완료 JSON 내보내기</button> <button id="backup">중간 백업 JSON 저장</button> <label>백업 불러오기 <input id="restore" type="file" accept="application/json"></label>')
 extra='''
document.getElementById('backup').onclick=()=>{save();const draft={schema:'door-review-draft-v1',sourceQueueSHA256:sourceHash,...collect()};const u=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='door_triage_review_draft.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);document.getElementById('message').textContent='중간 백업을 저장했습니다. 완료 검토 파일과는 다릅니다.';};
document.getElementById('restore').onchange=async(e)=>{try{const f=e.target.files[0];if(!f)return;const d=JSON.parse(await f.text());if(d.schema!=='door-review-draft-v1'||d.sourceQueueSHA256!==sourceHash||!Array.isArray(d.records)||d.records.length!==queue.length)throw Error('다른 대기열 또는 잘못된 백업');d.records.forEach((r,i)=>{const original={...r};delete original.decision;delete original.reason;if(JSON.stringify(original)!==JSON.stringify(queue[i])||!['UNREVIEWED','SAME_PHOTO','POSSIBLY_SAME_PART','DIFFERENT','UNSURE'].includes(r.decision)||typeof r.reason!=='string')throw Error('사례 메타데이터 불일치')});if(!confirm('백업 내용으로 현재 화면의 입력을 복원할까요?'))return;document.getElementById('reviewer').value=d.reviewer||'';d.records.forEach((r,i)=>{document.getElementById('decision_'+i).value=r.decision;document.getElementById('reason_'+i).value=r.reason});save();document.getElementById('message').textContent='백업을 복원했습니다.'}catch(err){document.getElementById('message').textContent='불러오기 실패: '+err.message}};
'''
 page=page.replace('</script>',extra+'</script>');(out/'index.html').write_text(page)
 if any(x in page for x in ['__CARDS__','__COUNT__','__QUEUE_JSON__','__QUEUE_SHA_JSON__']):raise ValueError('Unreplaced template')
 # Existing import validator accepts the exact queue payload; use explicit synthetic test data only here.
 simulated=dict(schema='door-remaining-candidate-review-v1',sourceQueueSHA256=sha(out/'review_queue.json'),applied=False,originalsModified=False,reviewer='AUTOMATED_SCHEMA_TEST_NOT_USER_REVIEW',reviewedAt=datetime.now(timezone.utc).isoformat(),records=[dict(r,decision='UNSURE',reason='schema test only') for r in queue])
 assert len(validate(simulated,queue,sha(out/'review_queue.json')))==24
 sources=[triage/'summary.json',triage/'proposed_first_pass_24.json',triage/'pixel_feature_cache.json',draft/'groups.json',draft/'suspected_part_constraints.json',template,Path(__file__).resolve()]
 summary=dict(status='24_pair_review_ready_not_human_reviewed',sourceTriage=str(triage),sourceDraft=str(draft),queueCount=24,priorityCounts=Counter(r['priority_band'] for r in queue),displayRoles=['model_selection','train'],previousReviewedPairsSelected=0,repeatedReviewGroups=0,sourceImageHashesMatch=True,exportSchemaValidatedWithSyntheticRecords=True,syntheticRecordsAreUserDecisions=False,browserInteractionVerified=False,currentModelChanged=False,manifestsChanged=False,finalTestRead=False,reservedPixelsRead=False,trainingStarted=False,sourceHashes={str(p):sha(p) for p in sources})
 dump(out/'summary.json',summary);dump(root/'outputs/door_triage_review/latest.json',dict(directory=str(out),reviewPage=str(out/'index.html'),queue=str(out/'review_queue.json'),reviewed=False,readyForTraining=False))
 (out/'README.md').write_text('''# 도어 유사 관계 24쌍 검토

index.html을 브라우저로 연다. 왼쪽은 새 초안의 모델 선택, 오른쪽은 학습이다. 이전 차수와 별도의1~24번이다.

1~16번은 높은 우선순위,17~20번은 중간 점검,21~24번은 낮은 순위 점검이다. 모두 같은 기준으로 판단한다. 같은 사진 / 같은 실물 의심 / 다른 사진·동일 실물 근거 없음 / 판단 불가 중 선택하고 짧은 근거를 적는다. 원본은 미리보기를 눌러 확인한다.

검토자 입력 후24쌍을 마치면 ‘검토 완료 JSON 내보내기’를 누른다. 중간 입력은 브라우저에 자동 저장되며 ‘중간 백업 JSON 저장’으로 파일도 남길 수 있다. 백업은 같은 대기열에서만 불러온다. 백업 불러오기는 사용자 확인 후 현재 입력을 바꾼다. 최종 JSON과 백업 JSON은 다르다.

이24쌍 검토는 전체 독립성 확인 완료를 의미하지 않는다. 낮은 순위에서 같은 사진이 발견되면 자동 선별 한계를 재검토한다. 높은 순위에서 중복이 계속 발견되면 관련 그룹 주변을 추가 확인한다. 새 학습을 시작하거나 기존 모델·분할·원본을 바꾸지 않는다.

검증 범위: 원본48장의SHA와대기열대응, 그룹반복없음, 기존검토쌍미포함, 미리보기존재, 템플릿치환, 합성레코드의내보내기스키마검사. 실제브라우저클릭·다운로드는미검증이다. 합성시험판단은사람검토기록으로저장하지않았다.
''')
 print('[24-PAIR REVIEW]',out/'index.html',flush=True)
if __name__=='__main__':main()
