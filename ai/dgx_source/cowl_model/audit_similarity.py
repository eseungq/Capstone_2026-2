"""Training-only full-pool image fingerprints and near-duplicate candidates, no split."""
import argparse,csv,hashlib,io,json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1]
def dhash(image):
 # Same 64-bit horizontal difference hash as ai_api.audit_data.difference_hash.
 pixels=list(image.convert('L').resize((9,8),Image.Resampling.LANCZOS).getdata());value=0
 for y in range(8):
  for x in range(8):value=(value<<1)|int(pixels[y*9+x]>pixels[y*9+x+1])
 return value
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--limit',type=int,default=256,help='Pilot images; use --all for the whole Training inventory');ap.add_argument('--all',action='store_true');ap.add_argument('--resume',type=Path);args=ap.parse_args()
 if args.limit<1:ap.error('limit must be positive')
 inv=Path(json.loads((ROOT/'cowl_model/latest_inventory.json').read_text())['directory'])/'image_label_inventory.csv';inv_hash=hashlib.sha256(inv.read_bytes()).hexdigest();rows=list(csv.DictReader(inv.open(encoding='utf-8-sig')));rows=[r for r in rows if r['status']=='ok'];rows.sort(key=lambda r:hashlib.sha256(('cowl-sim-v1:'+r['image_id']).encode()).hexdigest())
 out=args.resume or ROOT/'outputs/cowl_similarity'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True,exist_ok=bool(args.resume));(out/'thumbs').mkdir(exist_ok=True)
 records=[]
 if args.resume:
  old=json.loads((out/'summary.json').read_text())
  if old['inventory_sha256']!=inv_hash or old['script_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():raise ValueError('Resume inventory/code differs')
  records=[json.loads(l) for l in (out/'fingerprints.jsonl').read_text().splitlines()]
 done={r['image_id'] for r in records};todo=[r for r in rows if r['image_id'] not in done]
 if not args.all:todo=todo[:args.limit]
 summary=dict(status='running',inventory=str(inv),inventory_sha256=inv_hash,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),total_images=len(rows),trainingOnly=True,finalTestUsed=False,splitCreated=False,sourceLabelsChanged=False,trainingStarted=False,search='All pairs among successfully fingerprinted images, irrespective of quality/type; dHash64<=8 candidate threshold; exact display RGB hash separately indexed.',limitations=['Candidates are not confirmed same photos/parts.','Full-image dHash can miss crop/angle/lighting variants and give false positives.','Pilot does not cover the full inventory.','Grouping and independent splits remain pending.'])
 def save():
  summary.update(fingerprinted=len(records),decode_errors=sum('error' in r for r in records));(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 save();print('[COWL SIMILARITY]',out,flush=True)
 try:
  with (out/'fingerprints.jsonl').open('a') as stream:
   for n,r in enumerate(todo,1):
    try:
     with open(r['image_archive'],'rb') as f:f.seek(int(r['image_offset']));raw=f.read(int(r['image_bytes']))
     with Image.open(io.BytesIO(raw)) as im:display=ImageOps.exif_transpose(im).convert('RGB')
     result=dict(image_id=r['image_id'],type=r['annotation_types'],quality=r['source_quality'],width=display.width,height=display.height,source_sha256=hashlib.sha256(raw).hexdigest(),display_sha256=hashlib.sha256(str(display.size).encode()+display.tobytes()).hexdigest(),dhash64=str(dhash(display)))
     display.thumbnail((500,350));display.save(out/'thumbs'/f'{r["image_id"]}.jpg',quality=85)
    except Exception as exc:result=dict(image_id=r['image_id'],error=type(exc).__name__)
    records.append(result);stream.write(json.dumps(result,ensure_ascii=False)+'\n');stream.flush()
    if n%50==0:save();print('[COWL FINGERPRINT]',len(records),'/',len(rows),flush=True)
  index=defaultdict(set);exact=defaultdict(set);count=0;exact_count=0
  # Nine disjoint bit segments guarantee candidate retrieval for Hamming distance <=8.
  parts=[];offset=0
  for k in range(9):width=64//9+int(k<64%9);parts.append((offset,(1<<width)-1));offset+=width
  with (out/'candidates.jsonl').open('w') as f:
   for i,a in enumerate(records):
    if 'error' in a:continue
    h=int(a['dhash64']);possible=set(exact[a['display_sha256']])
    for k,(shift,mask) in enumerate(parts):possible.update(index[(k,(h>>shift)&mask)])
    for j in sorted(possible):
     b=records[j];dist=(h^int(b['dhash64'])).bit_count();same=a['display_sha256']==b['display_sha256']
     if dist<=8 or same:
      f.write(json.dumps(dict(a=a['image_id'],b=b['image_id'],dhash_distance=dist,exact_display_pixels=same,cross_quality=a['quality']!=b['quality'],cross_type=a['type']!=b['type']))+'\n');count+=1;exact_count+=int(same)
    for k,(shift,mask) in enumerate(parts):index[(k,(h>>shift)&mask)].add(i)
    exact[a['display_sha256']].add(i)
  summary.update(status='complete_candidates_unreviewed' if len(records)==len(rows) else 'pilot_complete_not_full_audit',candidate_pairs=count,exact_display_pairs=exact_count)
 except BaseException:
  summary['status']='failed_or_interrupted';raise
 finally:save()
 (ROOT/'cowl_model/latest_similarity.json').write_text(json.dumps(dict(directory=str(out),summary=str(out/'summary.json')),indent=2));print('[COWL SIMILARITY RESULT]',summary['status'],count,flush=True)
if __name__=='__main__':main()
