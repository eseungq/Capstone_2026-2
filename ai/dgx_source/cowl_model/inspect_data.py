"""Read cowl Training archive metadata/labels only; do not extract images or train."""
import csv,hashlib,json,tarfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'downloads/aihub/162.부품_품질_검사_영상_데이터(자동차)/01.데이터/1.Training'

def stat(p):s=p.stat();return dict(bytes=s.st_size,mtime_ns=s.st_mtime_ns)
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 images_path=BASE/'원천데이터/TS_6.카울커버.tar';labels_path=BASE/'라벨링데이터/TL_6.카울커버.tar';before={str(p):stat(p) for p in [images_path,labels_path]};out=ROOT/'outputs/cowl_inventory'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 print('[COWL INVENTORY]',out,flush=True);images={};duplicate_names=[]
 with tarfile.open(images_path,'r:') as archive:
  for m in archive:
   if m.isfile() and Path(m.name).suffix.lower() in ('.jpg','.jpeg','.png'):
    stem=Path(m.name).stem
    if stem in images:duplicate_names.append(m.name)
    images[stem]=dict(image_archive=str(images_path),image_member=m.name,image_offset=m.offset_data,image_bytes=m.size)
 records=[];errors=[];label_stems=set();duplicates=[]
 with tarfile.open(labels_path,'r:') as archive:
  for m in archive:
   if not m.isfile() or not m.name.endswith('.json'):continue
   stem=Path(m.name).stem
   if stem in label_stems:duplicates.append(m.name)
   label_stems.add(stem)
   try:
    if m.size>2_000_000:raise ValueError('Unexpected large label')
    raw=archive.extractfile(m).read();j=json.loads(raw.decode('utf-8-sig'));anns=j.get('annotations',[]);quality=sorted({a.get('attributes',{}).get('quality','unknown') for a in anns});parts=sorted({a.get('attributes',{}).get('part','unknown') for a in anns});categories={c['id']:c.get('name','unknown') for c in j.get('categories',[])};types=sorted({categories.get(a.get('category_id'),'unknown') for a in anns});image_info=j.get('images',[])
    if len(image_info)!=1:raise ValueError('Expected one image per label')
    info=image_info[0];linked=images.get(stem);cls={'양품':0,'불량품':1}.get(quality[0]) if len(quality)==1 else None
    issue='ok' if linked and parts==['카울커버'] and cls in (0,1) else 'hold_metadata_issue'
    records.append(dict(image_id=stem,**(linked or dict(image_archive=str(images_path),image_member='',image_offset='',image_bytes='')),label_archive=str(labels_path),label_member=m.name,label_sha256=hashlib.sha256(raw).hexdigest(),source_quality=' / '.join(quality),class_id=cls if cls is not None else '',part=' / '.join(parts),annotation_types=' / '.join(types),declared_width=info.get('width'),declared_height=info.get('height'),captured_at=info.get('date_captured'),annotation_image_id=info.get('id'),annotations=len(anns),has_bbox=any(bool(a.get('bbox')) for a in anns),has_segmentation=any(bool(a.get('segmentation')) for a in anns),label_filename_matches_member=Path(info.get('file_name','')).stem==stem,status=issue))
   except Exception as exc:errors.append(dict(label_member=m.name,error_type=type(exc).__name__))
   if len(label_stems)%2000==0:print('[COWL LABELS]',len(label_stems),flush=True)
 if not records:raise ValueError('No labels')
 with (out/'image_label_inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
 usable=[r for r in records if r['status']=='ok'];summary=dict(status='metadata_inventory_complete_not_training_ready',trainingOnly=True,imageMembers=len(images),labelMembers=len(label_stems),pairedImages=sum(bool(r['image_member']) for r in records),usableMetadataImages=len(usable),classCounts=dict(Counter(r['class_id'] for r in usable)),typeClassCounts={f'{t}/{q}':n for (t,q),n in Counter((r['annotation_types'],r['source_quality']) for r in usable).items()},imagesWithoutLabels=len(set(images)-label_stems),labelsWithoutImages=len(label_stems-set(images)),duplicateImageStems=duplicate_names,duplicateLabelStems=duplicates,metadataIssueImages=sum(r['status']!='ok' for r in records),filenameMismatchImages=sum(not r['label_filename_matches_member'] for r in records),bboxImages=sum(r['has_bbox'] for r in records),segmentationImages=sum(r['has_segmentation'] for r in records),captureDateRange=[min(r['captured_at'] for r in records if r['captured_at']),max(r['captured_at'] for r in records if r['captured_at'])],annotationImageIDCounts=dict(Counter(str(r['annotation_image_id']) for r in records)),errors=errors,archiveStats=before,sourceArchivesUnchanged=before=={str(p):stat(p) for p in [images_path,labels_path]},labelArchiveSHA256=hashlib.sha256(labels_path.read_bytes()).hexdigest(),imageBytesDecoded=False,duplicatePhotoAuditCompleted=False,splitCreated=False,trainingStarted=False,validationOrFinalArchiveRead=False,existingDoorOrFrameChanged=False,limitations=['Source labels are type-specific; not a verified full-cowl assembly certificate.','Metadata counts do not establish unique physical parts or usable framing.','No image content/EXIF/annotation coordinate validity or model/CAM performance has been verified.'])
 dump(out/'summary.json',summary);dump(ROOT/'cowl_model/latest_inventory.json',dict(directory=str(out),summary=str(out/'summary.json'),trainingReady=False));print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
