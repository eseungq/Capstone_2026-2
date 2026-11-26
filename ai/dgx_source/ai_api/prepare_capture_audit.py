"""Uniform random visual audit of current representative candidates; no inference."""
import csv,hashlib,html,json,random
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
ROOT=Path(__file__).resolve().parents[1]
def main():
 latest=json.loads((ROOT/'ai_api/verification/latest_data_proposal.json').read_text());source=ROOT/latest['representativeDirectory']/'candidate_manifest.csv'
 with source.open() as f:rows=list(csv.DictReader(f))
 assert len(rows)==13219 and len({r['group_id'] for r in rows})==13219
 selected=random.Random(20261018).sample(sorted(rows,key=lambda r:r['group_id']),64)
 output=ROOT/'ai_api/verification'/('capture_audit_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
 cases=[];sheets=[Image.new('RGB',(1600,1360),'white') for _ in range(4)]
 for i,row in enumerate(selected):
  path=Path(row['image_path']);ident=f'sample_{i+1:02d}'
  with Image.open(path) as im:display=ImageOps.exif_transpose(im).convert('RGB')
  size=display.size;display.thumbnail((1000,1000));display.save(output/(ident+'.jpg'),quality=94)
  thumb=display.copy();thumb.thumbnail((390,305));sheet=sheets[i//16];x=(i%4)*400;y=((i%16)//4)*340;sheet.paste(thumb,(x,y+28));ImageDraw.Draw(sheet).text((x+6,y+6),ident,fill='black')
  cases.append(dict(id=ident,groupId=row['group_id'],imagePath=str(path),imageSHA256=hashlib.sha256(path.read_bytes()).hexdigest(),displaySize=size,proposedClass=int(row['proposed_class_id'])))
 for i,sheet in enumerate(sheets):sheet.save(output/f'contact_{i+1}.jpg',quality=92)
 report=dict(status='prepared',population=13219,sampleCount=64,seed=20261018,method='simple random sampling without replacement from group representatives; no filtering by prediction, class, filename or framing',source=str(source),sourceSHA256=hashlib.sha256(source.read_bytes()).hexdigest(),finalTestUsed=False,originalsModified=False,cases=cases)
 (output/'source.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 parts=['<!doctype html><meta charset="utf-8"><title>도어 촬영 범위 무작위64장</title><h1>도어 외측 촬영 범위 표본64장</h1><p>분류 성능 평가가 아닌 촬영 구도 점검입니다. 라벨·예측은 표시하지 않습니다. 사진을 누르면 원본을 엽니다.</p>']
 for c in cases:parts.append('<h2>'+c['id']+'</h2><a href="'+html.escape(Path(c['imagePath']).as_uri(),quote=True)+'"><img style="max-width:900px;width:95%" src="'+c['id']+'.jpg"></a>')
 (output/'index.html').write_text('\n'.join(parts));print(output)
if __name__=='__main__':main()
