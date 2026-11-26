"""Rank all cowl candidates, preserve exact groups, and offer a bounded human review."""
import csv,hashlib,html,io,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
from ai_api.rank_similarity import features,metrics
ROOT=Path(__file__).resolve().parents[1]
def main():
 source=Path(json.loads((ROOT/'cowl_model/latest_full_similarity.json').read_text())['directory']);summary=json.loads((source/'summary.json').read_text())
 if summary['status']!='complete_candidates_unreviewed' or summary['decode_errors']!=0:raise ValueError('Full clean fingerprint pass required')
 records={r['image_id']:r for r in map(json.loads,(source/'fingerprints.jsonl').read_text().splitlines())};pairs=list(map(json.loads,(source/'candidates.jsonl').read_text().splitlines()))
 if len(pairs)!=summary['candidate_pairs'] or len(records)!=summary['total_images']:raise ValueError('Source counts differ')
 inventory=Path(summary['inventory'])
 if hashlib.sha256(inventory.read_bytes()).hexdigest()!=summary['inventory_sha256']:raise ValueError('Inventory changed')
 rows={r['image_id']:r for r in csv.DictReader(inventory.open(encoding='utf-8-sig'))};out=ROOT/'outputs/cowl_similarity_review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);(out/'images').mkdir()
 cache={}
 def get(ident):
  if ident not in cache:
   with Image.open(source/'thumbs'/f'{ident}.jpg') as im:f=features(im)
   r=records[ident];cache[ident]=(f[0],f[1],r['width']/r['height'])
  return cache[ident]
 for p in pairs:p.update(metrics(get(p['a']),get(p['b'])))
 ranked=sorted(pairs,key=lambda p:(not p['cross_quality'],not p['cross_type'],p['rankScore'],p['dhash_distance'],p['a'],p['b']))
 (out/'ranked_candidates.json').write_text(json.dumps(ranked,ensure_ascii=False,indent=2))
 exact={}
 for ident,r in records.items():exact.setdefault(r['display_sha256'],[]).append(ident)
 groups=[dict(display_sha256=h,members=sorted(ids),source_qualities=sorted({records[i]['quality'] for i in ids}),types=sorted({records[i]['type'] for i in ids})) for h,ids in sorted(exact.items()) if len(ids)>1]
 (out/'exact_display_groups.json').write_text(json.dumps(dict(groups=groups,sourceUnchanged=True,appliedToSplit=False,identityMeaning='Identical EXIF-corrected RGB size/pixels; physical part identity not established'),ensure_ascii=False,indent=2))
 # Only non-exact pairs need visual identity decisions. Limit repeated images first.
 candidates=[p for p in ranked if not p['exact_display_pixels']];selected=[];used=set()
 for p in candidates:
  if p['a'] in used or p['b'] in used:continue
  selected.append(p);used.update((p['a'],p['b']))
  if len(selected)==32:break
 cards=[]
 for n,p in enumerate(selected,1):
  ident=f'pair_{n:02d}';p['review_id']=ident
  images=[]
  for key in ['a','b']:
   sid=p[key];r=rows[sid];dest=out/'images'/f'{sid}.jpg'
   if not dest.exists():
    with open(r['image_archive'],'rb') as f:f.seek(int(r['image_offset']));raw=f.read(int(r['image_bytes']))
    if hashlib.sha256(raw).hexdigest()!=records[sid]['source_sha256']:raise ValueError('Image changed')
    with Image.open(io.BytesIO(raw)) as im:display=ImageOps.exif_transpose(im).convert('RGB')
    display.thumbnail((1400,1000));display.save(dest,quality=94)
   images.append(f'<div><p>{html.escape(r["annotation_types"])} / 原本 {html.escape(r["source_quality"])}</p><a href="images/{sid}.jpg" target="_blank"><img src="images/{sid}.jpg"></a></div>'.replace('原本','원천'))
  options=''.join('<option>'+v+'</option>' for v in ['미선택','같은 사진','같은 실물·연속 촬영 의심','다른 사진·실물 관계 불명','판단 보류'])
  cards.append(f'<section data-id="{ident}"><h2>{n}번 · dHash 거리 {p["dhash_distance"]}'+(' · 정상/불량 라벨 다름' if p['cross_quality'] else '')+'</h2><div class="pair">'+''.join(images)+f'</div><select>{options}</select><textarea placeholder="같다고 판단한 근거 또는 애매한 점"></textarea></section>')
 selected_ids={(p['a'],p['b']) for p in selected}
 data=dict(schema='cowl-similarity-review-v1',source=str(source),candidate_sha256=hashlib.sha256((source/'candidates.jsonl').read_bytes()).hexdigest(),total_images=len(records),candidate_pairs=len(pairs),exact_display_pairs=summary['exact_display_pairs'],exact_groups=len(groups),exact_group_images=sum(len(g['members']) for g in groups),cross_quality_pairs=sum(p['cross_quality'] for p in pairs),cross_type_pairs=sum(p['cross_type'] for p in pairs),review_pairs=len(selected),nonexact_unreviewed_outside_batch=len(candidates)-len(selected),selection='Non-exact candidates; prioritize cross-quality then cross-type then existing Pillow image/edge/aspect ranking, no repeated images in this batch. Heuristic priority, not identity confidence.',samples=selected,splitChanged=False,trainingStarted=False)
 (out/'selection.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
 (out/'summary.json').write_text(json.dumps({k:v for k,v in data.items() if k!='samples'},ensure_ascii=False,indent=2))
 page='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>카울커버 유사 사진 검토</title><style>body{font:17px sans-serif;margin:24px}.pair{display:flex;gap:10px}.pair>div{width:49%}img{width:100%}section{padding:18px 0;border-top:2px solid #999}textarea{display:block;width:95%;height:65px}header{position:sticky;top:0;background:white;padding:12px}</style><header>검토자 <input id="reviewer"><button onclick="save()">임시 저장</button><button onclick="downloadReview()">검토 JSON 내보내기</button><span id="status"></span></header><h1>카울커버 유사 후보 32쌍</h1><p>자동 후보이며 동일 사진으로 확정된 것이 아닙니다. 같은 사진은 구도·부품·주변 무늬가 일치하는 촬영본입니다. 사진이 다르더라도 같은 부품을 연속 촬영한 것으로 의심되면 별도 항목을 선택하세요. 비슷한 차종/형상만으로 같은 실물이라고 판단하지 마세요. 다른 사진으로 선택해도 독립 실물 확인을 뜻하지 않습니다. 이미지를 누르면 큰 미리보기를 엽니다. 동일 표시 픽셀 그룹은 별도 기록했고 원본·라벨·분할은 바꾸지 않았습니다.</p>'''+''.join(cards)+'''<script>
const storageKey='cowl-similarity:'+location.pathname;
function collect(){return {schema:'cowl-similarity-review-v1',selectionFile:location.href.replace(/index.html.*$/,'selection.json'),reviewer:document.querySelector('#reviewer').value.trim(),exportedAt:new Date().toISOString(),observations:[...document.querySelectorAll('section')].map(s=>({id:s.dataset.id,judgment:s.querySelector('select').value,notes:s.querySelector('textarea').value}))}}
function save(){try{localStorage.setItem(storageKey,JSON.stringify(collect()));document.querySelector('#status').textContent='임시 저장됨';}catch(e){document.querySelector('#status').textContent='임시 저장 불가: JSON 내보내기로 저장하세요';}}
function downloadReview(){const d=collect();if(!d.reviewer||d.observations.some(r=>r.judgment==='미선택')){alert('검토자와 32쌍의 판단을 입력해주세요');return}const u=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='cowl_similarity_review_'+Date.now()+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),10000);document.querySelector('#status').textContent='다운로드 폴더를 확인해주세요';}
try{const d=JSON.parse(localStorage.getItem(storageKey)||'null');if(d){document.querySelector('#reviewer').value=d.reviewer||'';for(const r of d.observations||[]){const s=document.querySelector('section[data-id="'+r.id+'"]');if(s){s.querySelector('select').value=r.judgment;s.querySelector('textarea').value=r.notes||''}}}}catch(e){}
document.addEventListener('change',save);
</script></html>'''
 (out/'index.html').write_text(page);(ROOT/'cowl_model/latest_similarity_review.json').write_text(json.dumps(dict(directory=str(out),html=str(out/'index.html')),ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in data.items() if k not in {'samples','selection','candidate_sha256'}},ensure_ascii=False,indent=2));print('[COWL SIMILARITY REVIEW]',out/'index.html')
if __name__=='__main__':main()
