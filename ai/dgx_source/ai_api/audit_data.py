"""Read-only train/internal audit. No final-test access, training or relabeling."""
import argparse
import csv
import hashlib
import json
import random
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
from ai_api.verify_gpu import ROOT,dump

Image.MAX_IMAGE_PIXELS=120_000_000


def write_csv(path,rows,fields):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def difference_hash(image):
    small=image.convert('L').resize((9,8),Image.Resampling.LANCZOS);pixels=list(small.getdata());value=0
    for y in range(8):
        for x in range(8):value=(value<<1)|int(pixels[y*9+x]>pixels[y*9+x+1])
    return value


def inspect(row):
    result=dict(row);result['issues']=[]
    try:
        label=json.loads(Path(row['json_path']).read_text(encoding='utf-8-sig'));annotations=label.get('annotations',[])
        qualities={a.get('attributes',{}).get('quality') for a in annotations};parts={a.get('attributes',{}).get('part') for a in annotations}
        if qualities!={row['quality']}:result['issues'].append('source_quality_manifest_mismatch')
        if parts!={'도어'}:result['issues'].append('source_part_mismatch')
        if {'양품':0,'불량품':1}.get(row['quality'])!=int(row['class_id']):result['issues'].append('manifest_class_mismatch')
        with Image.open(row['image_path']) as im:
            result.update(width=im.width,height=im.height,exifOrientation=im.getexif().get(274,1))
        images=label.get('images',[])
        if len(images)!=1:result['issues'].append('source_image_metadata_count')
        else:
            info=images[0];result['captureDate']=str(info.get('date_captured',''))[:10]
            if (info.get('width'),info.get('height'))!=(result['width'],result['height']):result['issues'].append('label_image_size_mismatch')
            if info.get('file_name')!=Path(row['image_path']).name:result['issues'].append('label_image_name_mismatch')
        cats={c['id']:c.get('name',str(c['id'])) for c in label.get('categories',[])}
        result['defectTypes']=sorted({cats.get(a.get('category_id'),str(a.get('category_id'))) for a in annotations
                                     if a.get('attributes',{}).get('quality')=='불량품'})
        result['sha256']=sha(row['image_path'])
    except Exception as exc:result['issues'].append(type(exc).__name__+': '+str(exc))
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--visual-per-split',type=int,default=64);args=parser.parse_args()
    if not 2<=args.visual_per_split<=512:parser.error('visual-per-split must be 2..512')
    output=ROOT/'ai_api/verification'/('data_audit_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    rows=[];sources={}
    for split,name in [('train','door_train.csv'),('internal_validation','door_internal_validation.csv')]:
        path=ROOT/'outputs/manifests'/name;sources[split]=dict(path=str(path),sha256=sha(path))
        with path.open(encoding='utf-8-sig') as stream:
            rows.extend(dict(r,auditSplit=split) for r in csv.DictReader(stream))
    expected={'train':11554,'internal_validation':2039}
    if dict(Counter(r['auditSplit'] for r in rows))!=expected:raise ValueError('Unexpected audit split sizes')
    report=dict(result='running',finalTestUsed=False,training=False,labelsChanged=False,dataDeleted=False,manifests=sources,
                expectedImages=len(rows),processedImages=0,visualScope='sample candidates only; dHash does not establish identity or physical-part independence')
    dump(output/'summary.json',report);results=[]
    try:
        print('[AUDIT OUTPUT]',output,flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            for i,result in enumerate(pool.map(inspect,rows),1):
                results.append(result)
                if i%500==0 or i==len(rows):
                    report['processedImages']=i;dump(output/'summary.json',report);print('[AUDIT]',i,'/',len(rows),flush=True)
        issues=[dict(split=r['auditSplit'],image_path=r['image_path'],issues='; '.join(r['issues'])) for r in results if r['issues']]
        write_csv(output/'label_metadata_issues.csv',issues,['split','image_path','issues'])
        groups=defaultdict(list)
        for r in results:
            if r.get('sha256'):groups[r['sha256']].append(r)
        exact=[]
        for digest,group in groups.items():
            if len(group)>1:
                for r in group:exact.append(dict(sha256=digest,split=r['auditSplit'],image_path=r['image_path'],class_id=r['class_id'],cross_split=len({x['auditSplit'] for x in group})>1))
        write_csv(output/'exact_duplicate_images.csv',exact,['sha256','split','image_path','class_id','cross_split'])
        paths={split:{str(Path(r['image_path']).resolve()) for r in results if r['auditSplit']==split} for split in expected}
        names={split:{Path(p).name.casefold() for p in values} for split,values in paths.items()}
        distribution=[]
        for split in expected:
            counts=Counter(t for r in results if r['auditSplit']==split for t in r.get('defectTypes',[]))
            distribution.extend(dict(split=split,defect_type=kind,images=count) for kind,count in counts.items())
        write_csv(output/'image_defect_type_counts.csv',distribution,['split','defect_type','images'])
        dated=defaultdict(Counter)
        for r in results:
            if r.get('captureDate'):dated[r['captureDate']][r['auditSplit']]+=1
        write_csv(output/'capture_date_overlap.csv',[dict(date=date,train=c['train'],internal_validation=c['internal_validation']) for date,c in sorted(dated.items()) if c['train'] and c['internal_validation']],['date','train','internal_validation'])
        hash_rows=[dict(split=r['auditSplit'],image_path=r['image_path'],sha256=r.get('sha256',''),bytes=Path(r['image_path']).stat().st_size) for r in results]
        write_csv(output/'image_hashes.csv',hash_rows,['split','image_path','sha256','bytes'])
        rng=random.Random(20261017);visual=[];visual_errors=[]
        for split in expected:
            candidates=sorted([r for r in results if r['auditSplit']==split and not r['issues']],key=lambda r:r['image_path'])
            for r in rng.sample(candidates,min(len(candidates),args.visual_per_split)):
                try:
                    with Image.open(r['image_path']) as im:corrected=ImageOps.exif_transpose(im).convert('RGB')
                    digest=difference_hash(corrected);corrected.thumbnail((500,500));ident=f'visual_{len(visual):03d}';corrected.save(output/(ident+'.jpg'),quality=85)
                    visual.append(dict(id=ident,image_path=r['image_path'],split=split,hash=digest,width=r['width'],height=r['height']))
                except Exception as exc:visual_errors.append(dict(image_path=r['image_path'],error=str(exc)))
            print('[VISUAL SAMPLE]',split,len(visual),flush=True)
        similar=[]
        for i,a in enumerate(visual):
            for b in visual[i+1:]:
                if a['split']==b['split']:continue
                distance=(a['hash']^b['hash']).bit_count()
                if distance<=8:similar.append(dict(a=a['id'],b=b['id'],distance=distance,image_a=a['image_path'],image_b=b['image_path']))
        write_csv(output/'similarity_candidates.csv',similar,['a','b','distance','image_a','image_b'])
        dump(output/'visual_samples.json',visual)
        report.update(result='complete',processedImages=len(results),labelMetadataIssueImages=len(issues),
            exactDuplicateGroups=sum(len(v)>1 for v in groups.values()),crossSplitExactDuplicateGroups=sum(len({r['auditSplit'] for r in v})>1 for v in groups.values()),
            hashedImages=sum(bool(r.get('sha256')) for r in results),pathOverlap=len(paths['train']&paths['internal_validation']),filenameOverlap=len(names['train']&names['internal_validation']),
            visualImages=len(visual),visualErrors=visual_errors,crossSplitVisualCandidates=len(similar),
            samePhysicalPartIndependence='not established',captureDateOverlapMeaning='same capture date is not proof of same part or leakage',
            defectTypeCountMeaning='unique defect categories per image with source quality DEFECT; multi-type images can appear in multiple categories')
        import html
        parts=['<!doctype html><meta charset="utf-8"><title>데이터 감사</title><h1>학습·내부 검증 데이터 감사</h1><p>후보는 사람이 확인해야 합니다. 같은 실물·유사 사진의 독립성은 미확정입니다. 데이터·라벨은 수정하지 않았습니다.</p><pre>'+html.escape(json.dumps(report,ensure_ascii=False,indent=2))+'</pre>']
        for pair in sorted(similar,key=lambda p:p['distance']):
            parts.append('<h2>유사 후보 거리 '+str(pair['distance'])+'</h2>')
            for ident in (pair['a'],pair['b']):parts.append(f'<img style="max-width:45%" src="{ident}.jpg">')
            parts.append('<pre>'+html.escape(json.dumps(pair,ensure_ascii=False,indent=2))+'</pre>')
        (output/'index.html').write_text('\n'.join(parts))
    except BaseException as exc:
        report.update(result='failed_or_interrupted',failureType=type(exc).__name__,failure=str(exc));raise
    finally:
        dump(output/'summary.json',report);print('[AUDIT REPORT]',output/'summary.json',flush=True)


if __name__=='__main__':main()
