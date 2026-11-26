"""Read-only frame train/selection similarity audit; no final/reserved images or model use."""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timezone
from functools import lru_cache
import hashlib
import html
import io
import json
from pathlib import Path
import time
from PIL import Image
from frame_model.check import ROOT,read_image
from frame_model.experiments import load_plan
from frame_model.train import dump
from ai_api.audit_data import difference_hash
from ai_api.rank_similarity import features,metrics


def segments(bits,radius):
    parts=radius+1;offset=0;result=[]
    for index in range(parts):
        width=bits//parts+int(index<bits%parts);result.append((offset,(1<<width)-1));offset+=width
    return result


class HashIndex:
    def __init__(self,values,bits,radius):
        self.parts=segments(bits,radius);self.table=defaultdict(list)
        for index,value in enumerate(values):
            for part,(shift,mask) in enumerate(self.parts):self.table[(part,(value>>shift)&mask)].append(index)
    def query(self,value):
        found=set()
        for part,(shift,mask) in enumerate(self.parts):found.update(self.table.get((part,(value>>shift)&mask),[]))
        return found


def fingerprint(row,out):
    try:
        display,_=read_image(row)
        h=difference_hash(display);v=difference_hash(display.transpose(Image.Transpose.TRANSPOSE))
        gray=list(display.convert('L').resize((8,8),Image.Resampling.LANCZOS).getdata());mean=sum(gray)/64;a=0
        for pixel in gray:a=(a<<1)|int(pixel>=mean)
        pixel_sha=hashlib.sha256(str(display.size).encode()+display.tobytes()).hexdigest()
        thumb=display.resize((64,64),Image.Resampling.LANCZOS);thumb.save(out/'thumbs'/f"{row['image_id']}.png")
        return {'image_id':row['image_id'],'role':row['split'],'type':row['defect_type'],'class_id':row['class_id'],'group_id':row['group_id'],'width':display.width,'height':display.height,'dhash64':str(h),'dual_hash128':str((h<<64)|v),'average_hash64':str(a),'display_pixel_sha256':pixel_sha}
    except Exception as exc:return {'image_id':row['image_id'],'error_type':type(exc).__name__,'error_message':str(exc)[:250]}


def rank_pairs(records,out):
    train=sorted([r for r in records if r.get('role')=='train' and 'error_type' not in r],key=lambda r:r['image_id'])
    valid=sorted([r for r in records if r.get('role')=='model_selection' and 'error_type' not in r],key=lambda r:r['image_id'])
    horizontal=[int(r['dhash64']) for r in train];dual=[int(r['dual_hash128']) for r in train]
    hi=HashIndex(horizontal,64,8);di=HashIndex(dual,128,12)
    exact=defaultdict(list)
    for index,row in enumerate(train):exact[row['display_pixel_sha256']].append(index)
    @lru_cache(maxsize=4096)
    def cached(ident):
        with Image.open(out/'thumbs'/f'{ident}.png') as image:return features(image)
    count=0;affected=set();groups=set();cross_quality=0;pixel_exact=0;ranked=[]
    with (out/'similarity_candidates.jsonl').open('w') as stream:
        for number,a in enumerate(valid,1):
            ah=int(a['dhash64']);ad=int(a['dual_hash128']);possible=hi.query(ah)|di.query(ad)|set(exact.get(a['display_pixel_sha256'],[]))
            for index in sorted(possible):
                b=train[index];hd=(ah^horizontal[index]).bit_count();dd=(ad^dual[index]).bit_count();same_pixels=a['display_pixel_sha256']==b['display_pixel_sha256']
                if not (hd<=8 or dd<=12 or same_pixels):continue
                fa=cached(a['image_id']);fb=cached(b['image_id'])
                # Rank on thumbnails but use original EXIF display aspect ratio.
                fa=(fa[0],fa[1],a['width']/a['height']);fb=(fb[0],fb[1],b['width']/b['height']);m=metrics(fa,fb)
                pair={'validation_image':a['image_id'],'train_image':b['image_id'],'dhash64_distance':hd,'dual128_distance':dd,'average64_distance':(int(a['average_hash64'])^int(b['average_hash64'])).bit_count(),'exact_display_pixels':same_pixels,'same_source_quality':a['class_id']==b['class_id'],'validation_type':a['type'],'train_type':b['type'],'validation_group':a['group_id'],'train_group':b['group_id'],**m}
                stream.write(json.dumps(pair,ensure_ascii=False)+'\n');count+=1;affected.add(a['image_id']);groups.add((a['group_id'],b['group_id']));cross_quality+=int(not pair['same_source_quality']);pixel_exact+=int(same_pixels)
                ranked.append(pair)
                if len(ranked)>10000:ranked=sorted(ranked,key=lambda p:(not p['exact_display_pixels'],p['rankScore'],p['validation_image'],p['train_image']))[:2000]
            if number%250==0:print('[SIMILARITY SEARCH]',number,'/',len(valid),'candidate_pairs',count,flush=True)
    best=sorted(ranked,key=lambda p:(not p['exact_display_pixels'],p['rankScore'],p['validation_image'],p['train_image']))
    gallery=[];per_image=Counter();seen_groups=set()
    for p in best:
        group=(p['validation_group'],p['train_group'])
        if per_image[p['validation_image']]>=2 or group in seen_groups:continue
        gallery.append(p);per_image[p['validation_image']]+=1;seen_groups.add(group)
        if len(gallery)==50:break
    dump(out/'gallery_candidates.json',gallery)
    return {'candidate_pairs':count,'validation_images_with_candidates':len(affected),'candidate_group_pairs':len(groups),'cross_source_quality_pairs':cross_quality,'exact_display_pixel_pairs':pixel_exact,'gallery_pairs':len(gallery),'train_images_searched':len(train),'validation_images_searched':len(valid)}


def render_gallery(out,source):
    pairs=json.loads((out/'gallery_candidates.json').read_text());parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>프레임 분할 간 유사 사진 후보</title><style>body{font:17px sans-serif;max-width:1400px;margin:20px auto}section{border-top:1px solid #aaa;margin:20px 0}img{max-width:48%;vertical-align:top}pre{white-space:pre-wrap}</style><h1>학습·내부 검증 유사 사진 후보</h1><p>자동 유사 후보입니다. 같은 실물이나 분할 누수 확정이 아니며 원본/정답/분할은 변경하지 않았습니다. 왼쪽 내부 검증·오른쪽 학습입니다. 썸네일 순위 상위 중 사진/촬영 그룹 반복을 줄인 최대50쌍이며 전체 후보는JSONL에 보존합니다.</p>']
    for index,pair in enumerate(pairs,1):
        parts.append('<section><h2>후보 '+str(index)+'</h2><pre>'+html.escape(json.dumps(pair,ensure_ascii=False,indent=2))+'</pre>')
        for role,key in [('validation','validation_image'),('train','train_image')]:
            ident=pair[key];path=out/'gallery'/f'{ident}.jpg'
            if not path.exists():
                display,_=read_image(source[ident]);display.thumbnail((900,700));display.save(path,quality=90)
            parts.append('<img src="gallery/'+ident+'.jpg" alt="'+role+'">')
        parts.append('</section>')
    (out/'index.html').write_text('\n'.join(parts))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path);parser.add_argument('--resume',type=Path);parser.add_argument('--limit',type=int);parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    if not 1<=args.workers<=8 or args.limit is not None and args.limit<1:parser.error('Invalid workers/limit')
    path=args.plan or Path(json.loads((ROOT/'frame_model/latest_experiment_plan.json').read_text())['plan'])
    _,_,experiments=load_plan(path);tables=experiments['unified'][1];source={r['image_id']:r for rows in tables.values() for r in rows}
    out=args.resume or ROOT/'outputs/frame_similarity'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True,exist_ok=bool(args.resume));(out/'thumbs').mkdir(exist_ok=True);(out/'gallery').mkdir(exist_ok=True)
    plan_sha=hashlib.sha256(path.read_bytes()).hexdigest();records=[]
    if args.resume:
        previous=json.loads((out/'summary.json').read_text())
        if previous['plan_sha256']!=plan_sha:raise ValueError('Resume plan differs')
        # A complete line is flushed after every result. Incomplete trailing JSON is rejected.
        if (out/'fingerprints.jsonl').exists():records=[json.loads(line) for line in (out/'fingerprints.jsonl').read_text().splitlines()]
        if any(r['image_id'] not in source for r in records):raise ValueError('Unknown cached image')
    done={r['image_id'] for r in records};todo=[r for r in source.values() if r['image_id'] not in done]
    # Spread the pilot across type/quality/archive/order, then process remaining source rows.
    todo.sort(key=lambda r:hashlib.sha256(('frame-similarity-pilot42:'+r['image_id']).encode()).hexdigest())
    if args.limit:todo=todo[:args.limit]
    summary={'status':'running','plan':str(path.resolve()),'plan_sha256':plan_sha,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'source_counts':{k:len(v) for k,v in tables.items()},'fingerprinted':len(records),'final_test_used':False,'reserved_pixels_used':False,'model_execution':False,'originals_or_splits_modified':False,'workers':args.workers,'search':'cross split only; 64-bit horizontal dHash<=8 OR 128-bit horizontal+vertical<=12 OR exact display RGB bytes; full-image only','limitations':['Candidates are not verified duplicate physical parts.','Crop, rotation, large angle/light changes and same-part photographs can be missed.','Uniform surfaces/repeated factory structures can be false positives.','No empirical precision/recall certification for candidate thresholds.']}
    dump(out/'summary.json',summary);dump(ROOT/'frame_model/latest_similarity.json',{'directory':str(out),'summary':str(out/'summary.json')});print('[SIMILARITY OUTPUT]',out,flush=True);start=time.perf_counter();processed=0
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool,(out/'fingerprints.jsonl').open('a') as stream:
            iterator=iter(todo);pending=set()
            for _ in range(args.workers*2):
                row=next(iterator,None)
                if row is not None:pending.add(pool.submit(fingerprint,row,out))
            while pending:
                completed,pending=wait(pending,return_when=FIRST_COMPLETED)
                for future in completed:
                    result=future.result();stream.write(json.dumps(result,ensure_ascii=False)+'\n');stream.flush();records.append(result);processed+=1
                    row=next(iterator,None)
                    if row is not None:pending.add(pool.submit(fingerprint,row,out))
                if processed%100<args.workers or not pending:
                    seconds=time.perf_counter()-start;rate=processed/max(seconds,.001);summary.update(fingerprinted=len(records),new_processed=processed,elapsed_this_run_seconds=seconds,images_per_second=rate,rough_remaining_seconds=(len(source)-len(records))/max(rate,.001));dump(out/'summary.json',summary);print('[FINGERPRINT]',len(records),'/',len(source),'rate',round(rate,2),'img/s',flush=True)
        summary.update(fingerprinted=len(records),decode_errors=[r for r in records if 'error_type' in r])
        if len(records)==len(source):
            summary.update(rank_pairs(records,out));render_gallery(out,source);summary['status']='complete_with_decode_errors' if summary['decode_errors'] else 'complete_candidates_unreviewed'
        else:summary['status']='pilot_complete_not_full_audit'
    except BaseException as exc:
        summary['status']='failed_or_interrupted';summary['error_type']=type(exc).__name__;raise
    finally:
        summary['elapsed_this_run_seconds']=time.perf_counter()-start;dump(out/'summary.json',summary)
    print('[SIMILARITY RESULT]',summary['status'],out/'summary.json',flush=True)

if __name__=='__main__':main()
