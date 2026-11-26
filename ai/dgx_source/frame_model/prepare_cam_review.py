"""Select fixed internal-validation cases for paired frame CAM diagnostics; no training."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
import random
from pathlib import Path
from frame_model.check import ROOT,read_image
from frame_model.compare import compare_suite
from frame_model.experiments import load_plan
from frame_model.train import dump,write_csv


def choose_cases(paired_rows):
    selected={};candidates=[]
    def add(row,reason):
        key=row['image_id']
        if key not in selected:selected[key]={'pair':row,'reasons':[]}
        if reason not in selected[key]['reasons']:selected[key]['reasons'].append(reason)
    for kind in sorted({r['defect_type'] for r in paired_rows}):
        rows=[r for r in paired_rows if r['defect_type']==kind]
        missed=sorted([r for r in rows if int(r['actual'])==1 and int(r['specialist_prediction'])==0],key=lambda r:(float(r['specialist_score']),r['image_id']))
        candidates.extend(dict(r,priority='specialist_FN') for r in missed)
        if missed:
            add(missed[0],'specialist_FN_lowest_score');add(missed[-1],'specialist_FN_near_cutoff')
        for category in ['unified_only_wrong','specialist_only_wrong']:
            eligible=sorted([r for r in rows if r['category']==category],key=lambda r:r['image_id'])
            if eligible:add(eligible[0],category)
        for truth,name in [(0,'both_TN_control'),(1,'both_TP_control')]:
            eligible=sorted([r for r in rows if int(r['actual'])==truth and r['category']=='both_correct'],key=lambda r:r['image_id'])
            if eligible:add(eligible[0],name)
    return list(selected.values()),candidates



def choose_shared_defect(rows,source,excluded,seeds=44):
    excluded_ids={i['source']['image_id'] for old in excluded for i in old['items']}
    excluded_groups={i['source']['group_id'] for old in excluded for i in old['items']}
    pool=[r for r in rows if r['unified_prediction']==r['specialist_prediction']=='1' and r['image_id'] not in excluded_ids and source[r['image_id']]['group_id'] not in excluded_groups]
    selected=[];used_groups=set(excluded_groups);rng=random.Random(seeds)
    for kind in sorted({r['defect_type'] for r in rows}):
        # Reserve scarce shared FP groups first; never silently replace FP with TP.
        for actual,count,label in [('0',1,'both_DEFECT_shared_FP'),('1',3,'both_DEFECT_shared_TP')]:
            candidates=sorted([r for r in pool if r['defect_type']==kind and r['actual']==actual],key=lambda r:r['image_id'])
            rng.shuffle(candidates);picked=[]
            for row in candidates:
                group=source[row['image_id']]['group_id']
                if group in used_groups:continue
                used_groups.add(group);picked.append({'pair':row,'reasons':[label]})
                if len(picked)==count:break
            if len(picked)!=count:raise ValueError(f'Insufficient unseen groups for {kind} {label}: {len(picked)}/{count}')
            selected.extend(picked)
    return selected,pool


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',type=Path,required=True)
    parser.add_argument('--selection-mode',choices=['errors','shared-defect'],default='errors')
    parser.add_argument('--exclude-review',type=Path,action='append',default=[])
    args=parser.parse_args()
    if args.selection_mode=='shared-defect' and not args.exclude_review:parser.error('shared-defect requires --exclude-review')
    report=compare_suite(args.suite)
    if report['mode']!='train':raise ValueError('Need full training suite')
    suite=json.loads(args.suite.read_text());_,_,experiments=load_plan(Path(suite['plan']))
    rows=list(csv.DictReader(io.StringIO((args.suite.parent/'paired_predictions.csv').read_text())))
    source={r['image_id']:r for r in experiments['unified'][1]['model_selection']}
    if args.selection_mode=='shared-defect':
        excluded=[json.loads(p.read_text()) for p in args.exclude_review]
        chosen,candidates=choose_shared_defect(rows,source,excluded)
    else:chosen,candidates=choose_cases(rows)
    out=ROOT/'outputs/frame_cam_review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    checkpoints={}
    for run in suite['runs']:
        directory=Path(run['directory']);path=directory/'best.pt';config=json.loads((directory/'run_config.json').read_text())
        history=list(csv.DictReader(io.StringIO((directory/'history.csv').read_text())))
        best=max(history,key=lambda row:float(row['f1']))
        checkpoints[run['experiment_id']]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'expected_best_epoch':int(best['epoch']),'expected_best_f1':float(best['f1']),'run_config':config,'run_config_sha256':hashlib.sha256((directory/'run_config.json').read_bytes()).hexdigest()}
    labels={};wanted={source[x['pair']['image_id']]['label_member'] for x in chosen}
    import tarfile
    with tarfile.open(next(iter(source.values()))['label_archive'],'r:') as archive:
        for member in archive:
            if member.name in wanted:labels[member.name]=archive.extractfile(member).read()
    items=[]
    kinds={e['inspection_type']:ident for ident,(e,_) in experiments.items() if ident!='unified'}
    for index,item in enumerate(chosen,1):
        row=source[item['pair']['image_id']];ident=f'{index:02d}';dest=out/ident;dest.mkdir()
        display,padded=read_image(row);display.save(dest/'display.png');preview=display.copy();preview.thumbnail((1200,1200));preview.save(dest/'preview.jpg',quality=90);padded.save(dest/'input224.png')
        data=labels[row['label_member']]
        if hashlib.sha256(data).hexdigest()!=row['label_sha256']:raise ValueError('Label mismatch')
        (dest/'label.json').write_bytes(data)
        items.append({'id':ident,'source':row,'pair':item['pair'],'selection_reasons':item['reasons'],'specialist_id':kinds[row['defect_type']],'display_size':list(display.size)})
    selection={'schema':'frame_cam_review_v1','review_id':out.name,'suite':str(args.suite.resolve()),'suite_sha256':hashlib.sha256(args.suite.read_bytes()).hexdigest(),'plan_sha256':suite['plan_sha256'],'checkpoints':checkpoints,'items':items,'layers':['layers.3.blocks.1.norm1','layers.2.blocks.5.norm1'],'selection_rule':'Per type: up to two specialist FNs (low/near cutoff), one each disagreement direction, one shared TN and TP; overlaps merged. All specialist FNs retained in candidate ledger.','score_tolerance':{'absolute':1e-6,'relative':1e-4},'class_order':{'GOOD':0,'DEFECT':1},'final_test_used':False,'training_performed':False}
    selection.update(selection_mode=args.selection_mode,excluded_reviews=[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in args.exclude_review])
    if args.selection_mode=='shared-defect':
        selection.update(review_layout='per_layer_v2',selection_seed=44,selection_rule='Per type: shared FP1 and TP3, both models predicted DEFECT; prior image IDs and temporal groups excluded; distinct temporal groups across all selected cases; seed44. Not a representative error rate.')
    dump(out/'selection.json',selection)
    write_csv(out/('shared_DEFECT_candidate_pool.csv' if args.selection_mode=='shared-defect' else 'all_specialist_FN_candidates.csv'),candidates)
    from frame_model.cam_review import render
    render(out,selection,None)
    dump(ROOT/'frame_model/latest_cam_review.json',{'directory':str(out),'selection':str(out/'selection.json'),'html':str(out/'index.html'),'samples':len(items)})
    print('[FRAME CAM REVIEW PREPARED]',out/'index.html');print('[SELECTED]',len(items),'[CANDIDATE POOL]',len(candidates))

if __name__=='__main__':main()
