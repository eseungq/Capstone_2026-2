"""Small training-archive galleries for all eleven parts; no full extraction."""
import hashlib,html,io,json,tarfile
from contextlib import ExitStack
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'downloads/aihub/162.부품_품질_검사_영상_데이터(자동차)/01.데이터/1.Training'
PARTS=[('1','도어'),('2','라디에이터_그릴'),('3','루프사이드'),('4','배선'),('5','범퍼'),('6','카울커버'),('7','커넥터'),('8','테일_램프'),('9','프레임'),('10','헤드_램프'),('11','휀더')]
def main():
 out=ROOT/'ai_api/verification'/('all_parts_preview_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir();report=[]
 print('[ALL PARTS]',out,flush=True)
 index=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>자동차 부품 원본 둘러보기</title><style>body{font-family:sans-serif;margin:28px}a{line-height:2}img{max-width:95%}</style><h1>자동차 부품11종 원본 표본</h1><p>학습 압축 파일에서 부품당 최대6장만 별도 복사했습니다. 전체 분포·라벨 정확도·모델 성능을 대표하지 않습니다. 원본 archive와 최종 시험은 변경/사용하지 않았습니다. 부품 이름을 누르면 원본 사진과 JSON을 볼 수 있습니다.</p>']
 for code,part in PARTS:
  folder=out/f'part_{int(code):02d}';folder.mkdir();label_path=BASE/'라벨링데이터'/f'TL_{code}.{part}.tar';archive_paths=sorted((BASE/'원천데이터').glob(f'TS_{code}.{part}*.tar'))
  if not archive_paths:raise FileNotFoundError(part)
  with ExitStack() as stack:
   archives=[stack.enter_context(tarfile.open(p)) for p in archive_paths];labels=stack.enter_context(tarfile.open(label_path))
   images={}
   for path,archive in zip(archive_paths,archives):
    for member in archive:
     if member.isfile() and member.name.lower().endswith(('.jpg','.jpeg','.png')):
      stem=Path(member.name).stem
      if stem in images:raise ValueError('Duplicate archive stem')
      images[stem]=(path,archive,member)
   buckets={}
   for member in labels:
    if not member.isfile() or not member.name.endswith('.json'):continue
    category=member.name.split('/')[1]
    if {q for c,q in buckets if c==category}>={'양품','불량품'}:continue
    if member.size>2_000_000:raise ValueError('Unexpected annotation size')
    raw=labels.extractfile(member).read();label=json.loads(raw.decode('utf-8-sig'));quality=' / '.join(sorted({a.get('attributes',{}).get('quality','unknown') for a in label.get('annotations',[])}))
    stem=Path(member.name).stem
    if (category,quality) not in buckets and stem in images:buckets[(category,quality)]=(member.name,raw,label,images[stem])
   # Offer at least one view per category first, then complementary quality.
   selected=sorted(buckets,key=lambda k:(k[1]!='불량품',k[0],k[1]))[:6]
   samples=[]
   for i,(category,quality) in enumerate(selected,1):
    label_member,label_raw,label,(archive_path,archive,member)=buckets[(category,quality)]
    if member.size>60_000_000:raise ValueError('Unexpected image size')
    raw=archive.extractfile(member).read();ident=f'sample_{i:02d}';(folder/f'{ident}_original.jpg').write_bytes(raw);(folder/f'{ident}_label.json').write_bytes(label_raw)
    with Image.open(io.BytesIO(raw)) as image:raw_size=image.size;display=ImageOps.exif_transpose(image).convert('RGB')
    size=display.size;display.thumbnail((1200,1000));display.save(folder/f'{ident}_preview.jpg',quality=94)
    samples.append(dict(id=ident,part=part.replace('_',' '),category=category,sourceQuality=quality,imageArchive=str(archive_path),imageMember=member.name,labelArchive=str(label_path),labelMember=label_member,imageSHA256=hashlib.sha256(raw).hexdigest(),labelSHA256=hashlib.sha256(label_raw).hexdigest(),rawSize=raw_size,displaySize=size))
  data=dict(trainingOnly=True,finalTestUsed=False,sourceArchivesModified=False,sampleCount=len(samples),availableCategoryQualityPairs=[dict(category=c,quality=q) for c,q in sorted(buckets)],selection='one per category/quality, capped6; convenience examples only',samples=samples);(folder/'source.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
  parts=[f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{part} 원본 표본</title><style>body{{font-family:sans-serif;margin:24px}}img{{width:95%;max-width:1200px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style><p><a href="../index.html">전체 부품 목록</a></p><h1>{part.replace("_"," ")} — {len(samples)}장</h1><p>quality는 원본의 해당 불량 유형에 대한 기록입니다. 사진 전체 정답으로 새로 확정하지 않았습니다. 사진을 누르면 원본을 엽니다.</p>']
  sheet=Image.new('RGB',(1000,((len(samples)+1)//2)*340),'white');draw=ImageDraw.Draw(sheet)
  for i,r in enumerate(samples):
   parts.append('<h2>'+html.escape(r['id']+' / '+r['category']+' / '+r['sourceQuality'])+'</h2><a href="'+r['id']+'_original.jpg"><img src="'+r['id']+'_preview.jpg"></a><p><a href="'+r['id']+'_label.json">원본 JSON</a></p><details><summary>출처·크기·해시</summary><pre>'+html.escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre></details>')
   with Image.open(folder/(r['id']+'_preview.jpg')) as image:image.thumbnail((490,305));x=i%2*500;y=i//2*340;sheet.paste(image,(x,y+25));draw.text((x+5,y+5),f'PART {code} / '+r['id'],fill='black')
  (folder/'index.html').write_text('\n'.join(parts));sheet.save(folder/'contact.jpg')
  summary=dict(part=part.replace('_',' '),folder=folder.name,sampleCount=len(samples),categories=sorted({s['category'] for s in samples}));report.append(summary)
  index.append('<h2><a href="'+folder.name+'/index.html">'+html.escape(summary['part'])+' — '+str(len(samples))+'장</a></h2><p>'+html.escape(' / '.join(summary['categories']))+'</p><a href="'+folder.name+'/index.html"><img style="max-width:650px" src="'+folder.name+'/contact.jpg"></a>')
  print('[PART READY]',part,len(samples),flush=True)
  (out/'index.html').write_text('\n'.join(index))
 dump=dict(status='complete',trainingOnly=True,finalTestUsed=False,sourceArchivesModified=False,parts=report,totalSamples=sum(r['sampleCount'] for r in report));(out/'summary.json').write_text(json.dumps(dump,ensure_ascii=False,indent=2));print('[ALL PARTS READY]',out/'index.html',flush=True)
if __name__=='__main__':main()
