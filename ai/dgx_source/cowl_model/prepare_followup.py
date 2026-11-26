"""Preserve source annotations and show the three unresolved scope samples."""
import hashlib,html,json,subprocess,tarfile
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
ROOT=Path(__file__).resolve().parents[1]
GUIDE=Path('/path/to/private-user/다운로드/04.데이터구축가이드라인_2-9-19.자동차 부품.pdf')
def main():
 original=Path(json.loads((ROOT/'cowl_model/latest_review.json').read_text())['directory']);selection=json.loads((original/'selection.json').read_text());out=ROOT/'outputs/cowl_followup'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 guide_text=subprocess.check_output(['pdftotext','-layout',str(GUIDE),'-']).decode();(out/'guide_text.txt').write_text(guide_text)
 subprocess.run(['pdftoppm','-f','6','-l','6','-scale-to','1600','-singlefile','-png',str(GUIDE),str(out/'guide_page6')],check=True)
 records=[];cards=[]
 for r in selection['samples']:
  if r['id'] not in {'sample_17','sample_18','sample_22'}:continue
  ident=r['id']
  with tarfile.open(r['label_archive']) as archive:raw=archive.extractfile(r['label_member']).read()
  if hashlib.sha256(raw).hexdigest()!=r['label_sha256']:raise ValueError('Label changed')
  label=json.loads(raw.decode('utf-8-sig'));(out/f'{ident}_label.json').write_bytes(raw)
  with Image.open(original/f'{ident}_original.jpg') as im:
   orientation=im.getexif().get(274,1);base=im.convert('RGB');marked=base.copy();draw=ImageDraw.Draw(marked);boxes=[]
   for ann in label['annotations']:
    x,y,w,h=ann['bbox']
    if not (w>0 and h>0 and 0<=x<x+w<=base.width and 0<=y<y+h<=base.height):raise ValueError('Invalid source box')
    boxes.append([x,y,w,h]);draw.rectangle((x,y,x+w,y+h),outline='red',width=max(4,base.width//500))
   # Source box coordinates belong to raw pixels; apply EXIF after drawing.
   marked.info['exif']=im.info.get('exif',b'');marked=ImageOps.exif_transpose(marked);marked.thumbnail((1200,900));marked.save(out/f'{ident}_source_box.jpg',quality=94)
   crops=[]
   for n,(x,y,w,h) in enumerate(boxes):
    if orientation!=1:continue # Do not silently misorient a source-coordinate crop.
    crop=base.crop((int(x),int(y),int(x+w+.999),int(y+h+.999)));crop.thumbnail((1100,800));name=f'{ident}_crop_{n}.jpg';crop.save(out/name,quality=95);crops.append(name)
  records.append(dict(id=ident,image_id=r['image_id'],label_sha256=r['label_sha256'],source_boxes_xywh=boxes,exif_orientation=orientation,crop_files=crops,source_label=str(out/f'{ident}_label.json'),original=str(original/f'{ident}_original.jpg')))
  options=''.join('<option>'+v+'</option>' for v in ['미선택','주석 영역에서 불량 근거 확인','여전히 불량 근거 불명확','검사 부위가 보이지 않음'])
  cards.append(f'<section data-id="{ident}"><h2>{ident} / 연계 불량 · 원천 불량품</h2><a href="{html.escape(str(original/f"{ident}_original.jpg"))}" target="_blank">원본 확대</a> · <a href="{ident}_label.json">원천 JSON</a><p>빨간 사각형은 원천 주석입니다. 결함의 정확한 윤곽이나 검증된 정답 마스크가 아닙니다.</p><img src="{ident}_source_box.jpg">'+''.join(f'<p>주석 영역 확대(검토용이며 모델 입력 변경 아님)</p><img src="{name}">' for name in crops)+f'<p>기존 224 전체 입력</p><img width="224" src="{original}/{ident}_224.png"><label>재확인 <select>{options}</select></label><textarea placeholder="보이는 근거 또는 계속 불명확한 이유"></textarea></section>')
 manifest=dict(schema='cowl-followup-v1',samples=records,guide=str(GUIDE),guide_sha256=hashlib.sha256(GUIDE.read_bytes()).hexdigest(),guide_pages=[5,6],finding='Guide identifies assembly work and source bounding boxes for pin/link defects; text does not establish a numeric gap/tolerance or detailed link defect criterion.',sourceModified=False,trainingStarted=False)
 (out/'evidence.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 page='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>카울커버 3장 재확인</title><style>body{font:17px sans-serif;margin:24px}img{max-width:95%;max-height:700px}section{border-top:2px solid #888;padding:20px 0}textarea{display:block;width:90%;height:80px}label{display:block;margin:15px}</style><h1>카울커버 보류 3장: 원천 주석과 비교</h1><p>구축 가이드 5쪽은 두 유형을 조립 검사·BB 주석으로 분류합니다. 6쪽에는 정상·불량 예시가 있으나 텍스트만으로 세부 허용 틈이나 불량 조건이 확정되지는 않습니다. 주석을 봐도 불명확하면 보류하세요. 22번은 확대에서 보이는 근거가 224에서도 유지되는지 기록하세요.</p><a href="guide_page6.png" target="_blank">구축 가이드 6쪽 정상·불량 예시</a><p>검토자 <input id="reviewer"><button onclick="downloadReview()">재확인 JSON 내보내기</button><span id="status"></span></p>'''+''.join(cards)+'''<script>function downloadReview(){const reviewer=document.querySelector('#reviewer').value.trim();const observations=[...document.querySelectorAll('section')].map(s=>({id:s.dataset.id,judgment:s.querySelector('select').value,notes:s.querySelector('textarea').value}));if(!reviewer||observations.some(r=>r.judgment==='미선택')){alert('검토자와 3장의 재확인 항목을 작성해주세요');return}const d={schema:'cowl-followup-v1',evidenceFile:location.href.replace(/index.html.*$/,'evidence.json'),reviewer,observations,exportedAt:new Date().toISOString()};const u=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='cowl_followup_'+Date.now()+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),10000);document.querySelector('#status').textContent='다운로드 폴더를 확인해주세요';}</script>'''
 (out/'index.html').write_text(page);(ROOT/'cowl_model/latest_followup.json').write_text(json.dumps(dict(directory=str(out),html=str(out/'index.html')),ensure_ascii=False,indent=2));print('[COWL FOLLOWUP]',out/'index.html')
if __name__=='__main__':main()
