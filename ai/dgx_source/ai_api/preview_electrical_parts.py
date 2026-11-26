"""Extract a few training-only part examples from existing archives."""
import argparse,hashlib,html,io,json,tarfile
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'downloads/aihub/162.부품_품질_검사_영상_데이터(자동차)/01.데이터/1.Training'
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--parts',nargs='+',choices=['배선','커넥터','카울커버'],default=['배선','커넥터'])
 args=parser.parse_args();codes={'배선':'4','커넥터':'7','카울커버':'6'};parts_requested=list(dict.fromkeys(args.parts));title='·'.join(parts_requested)
 prefix='cowl_preview_' if parts_requested==['카울커버'] else 'electrical_preview_'
 out=ROOT/'ai_api/verification'/(prefix+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir()
 records=[];distribution={}
 for part in parts_requested:
  code=codes[part]
  labels=BASE/'라벨링데이터'/f'TL_{code}.{part}.tar';images=BASE/'원천데이터'/f'TS_{code}.{part}.tar'
  selected=[];counts=Counter()
  with tarfile.open(images) as sources,tarfile.open(labels) as annotations:
   image_members={Path(m.name).stem:m for m in sources.getmembers() if m.isfile() and m.name.lower().endswith(('.jpg','.jpeg','.png'))}
   for member in annotations:
    if not member.isfile() or not member.name.endswith('.json'):continue
    category=member.name.split('/')[1];counts[category]+=1
    if member.size>2_000_000:raise ValueError('Unexpected annotation size')
    raw=annotations.extractfile(member).read();label=json.loads(raw.decode('utf-8-sig'))
    qualities=sorted({a.get('attributes',{}).get('quality','unknown') for a in label.get('annotations',[])})
    quality=' / '.join(qualities)
    if sum(x['category']==category and x['quality']==quality for x in selected)>=2:continue
    image_member=image_members.get(Path(member.name).stem)
    if image_member is None:continue
    selected.append(dict(category=category,quality=quality,member=member.name,image_member=image_member.name,label=label,label_bytes=raw))
   for s in selected:
    m=sources.getmember(s['image_member'])
    if m.size>60_000_000:raise ValueError('Unexpected image size')
    raw=sources.extractfile(m).read();ident=f'sample_{len(records)+1:02d}'
    (out/(ident+'_original.jpg')).write_bytes(raw);(out/(ident+'_label.json')).write_bytes(s['label_bytes'])
    with Image.open(io.BytesIO(raw)) as image:
     raw_size=image.size;orientation=image.getexif().get(274,1);preview=ImageOps.exif_transpose(image).convert('RGB')
    size=preview.size;preview.thumbnail((1000,800));preview.save(out/(ident+'_preview.jpg'),quality=94)
    records.append(dict(id=ident,part=part,category=s['category'],sourceQuality=s['quality'],imageArchive=str(images),imageMember=s['image_member'],labelArchive=str(labels),labelMember=s['member'],imageSHA256=hashlib.sha256(raw).hexdigest(),labelSHA256=hashlib.sha256(s['label_bytes']).hexdigest(),rawSize=raw_size,displaySize=size,exif=orientation,annotations=s['label']['annotations']))
  distribution[part]=dict(counts)
  print('[PREVIEW]',part,len(selected),flush=True)
 report=dict(trainingOnly=True,finalTestUsed=False,sourceArchivesModified=False,selection='First two available images per source category/quality; convenience examples, not representative or evaluated',categoryCounts=distribution,samples=records)
 (out/'source.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 parts=[f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{title} 원본 표본</title><style>body{{font-family:sans-serif;margin:25px}}img{{max-width:900px;width:95%}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}article{{border-top:2px solid #aaa;padding:20px}}</style><h1>{title} 학습 원본 표본</h1><p>원래 학습 압축 파일에서 결함 유형·quality별 처음 찾은 두 장입니다. 전체 분포나 모델 성능을 대표하지 않습니다. 양품/불량품은 원본 해당 유형의 quality이며 사진 전체 정답으로 재확정하지 않았습니다. 사진을 누르면 EXIF를 보존한 원본을 엽니다. 주석 위치는 변환하지 않았습니다.</p>']
 for r in records:
  parts.append('<article><h2>'+html.escape(f'{r["id"]} — {r["part"]} / {r["category"]} / 원본 라벨: {r["sourceQuality"]}')+'</h2>'+f'<a href="{r["id"]}_original.jpg"><img src="{r["id"]}_preview.jpg"></a><p><a href="{r["id"]}_label.json">원본 JSON</a></p><details><summary>출처·크기·주석</summary><pre>'+html.escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre></details></article>')
 (out/'index.html').write_text('\n'.join(parts))
 sheet=Image.new('RGB',(1000,((len(records)+1)//2)*320),'white');draw=ImageDraw.Draw(sheet)
 for i,r in enumerate(records):
  with Image.open(out/(r['id']+'_preview.jpg')) as image:image.thumbnail((490,285));x=(i%2)*500;y=(i//2)*320;sheet.paste(image,(x,y+25));draw.text((x+5,y+5),r['id']+' '+{'배선':'WIRING','커넥터':'CONNECTOR','카울커버':'COWL COVER'}[r['part']],fill='black')
 sheet.save(out/'contact.jpg');print('[PREVIEW READY]',out/'index.html')
if __name__=='__main__':main()
