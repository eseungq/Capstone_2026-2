"""Build a small visible-DOOR label clarification page without changing labels."""
import csv,hashlib,html,json,shutil
from datetime import datetime,timezone
from pathlib import Path

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 root=Path(__file__).resolve().parents[1];imported=Path(load(root/'outputs/door_cam_observation_import/latest.json')['directory']);meta=load(imported/'summary.json');source=Path(meta['sourceReport']);report=load(source);samples={s['id']:s for s in report['samples']};observations={r['id']:r for r in load(imported/'observations.json')};run=Path(report['run']);cfg=load(run/'run_config.json');experiment=cfg['manifests']['provenance']['config']
 with (root/experiment['manifests']['model_selection']).open(encoding='utf-8-sig',newline='') as f:by_path={r['image_path']:r for r in csv.DictReader(f)}
 if sha(source)!=meta['sourceReportSHA256']:raise ValueError('GPU report changed')
 specs=[(['sample_1465'],'흠집이 없다는 관찰이 다른 손상도 없다는 뜻인지 확인'),(['sample_1148'],'저장 DEFECT와 결함 없음 관찰의 차이 확인'),(['sample_0129'],'저장 GOOD과 결함 있음 관찰의 차이 확인'),(['sample_0170'],'저장 GOOD과 결함 있음 관찰의 차이 확인. 레이어3 정정은 별도로 보존'),(['sample_0878','sample_0879'],'같은 사진으로 확인된 두 장: 저장 DEFECT와 결함 없음 관찰 확인')]
 out=root/'outputs/door_label_recheck'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);queue=[];cards=[]
 for i,(idents,reason) in enumerate(specs,1):
  item=dict(caseId=f'label_{i:02d}',sampleIds=idents,reasonForRecheck=reason,scope='visible target DOOR only',samples=[])
  cards.append(f'<section><h2>{i}/5 · '+html.escape(' / '.join(idents))+'</h2><p>'+html.escape(reason)+'</p>')
  for ident in idents:
   s=samples[ident];row=by_path[s['image_path']];jp=Path(row['json_path'])
   if sha(Path(s['image_path']))!=s['image_sha256']:raise ValueError('Original image changed')
   item['samples'].append(dict(id=ident,imagePath=s['image_path'],imageSHA256=s['image_sha256'],jsonPath=str(jp),jsonSHA256=sha(jp),storedTrainingClass=int(row['proposed_class_id']),originalObservation=observations[ident]['raw_notes']))
   for name in ['display.jpg','input224.png']:shutil.copy2(source.parent/ident/name,out/f'{ident}_{name}')
   cards.append('<p>학습에 사용한 라벨: <b>'+('GOOD' if row['proposed_class_id']=='0' else 'DEFECT')+'</b></p><p>기존 관찰: '+html.escape(observations[ident]['raw_notes'])+'</p>')
   cards.append(f'<div class="images"><a target="_blank" href="{html.escape(Path(s["image_path"]).as_uri(),quote=True)}"><img src="{ident}_display.jpg"><p>원본 미리보기 · 클릭하면 원본</p></a><figure><img src="{ident}_input224.png"><figcaption>실제 224 입력</figcaption></figure></div>')
  cards.append(f'<label for="decision_{i-1}">보이는 대상 도어의 품질 </label><select id="decision_{i-1}"><option value="UNREVIEWED">미검토</option><option value="GOOD_CANDIDATE">손상 없음 → GOOD 후보</option><option value="DEFECT_CANDIDATE">손상 있음 → DEFECT 후보</option><option value="HOLD">판단 불가 → 보류</option></select><textarea id="reason_{i-1}" placeholder="손상 종류·위치 또는 판단이 어려운 이유를 적어주세요."></textarea></section>')
  queue.append(item)
 dump(out/'review_queue.json',queue)
 page='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>도어 라벨 재확인 5건</title><style>body{font:18px sans-serif;max-width:1200px;margin:25px auto}.images{display:flex;gap:20px}.images a{width:65%}.images figure{width:30%;margin:0}.images img{max-width:100%;max-height:650px;object-fit:contain}section{border-top:1px solid #aaa;padding:20px 0}input,select,textarea,button{font:inherit;margin:10px 0}textarea{display:block;width:95%;height:85px}</style><h1>보이는 도어 라벨 재확인 · 5건/6장</h1><p>현재 라벨과 이전 관찰이 다른 항목만 확인합니다. 흠집뿐 아니라 찍힘·깨짐 등 보이는 대상 도어의 손상이 하나라도 있으면 DEFECT 후보입니다. 보이지 않는 면까지 정상이라고 판단하지 마세요. 판단이 어려우면 보류할 수 있습니다.</p><p>이 화면은 원본과224입력만 보여 줍니다. 원본 라벨·모델은 자동 변경하지 않습니다. 마지막 두 사진은 같은 사진으로 확인된 관계여서 한 번의 판단으로 기록하되 두 원본을 함께 확인하세요.</p><label>검토자 <input id="reviewer"></label><button id="export">라벨 재확인 JSON 내보내기</button><p id="message"></p>'''+ '\n'.join(cards)
 page+='''<script>
const queue=__QUEUE__,sourceHash=__HASH__,key='door-label-recheck-'+sourceHash;
function collect(){return {reviewer:document.getElementById('reviewer').value.trim(),records:queue.map((r,i)=>({...r,decision:document.getElementById('decision_'+i).value,reason:document.getElementById('reason_'+i).value.trim()}))}}
function persist(){try{localStorage.setItem(key,JSON.stringify(collect()))}catch(e){document.getElementById('message').textContent='브라우저 자동 저장이 제한됩니다. 완료 후 반드시 내보내세요.'}}
try{const old=JSON.parse(localStorage.getItem(key)||'null');if(old){document.getElementById('reviewer').value=old.reviewer||'';old.records.forEach((r,i)=>{if(queue[i]&&r.caseId===queue[i].caseId){document.getElementById('decision_'+i).value=r.decision;document.getElementById('reason_'+i).value=r.reason}})}}catch(e){}
document.addEventListener('input',persist);document.addEventListener('change',persist);
document.getElementById('export').onclick=()=>{const data=collect(),msg=document.getElementById('message');if(!data.reviewer||data.records.some(r=>r.decision==='UNREVIEWED'||!r.reason)){msg.textContent='검토자와 5건의 판단·근거를 입력하세요.';return}persist();const obj={schema:'door-visible-label-recheck-v1',sourceQueueSHA256:sourceHash,reviewedAt:new Date().toISOString(),applied:false,originalsModified:false,...data};const u=URL.createObjectURL(new Blob([JSON.stringify(obj,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='door_label_recheck_'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);msg.textContent='다운로드를 요청했습니다. 원본 라벨은 변경되지 않았습니다.'};
</script></html>'''
 page=page.replace('__QUEUE__',json.dumps(queue,ensure_ascii=True).replace('<','\\u003c')).replace('__HASH__',json.dumps(sha(out/'review_queue.json')));assert page.count('<section>')==5 and len(list(out.glob('*_display.jpg')))==6
 (out/'index.html').write_text(page);dump(out/'summary.json',dict(status='label_recheck_ready_not_reviewed',sourceReviewImport=str(imported),sourceGPUReport=str(source),caseCount=5,imageCount=6,samePhotoCombinedCase=['sample_0878','sample_0879'],labelsChanged=False,modelChanged=False,trainingStarted=False,finalTestRead=False,sourceHashes={str(p):sha(p) for p in [source,imported/'observations.json',Path(__file__).resolve()]},browserVerified=False))
 dump(root/'outputs/door_label_recheck/latest.json',dict(directory=str(out),reviewPage=str(out/'index.html'),queue=str(out/'review_queue.json'),reviewed=False))
 print('[LABEL RECHECK PAGE]',out/'index.html')
if __name__=='__main__':main()
