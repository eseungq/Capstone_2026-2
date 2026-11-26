"""Read-only DGX preparation audit. Does not train, tune, or generate patch labels."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
from collections import Counter
from datetime import datetime
from pathlib import Path


def sequence(value):
    return value if isinstance(value, list) else [value] if isinstance(value, dict) else []


def run(root, output_root, check_env):
    manifest_root = root/'outputs/manifests'
    names = {'train':'door_train.csv', 'internal_validation':'door_internal_validation.csv', 'test':'door_test.csv'}
    report = {'purpose':'read-only preparation audit; not model performance evaluation', 'root':str(root),
              'environment':{}, 'manifests':{}, 'issues':[], 'label_distributions':{}, 'training_image_headers':[]}
    report['environment']['python'] = platform.python_version()
    report['environment']['platform'] = platform.platform()
    for package in ['torch','torchvision','timm','Pillow','pandas','scikit-learn']:
        try: report['environment'][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: report['environment'][package] = 'not installed in this interpreter'
    if check_env:
        try:
            import torch
            report['environment']['cuda_available'] = torch.cuda.is_available()
            report['environment']['cuda_build'] = torch.version.cuda
            if torch.cuda.is_available(): report['environment']['gpu'] = torch.cuda.get_device_name(0)
        except Exception as e: report['issues'].append({'type':'torch_environment_error','detail':str(e)})
    rows_by_split={}
    for split,name in names.items():
        path=manifest_root/name
        if not path.is_file():
            report['issues'].append({'type':'manifest_missing','path':str(path)})
            continue
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);rows=list(reader);columns=reader.fieldnames or []
        report['manifests'][split]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                    'rows':len(rows),'columns':columns,
                                    'quality_counts':dict(Counter(r.get('quality','missing') for r in rows))}
        if not {'image_path','json_path','quality'}.issubset(columns):
            report['issues'].append({'type':'required_manifest_columns_missing','split':split,
                                     'required':['image_path','json_path','quality'],'actual':columns})
            continue
        rows_by_split[split]=rows
    # Index only labels; data files are never extracted, copied or modified.
    needs_index=any(not Path(r['json_path']).expanduser().is_file() for rows in rows_by_split.values() for r in rows)
    label_index={}
    if needs_index:
        label_root=root/'data/labels'
        if label_root.is_dir():
            for p in label_root.rglob('*.json'):label_index.setdefault(p.name.casefold(),[]).append(p)
        else:report['issues'].append({'type':'label_root_missing','path':str(label_root)})
    global_names={}
    for split,rows in rows_by_split.items():
        counts=Counter();categories=Counter();bad=[];image_keys=[];missing_images=0;missing_json=0;collisions=0
        for row in rows:
            image=Path(row['image_path']).expanduser()
            if not image.is_absolute():image=root/image
            basename=Path(row.get('file_name') or str(image)).name.casefold()
            image_keys.append(basename)
            if not image.is_file():missing_images+=1
            raw=Path(row['json_path']).expanduser()
            possible=[raw,root/raw,root/'data/labels'/raw]
            existing=list(dict.fromkeys(p for p in possible if p.is_file()))
            if not existing:existing=label_index.get(raw.name.casefold(),[])
            if len(existing)!=1:
                missing_json+=1;bad.append({'file_name':basename,'error':'JSON path not uniquely resolved','matches':len(existing)})
                continue
            try:
                data=json.loads(existing[0].read_text(encoding='utf-8-sig'))
                ir=[x for x in sequence(data.get('images')) if Path(x.get('file_name','')).name.casefold()==basename]
                if len(ir)!=1:raise ValueError('JSON image record does not uniquely match image filename')
                anns=[a for a in sequence(data.get('annotations')) if a.get('image_id')==ir[0].get('id')]
                q={a.get('attributes',{}).get('quality') for a in anns}
                part={a.get('attributes',{}).get('part') for a in anns}
                if q!={row['quality']} or part!={'도어'}:raise ValueError('quality or part mismatch')
                cats={str(a.get('category_id')) for a in anns}
                # Categories are metadata, not automatically assigned patch labels.
                for c in cats:categories[(c,row['quality'])]+=1
                counts[(row['quality'],','.join(sorted(cats)))]+=1
                if split=='train' and len(report['training_image_headers'])<12 and image.is_file():
                    try:
                        from PIL import Image
                        with Image.open(image) as im:
                            orientation=im.getexif().get(274,1);size=list(im.size)
                        exif_size=list(reversed(size)) if orientation in [5,6,7,8] else size
                        label_size=[ir[0]['width'],ir[0]['height']]
                        report['training_image_headers'].append({'file_name':image.name,'stored_size':size,
                            'exif_size':exif_size,'exif_orientation':orientation,'label_size':label_size,
                            'stored_size_matches':size==label_size,'exif_size_matches':exif_size==label_size,
                            'warning':'matching dimensions alone do not confirm coordinate frame'})
                    except Exception as e:bad.append({'file_name':basename,'error':'image header: '+str(e)})
            except Exception as e:bad.append({'file_name':basename,'error':str(e)})
        duplicate_names=[name for name,n in Counter(image_keys).items() if n>1]
        report['manifests'][split].update({'missing_images':missing_images,'unresolved_json':missing_json,
                                          'duplicate_image_names':duplicate_names,'label_errors':bad})
        report['label_distributions'][split]=[{'quality':q,'category_ids':cats,'image_count':n} for (q,cats),n in sorted(counts.items())]
        report['manifests'][split]['category_quality_image_counts']=[{'category_id':c,'quality':q,'image_count':n} for (c,q),n in sorted(categories.items())]
        if missing_images or missing_json or bad or duplicate_names:report['issues'].append({'type':'split_data_not_ready','split':split})
        global_names[split]=set(image_keys)
    splits=list(global_names)
    report['cross_split_duplicates']={}
    for i,a in enumerate(splits):
        for b in splits[i+1:]:
            duplicates=sorted(global_names[a]&global_names[b]);report['cross_split_duplicates'][a+'__'+b]=duplicates
            if duplicates:report['issues'].append({'type':'cross_split_duplicate','splits':[a,b],'count':len(duplicates)})
    report['ready_for_data_rule_review']=len(rows_by_split)==3 and not report['issues']
    report['ready_to_train']=False
    report['training_blockers']=['Existing model/backbone/checkpoint and preprocessing settings must be recorded.',
                                 'Patch supervision and image-level aggregation must be explicitly defined on Training data.',
                                 'Probability calibration and AUTO_PASS policy are excluded from this first experiment.']
    out=output_root/('door_scope_preflight_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir(parents=True,exist_ok=False)
    (out/'preflight_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(out/'preflight_report.json'),'manifest_rows':{k:v['rows'] for k,v in report['manifests'].items()},
                      'issues':report['issues'],'ready_for_data_rule_review':report['ready_for_data_rule_review'],
                      'ready_to_train':False,'note':'No source, split, weights, labels or training settings were changed.'},ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path.home()/'car-parts-ai')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--skip-env',action='store_true')
    args=parser.parse_args()
    root=args.root.expanduser().resolve()
    run(root,args.output.expanduser().resolve() if args.output else root/'outputs/feasibility',not args.skip_env)
