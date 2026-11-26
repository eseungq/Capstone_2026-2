"""Create a bounded, deterministic Training-only scope review; never train."""
import csv,hashlib,html,io,json,random
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1]
def main():
 inventory=Path(json.loads((ROOT/'cowl_model/latest_inventory.json').read_text())['directory'])
 rows=list(csv.DictReader((inventory/'image_label_inventory.csv').open(encoding='utf-8-sig')))
 buckets=defaultdict(list)
 for r in rows:
  if r['status']=='ok':buckets[(r['annotation_types'],r['source_quality'])].append(r)
 selected=[]
 for key,items in sorted(buckets.items()):
  items=sorted(items,key=lambda r:r['image_id']);random.Random('cowl-scope-v1:'+repr(key)).shuffle(items);selected.extend(items[:8])
 out=ROOT/'outputs/cowl_scope_review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 samples=[];cards=[]
 # Korean labels are kept explicit for the reviewer.
 fields={'targetVisible':['미선택','충분히 보임','일부 부족','보이지 않음'],'visibility224':['미선택','224에서도 판단 가능','원본에서만 판단 가능','판단 어려움'],'framing':['미선택','공정 입력 후보','보조 후보','제외 후보'],'labelAgreement':['미선택','원천 라벨에 동의','라벨 불일치 의심','판단 보류']}
 for i,r in enumerate(selected,1):
  ident=f'sample_{i:02d}'
  with open(r['image_archive'],'rb') as f:f.seek(int(r['image_offset']));raw=f.read(int(r['image_bytes']))
  if len(raw)!=int(r['image_bytes']):raise ValueError('Truncated archive read')
  (out/f'{ident}_original.jpg').write_bytes(raw)
  with Image.open(io.BytesIO(raw)) as im:
   source_size=im.size;display=ImageOps.exif_transpose(im).convert('RGB')
  size=display.size;inp=ImageOps.pad(display,(224,224),method=Image.Resampling.BICUBIC,color=(124,116,104));inp.save(out/f'{ident}_224.png')
  preview=display.copy();preview.thumbnail((1000,700));preview.save(out/f'{ident}_preview.jpg',quality=92)
  sample=dict(r,id=ident,image_sha256=hashlib.sha256(raw).hexdigest(),raw_size=source_size,display_size=size)
  samples.append(sample)
  selects=''.join(f'<label>{html.escape(k)} <select data-field="{k}">'+''.join(f'<option>{html.escape(v)}</option>' for v in vals)+'</select></label>' for k,vals in fields.items())
  cards.append(f'<section data-id="{ident}"><h2>{ident} · {html.escape(r["annotation_types"])} · 원천 {html.escape(r["source_quality"])}</h2><a href="{ident}_original.jpg" target="_blank"><img class="preview" src="{ident}_preview.jpg"></a><img width="224" height="224" src="{ident}_224.png"><p>왼쪽 클릭: 원본 확대 / 오른쪽: 224 입력(정규화 전)</p>{selects}<label>검사 대상 위치·관찰·보류 사유<textarea data-field="notes"></textarea></label></section>')
 manifest=dict(schema='cowl-scope-review-v1',inventory=str(inventory),selection='seeded convenience sample up to 8 per type/quality; not representative, duplicate audit pending',samples=samples,trainingStarted=False,splitCreated=False,finalTestUsed=False,preprocessing='EXIF transpose -> RGB -> BICUBIC pad224 RGB(124,116,104); visualization only, no normalization/model')
 (out/'selection.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 page='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>카울커버 학습 전 검토</title><style>body{font-family:sans-serif;margin:24px}section{border-top:2px solid #777;padding:20px 0}.preview{max-width:65%;max-height:550px}label{display:block;margin:10px}textarea{display:block;width:90%;height:70px}header{position:sticky;top:0;background:white;padding:12px;border:1px solid #aaa}</style><header>검토자 <input id="reviewer"><button onclick="save()">임시 저장</button><button onclick="exportReview()">검토 JSON 내보내기</button><span id="status"></span></header><h1>카울커버: 검사 범위·사진 사용 검토</h1><p>고정핀 유형은 핀과 체결 주변, 연계 유형은 부품 연결부를 확인합니다. 다른 손상만으로 해당 유형 라벨을 바꾸지 말고 메모하세요. 대상이 안 보이는 사진을 GOOD으로 판단하지 마세요. 근접 촬영 자체는 제외 사유가 아닙니다. 224에서 작은 틈이 사라지는지도 비교하세요. 연계 불량의 세부 정의는 가이드 대조 전 미확정입니다.</p>'''+''.join(cards)+'''<script>
const key='cowl-review:'+location.pathname;
function collect(){return {schema:'cowl-scope-review-v1',selectionFile:location.href.replace(/index.html.*$/,'selection.json'),reviewer:document.querySelector('#reviewer').value.trim(),exportedAt:new Date().toISOString(),observations:[...document.querySelectorAll('section')].map(s=>({id:s.dataset.id,...Object.fromEntries([...s.querySelectorAll('[data-field]')].map(e=>[e.dataset.field,e.value]))}))}}
function save(){try{localStorage.setItem(key,JSON.stringify(collect()));document.querySelector('#status').textContent='임시 저장됨. 최종 제출은 JSON 내보내기';}catch(e){document.querySelector('#status').textContent='브라우저 저장 불가: JSON으로 내보내세요';}}
function exportReview(){const d=collect();if(!d.reviewer){alert('검토자를 입력해주세요');return}const u=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='cowl_scope_review_'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),10000);document.querySelector('#status').textContent='다운로드 폴더의 JSON 파일을 확인해주세요';}
try{const d=JSON.parse(localStorage.getItem(key)||'null');if(d){document.querySelector('#reviewer').value=d.reviewer||'';for(const r of d.observations||[]){const s=document.querySelector('section[data-id="'+r.id+'"]');if(s)for(const e of s.querySelectorAll('[data-field]'))e.value=r[e.dataset.field]||e.value}}}catch(e){}
document.addEventListener('change',save);
</script></html>'''
 (out/'index.html').write_text(page)
 (ROOT/'cowl_model/latest_review.json').write_text(json.dumps(dict(directory=str(out),html=str(out/'index.html'),samples=len(samples)),ensure_ascii=False,indent=2))
 print('[COWL REVIEW READY]',out/'index.html',flush=True)
if __name__=='__main__':main()
