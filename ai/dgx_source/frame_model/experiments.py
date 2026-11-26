"""Run a frozen comparison plan, sequentially, with identical model initialization."""
import argparse
import copy
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
from frame_model.check import ROOT
from frame_model.train import manifests,subset,dump,execute


def load_plan(path):
    path=path.resolve();plan=json.loads(path.read_text());prep=Path(plan['source_preparation'])
    config,source=manifests(prep)
    if config['manifests']!=plan['source_manifests']:raise ValueError('Source preparation manifest mismatch')
    if plan['reserved_roles_used_for_training_or_evaluation'] or plan['official_final_test_used']:raise ValueError('Reserved data plan forbidden')
    verified={}
    for relative,expected in plan['manifest_sha256'].items():
        file=(path.parent/relative).resolve()
        if not file.is_relative_to(path.parent):raise ValueError('Manifest outside plan')
        data=file.read_bytes()
        if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Manifest hash differs: '+relative)
        verified[str(file)]=list(csv.DictReader(io.StringIO(data.decode())))
    experiments={}
    expected_types={f'type_{i:02d}':k for i,k in enumerate(config['inspection_types'],1)}
    if len(plan['experiments'])!=5 or {e['id'] for e in plan['experiments']}!={'unified',*expected_types}:raise ValueError('Expected unified plus four types')
    for exp in plan['experiments']:
        if exp['inspection_type']!=expected_types.get(exp['id']):raise ValueError('Inspection type mismatch')
        if any(exp[k]!=config[c] for k,c in [('epochs','epochs'),('seed','seed'),('batch_size','batch_size'),('pretrained','pretrained')]) or exp['precision']!='FP32':raise ValueError('Plan settings differ')
        tables={}
        for role,key in [('train','train_manifest'),('model_selection','model_selection_manifest')]:
            file=str(Path(exp[key]).resolve())
            if file not in verified:raise ValueError('Manifest unverified')
            rows=verified[file];original={r['image_id']:r for r in source[role]}
            if not rows or len({r['image_id'] for r in rows})!=len(rows):raise ValueError('Empty or duplicate images')
            for r in rows:
                if original.get(r['image_id'])!=r:raise ValueError('Manifest is not unchanged source-role subset')
                if exp['inspection_type'] and r['defect_type']!=exp['inspection_type']:raise ValueError('Mixed inspection types')
            for kind in {r['defect_type'] for r in rows}:
                if {r['class_id'] for r in rows if r['defect_type']==kind}!={'0','1'}:raise ValueError('Class coverage missing')
            tables[role]=rows
        experiments[exp['id']]=(exp,tables)
    unified=experiments['unified'][1]
    if set(r['defect_type'] for r in unified['train'])!=set(config['inspection_types']):raise ValueError('Missing unified type')
    for role in unified:
        union=set()
        for ident,kind in expected_types.items():
            specialist={r['image_id'] for r in experiments[ident][1][role]}
            expected={r['image_id'] for r in unified[role] if r['defect_type']==kind}
            if specialist!=expected:raise ValueError('Unified/specialist images differ')
            union.update(specialist)
        if union!={r['image_id'] for r in unified[role]}:raise ValueError('Union mismatch')
    return config,prep,experiments


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--mode',choices=['validate','smoke','train'],default='validate')
    parser.add_argument('--start-training',action='store_true')
    args=parser.parse_args()
    if args.mode=='train' and not args.start_training:parser.error('--start-training required for full suite')
    config,prep,experiments=load_plan(args.plan)
    print('[PLAN VERIFIED]',args.plan,flush=True)
    if args.mode=='validate':return
    smoke=args.mode=='smoke'
    out=ROOT/'outputs/frame_training'/f"comparison_{args.mode}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')}"
    out.mkdir(parents=True);plan_sha=hashlib.sha256(args.plan.read_bytes()).hexdigest()
    suite={'status':'running','mode':args.mode,'plan':str(args.plan.resolve()),'plan_sha256':plan_sha,'quality_evaluation':not smoke,'runs':[]}
    dump(out/'suite.json',suite);initial=None
    print('[COMPARISON OUTPUT]',out,flush=True)
    try:
        order=['unified']+[f'type_{i:02d}' for i in range(1,5)]
        for ident in order:
            exp,full_tables=experiments[ident]
            tables={role:subset(rows,16 if role=='train' else 8) if smoke else rows for role,rows in full_tables.items()}
            current=copy.deepcopy(config)
            current['inspection_types']=sorted({r['defect_type'] for r in tables['train']})
            current['roles']={role:len(rows) for role,rows in full_tables.items()}
            directory=out/ident;directory.mkdir()
            dump(directory/'status.json',{'status':'starting','mode':args.mode})
            context={'experiment_id':ident,'inspection_type':exp['inspection_type'],'plan':str(args.plan.resolve()),'plan_sha256':plan_sha,'seed':exp['seed'],'source_manifest_sha256':{role:hashlib.sha256(Path(exp[key]).read_bytes()).hexdigest() for role,key in [('train','train_manifest'),('model_selection','model_selection_manifest')]}}
            suite['runs'].append({'experiment_id':ident,'directory':str(directory),'status':'running'})
            dump(out/'suite.json',suite)
            execute(current,tables,prep,directory,smoke,context=context,initial_state=initial)
            if initial is None:initial=directory/'initial_state.pt'
            suite['runs'][-1]['status']='passed';dump(out/'suite.json',suite)
            import gc,torch
            gc.collect();torch.cuda.empty_cache()
        from frame_model.compare import compare_suite
        compare_suite(out/'suite.json',require_complete=False)
        suite['status']='passed';dump(out/'suite.json',suite)
    except BaseException as exc:
        if suite['runs'] and suite['runs'][-1]['status']=='running':
            suite['runs'][-1]['status']='failed_or_interrupted'
            dump(Path(suite['runs'][-1]['directory'])/'status.json',{'status':'failed_or_interrupted','mode':args.mode,'error_type':type(exc).__name__})
        suite['status']='failed_or_interrupted';suite['error_type']=type(exc).__name__;dump(out/'suite.json',suite);raise
    print('[COMPARISON SMOKE PASSED]' if smoke else '[COMPARISON TRAINING COMPLETE]',out,flush=True)

if __name__=='__main__':main()
