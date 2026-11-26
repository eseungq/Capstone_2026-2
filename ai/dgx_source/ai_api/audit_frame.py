"""Read-only frame Training archive audit; no split, inference or training."""
import csv,hashlib,html,io,json,math,tarfile,time,os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
from ai_api.duplicate_groups import dump
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'downloads/aihub/162.부품_품질_검사_영상_데이터(자동차)/01.데이터/1.Training'
Image.MAX_IMAGE_PIXELS=120_000_000

def label_info(label,member):
 annotations=label.get('annotations',[]);categories={c['id']:c['name'] for c in label.get('categories',[])}
 qualities=sorted({a.get('attributes',{}).get('quality','unknown') for a in annotations})
 types=sorted({categories.get(a.get('category_id'),'unknown') for a in annotations})
 parts=sorted({a.get('attributes',{}).get('part','unknown') for a in annotations})
 issues=[]
 if len(label.get('images',[]))!=1:issues.append('image_metadata_count')
 if not annotations:issues.append('empty_annotations')
 if not set(qualities)<={'양품','불량품'} or len(qualities)!=1:issues.append('mixed_or_unknown_quality')
 if parts!=['프레임']:issues.append('part_mismatch')
 return dict(labelMember=member,quality=' / '.join(qualities),types=' / '.join(types),parts=parts,issues=issues,metadata=label.get('images',[{}])[0] if label.get('images') else {},annotations=annotations)

def prefetched_images(archive):
 fd=archive.fileobj.fileno()
 def read(member):
  data=os.pread(fd,member.size,member.offset_data)
  if len(data)!=member.size:raise OSError('Short archive member read')
  return data
 with ThreadPoolExecutor(max_workers=4) as pool:
  pending=deque()
  for member in archive:
   if not member.isfile() or not member.name.lower().endswith(('.jpg','.jpeg','.png')):continue
   pending.append((member,pool.submit(read,member)))
   if len(pending)>=8:
    m,future=pending.popleft();yield m,future.result()
  while pending:
   m,future=pending.popleft();yield m,future.result()

def main():
 output=ROOT/'ai_api/verification'/('frame_audit_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
 labels_path=BASE/'라벨링데이터/TL_9.프레임.tar';images_paths=sorted((BASE/'원천데이터').glob('TS_9.프레임_*.tar'))
 sources=[labels_path]+images_paths;stats_before={str(p):dict(bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for p in sources}
 report=dict(status='running',scope='Training frame only; all image bytes hashed and headers read, not full pixel decoding',validationArchivesRead=False,doorFinalTestUsed=False,trainingStarted=False,modelRun=False,labelsChanged=False,splitAssigned=False,processedImages=0)
 dump(output/'summary.json',report);print('[FRAME AUDIT]',output,flush=True)
 labels={};label_errors=[];label_counts=Counter();rows=[];samples=[];sample_counts=Counter();seen=Counter();digests=defaultdict(list);start=time.monotonic()
 try:
  with tarfile.open(labels_path) as archive:
   for member in archive:
    if not member.isfile() or not member.name.endswith('.json'):continue
    try:
     raw=archive.extractfile(member).read();label=json.loads(raw.decode('utf-8-sig'));info=label_info(label,member.name);info['labelSHA256']=hashlib.sha256(raw).hexdigest();info['rawLabel']=raw
     key=Path(member.name).stem
     if key in labels:raise ValueError('Duplicate JSON stem')
     labels[key]=info;label_counts[(info['types'],info['quality'])]+=1
    except Exception as exc:label_errors.append(dict(member=member.name,error=repr(exc)))
  dump(output/'label_stage_counts.json',[dict(sourceType=k[0],sourceQuality=k[1],labels=v) for k,v in sorted(label_counts.items())]);print('[FRAME LABELS]',len(labels),'errors',len(label_errors),flush=True)
  for archive_path in images_paths:
   with tarfile.open(archive_path,mode='r:') as archive:
    for member,raw in prefetched_images(archive):
     if not member.isfile() or not member.name.lower().endswith(('.jpg','.jpeg','.png')):continue
     key=Path(member.name).stem;seen[key]+=1;info=labels.get(key);issues=list(info['issues']) if info else ['missing_label']
     row=dict(imageArchive=str(archive_path),imageMember=member.name,bytes=member.size,labelMember=info['labelMember'] if info else '',sourceQuality=info['quality'] if info else '',sourceTypes=info['types'] if info else '',imageSHA256='',width='',height='',exif='',declaredWidth='',declaredHeight='',rawSizeMatches='',displaySizeMatches='',bboxOutsideDeclared=0,issues='')
     try:
      digest=hashlib.sha256(raw).hexdigest();row['imageSHA256']=digest
      with Image.open(io.BytesIO(raw)) as image:width,height=image.size;orientation=image.getexif().get(274,1)
      row.update(width=width,height=height,exif=orientation)
      display=(height,width) if orientation in (5,6,7,8) else (width,height)
      if info:
       m=info['metadata'];declared=(m.get('width'),m.get('height'));row.update(declaredWidth=declared[0],declaredHeight=declared[1],rawSizeMatches=declared==(width,height),displaySizeMatches=declared==display)
       if m.get('file_name')!=Path(member.name).name:issues.append('label_filename_mismatch')
       if declared!=(width,height):issues.append('raw_size_mismatch')
       if declared!=display:issues.append('display_size_mismatch')
       for a in info['annotations']:
        box=a.get('bbox')
        if box is None:continue
        if not isinstance(box,list) or len(box)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in box):issues.append('invalid_bbox');continue
        x,y,w,h=box
        if w<0 or h<0 or x<0 or y<0 or not all(isinstance(v,(int,float)) for v in declared) or x+w>declared[0]+1 or y+h>declared[1]+1:row['bboxOutsideDeclared']+=1
       if row['bboxOutsideDeclared']:issues.append('bbox_outside_declared')
       sample_key=(info['types'],info['quality'])
       if sample_counts[sample_key]<2 and info['quality'] in ('양품','불량품'):
        ident=f'sample_{len(samples)+1:02d}';(output/(ident+'_original.jpg')).write_bytes(raw);(output/(ident+'_label.json')).write_bytes(info['rawLabel'])
        with Image.open(io.BytesIO(raw)) as image:full=ImageOps.exif_transpose(image).convert('RGB')
        small=ImageOps.pad(full,(224,224),method=Image.Resampling.BICUBIC,color=(124,116,104));small.save(output/(ident+'_224.png'))
        full.thumbnail((1200,1000));full.save(output/(ident+'_preview.jpg'),quality=94)
        overlay=full.copy();draw=ImageDraw.Draw(overlay)
        for a in info['annotations']:
         box=a.get('bbox')
         if isinstance(box,list) and len(box)==4 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in box) and all(isinstance(v,(int,float)) and v>0 for v in declared):
          x,y,w,h=box;sx,sy=full.width/declared[0],full.height/declared[1];draw.rectangle((x*sx,y*sy,(x+w)*sx,(y+h)*sy),outline='red',width=3)
        overlay.save(output/(ident+'_bbox_display_hypothesis.jpg'),quality=94)
        samples.append(dict(id=ident,**row,labelSHA256=info['labelSHA256'],displaySize=display,overlayInterpretation='JSON declared coordinates scaled directly into EXIF display; hypothesis only, not verified coordinate convention'))
        sample_counts[sample_key]+=1
      digests[digest].append(len(rows))
     except Exception as exc:issues.append('image_read_or_sample_error:'+repr(exc))
     row['issues']=';'.join(issues);rows.append(row)
     if len(rows)%1000==0:
      report['processedImages']=len(rows);dump(output/'summary.json',report);print('[FRAME IMAGES]',len(rows),f'{time.monotonic()-start:.0f}s',flush=True)
  def write(name,items,fields):
   with (output/name).open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(items)
  write('image_inventory.csv',rows,list(rows[0]))
  write('category_quality_counts.csv',[dict(sourceType=k[0],sourceQuality=k[1],labels=v) for k,v in sorted(label_counts.items())],['sourceType','sourceQuality','labels'])
  duplicate_groups=[dict(sha256=h,members=[rows[i] for i in indices],qualityConflict=len({rows[i]['sourceQuality'] for i in indices})>1) for h,indices in digests.items() if len(indices)>1]
  dump(output/'exact_duplicate_groups.json',duplicate_groups);dump(output/'label_errors.json',label_errors)
  dump(output/'missing_image_labels.json',[dict(stem=k,labelMember=v['labelMember']) for k,v in labels.items() if k not in seen])
  dump(output/'sample_sources.json',samples)
  parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>프레임 데이터 첫 점검</title><style>body{font-family:sans-serif;margin:28px}img{max-width:90%;vertical-align:top}article{border-top:2px solid #aaa;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>프레임 유형별 원본·224 입력 비교</h1><p>학습 원본에서 유형/quality별 처음 찾은2장입니다. 분류·추론·Grad-CAM을 실행하지 않았습니다.224는 기존 도어 기준 전처리의 RGB 시각화 비교이며 프레임 학습 입력으로 확정한 것은 아닙니다.빨간bbox는 표시 좌표 가설이라 실제 결함 경계나 좌표 복원 정답으로 보지 않습니다.원본을 눌러 확대하고 정답 유형별로 어떤 부위를 봐야 하는지 확인하세요.</p>']
  for s in samples:
   parts.append('<article><h2>'+s['id']+' — '+html.escape(s['sourceTypes']+' / '+s['sourceQuality'])+'</h2><a href="'+s['id']+'_original.jpg"><img style="width:65%" src="'+s['id']+'_preview.jpg"></a><img width="224" height="224" src="'+s['id']+'_224.png"><details><summary>주석 표시 가설·출처</summary><img src="'+s['id']+'_bbox_display_hypothesis.jpg"><pre>'+html.escape(json.dumps(s,ensure_ascii=False,indent=2))+'</pre><a href="'+s['id']+'_label.json">원본 JSON</a></details></article>')
  (output/'index.html').write_text('\n'.join(parts))
  unchanged=all(p.stat().st_size==stats_before[str(p)]['bytes'] and p.stat().st_mtime_ns==stats_before[str(p)]['mtime_ns'] for p in sources)
  report.update(status='complete' if not label_errors and unchanged else 'complete_with_issues',labelFiles=len(labels),labelErrors=len(label_errors),processedImages=len(rows),imageBytesRead=sum(r['bytes'] for r in rows),imageErrors=sum('image_read_or_sample_error' in r['issues'] for r in rows),issueImages=sum(bool(r['issues']) for r in rows),issues=dict(Counter(issue for r in rows for issue in r['issues'].split(';') if issue)),missingImages=sum(k not in seen for k in labels),missingLabels=sum('missing_label' in r['issues'] for r in rows),repeatedImageStems=sum(n>1 for n in seen.values()),exactDuplicateGroups=len(duplicate_groups),qualityConflictGroups=sum(g['qualityConflict'] for g in duplicate_groups),samples=len(samples),archiveStatsUnchanged=unchanged,archiveStats=stats_before,labelArchiveSHA256=hashlib.sha256(labels_path.read_bytes()).hexdigest(),scriptSHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),similarOrSamePhysicalPartIndependence='not established',sourceQualityMeaning='per source annotation/type; not finalized whole-frame binary label')
 except BaseException as exc:report.update(status='failed_or_interrupted',failure=repr(exc));raise
 finally:dump(output/'summary.json',report);print('[FRAME REPORT]',output/'summary.json',flush=True)
if __name__=='__main__':main()
