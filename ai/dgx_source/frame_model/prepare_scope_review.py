"""Build a local-only frame inspection-scope review; never modifies source data."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import random
import tarfile
from frame_model.train import manifests,dump
from frame_model.check import ROOT,read_image

SCOPES={'외관 손상':'지정 표면에서 사진으로 확인 가능한 외관 손상. 보이지 않는 면은 판단 범위에서 제외.', '실링 불량':'사진에 보이는 지정 실링 구간의 도포·연결 상태. 사진만으로 기밀성·내부 접착 성능을 확정하지 않음.', '헤밍 불량':'사진에 보이는 지정 접합 가장자리 상태. 보이지 않는 내부 접합 강도는 판단하지 않음.', '홀 변형':'지정 홀의 눈에 보이는 테두리·형상 이상. 설계 기준 없이 치수 공차나 정상 형상을 확정하지 않음.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--per-class',type=int,default=8)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--exclude-review',type=Path,action='append',default=[])
    parser.add_argument('--scope-baseline',type=Path)
    args=parser.parse_args()
    baseline=json.loads(args.scope_baseline.read_text()) if args.scope_baseline else None
    if not 1<=args.per_class<=16: parser.error('--per-class must be 1..16')
    prep=Path(json.loads((ROOT/'frame_model/latest_preparation.json').read_text())['preparation'])
    config,tables=manifests(prep)
    excluded_images=set();excluded_groups=set()
    for path in args.exclude_review:
        old=json.loads(path.read_text())
        for row in old['items']:
            excluded_images.add(row['image_sha256']);excluded_groups.add(row['group_id'])
    chosen=[];rng=random.Random(args.seed)
    # Training only: do not use reserved or model-selection photos to design inclusion rules.
    for kind in config['inspection_types']:
        for quality in ['0','1']:
            candidates=sorted([r for r in tables['train'] if r['defect_type']==kind and r['class_id']==quality and r['image_sha256'] not in excluded_images and r['group_id'] not in excluded_groups],key=lambda r:r['image_id'])
            rng.shuffle(candidates);groups=set();picked=[]
            for row in candidates:
                if row['group_id'] not in groups:
                    picked.append(row);groups.add(row['group_id'])
                if len(picked)==args.per_class: break
            if len(picked)!=args.per_class: raise ValueError('Insufficient distinct groups')
            chosen.extend(picked)
    out=ROOT/'outputs/frame_scope_review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out.mkdir(parents=True,exist_ok=False)
    wanted={r['label_member'] for r in chosen};labels={}
    with tarfile.open(chosen[0]['label_archive'],'r:') as archive:
        for member in archive:
            if member.name in wanted:
                data=archive.extractfile(member).read();labels[member.name]=data
    items=[]
    for index,row in enumerate(chosen,1):
        ident=f'{index:02d}';display,padded=read_image(row)
        data=labels[row['label_member']]
        if hashlib.sha256(data).hexdigest()!=row['label_sha256']: raise ValueError('Label changed')
        display.save(out/f'{ident}_display.jpg',quality=95)
        preview=display.copy();preview.thumbnail((1200,1200));preview.save(out/f'{ident}_preview.jpg',quality=90)
        padded.save(out/f'{ident}_224.png')
        (out/f'{ident}_label.json').write_bytes(data)
        items.append(dict(row,id=ident,display_size=display.size,display=f'{ident}_display.jpg',preview=f'{ident}_preview.jpg',input224=f'{ident}_224.png',label=f'{ident}_label.json'))
    bundle={'schema':'frame_scope_review_v1','review_id':out.name,'preparation':str(prep),'selection':f'Training only; seed={args.seed}, per type/class={args.per_class}; previous images and temporal groups excluded; exploratory, not population estimate','excluded_reviews':[str(p) for p in args.exclude_review],'seed':args.seed,'per_class':args.per_class,'scopes':SCOPES,'items':items}
    if args.scope_baseline:
        bundle['scope_baseline']=baseline['scopes']
        bundle['scope_baseline_source']=str(args.scope_baseline)
    criteria=ROOT/'frame_model/PHOTO_CRITERIA_V1.md'
    if criteria.exists():
        bundle['criteria_sha256']=hashlib.sha256(criteria.read_bytes()).hexdigest()
        (out/'criteria.md').write_bytes(criteria.read_bytes())
    dump(out/'selection.json',bundle)
    template=(ROOT/'frame_model/scope_review.html').read_text()
    (out/'index.html').write_text(template.replace('__BUNDLE__',json.dumps(bundle,ensure_ascii=False).replace('<','\\u003c')))
    dump(ROOT/'frame_model/latest_scope_review.json',{'directory':str(out),'html':str(out/'index.html'),'samples':len(items)})
    print('[SCOPE REVIEW READY]',out/'index.html',flush=True)

if __name__=='__main__':main()
