"""Offline paired Grad-CAM review, reusing ai_api.diagnostics.cam. Never trains/serves."""
import argparse
from datetime import datetime,timezone
import hashlib
import html
import importlib.metadata
import json
import math
from pathlib import Path
from PIL import Image,ImageOps
from frame_model.check import ROOT,read_image
from frame_model.train import dump


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()



def verify_metadata(actual,expected):
    """Match the JSON-recorded representation, preserving every field/value.

    timm pretrained_cfg contains tuples; torch.save preserves them while JSON
    stores arrays as lists. This is the same normalization used by prototype.Engine.
    """
    actual_json=json.dumps(actual,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))
    expected_json=json.dumps(expected,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))
    if actual_json!=expected_json:
        a=json.loads(actual_json);b=json.loads(expected_json)
        differences=[]
        def walk(x,y,path):
            if type(x) is not type(y):differences.append(path+' (type)');return
            if isinstance(x,dict):
                for key in sorted(set(x)|set(y)):
                    if key not in x or key not in y:differences.append(path+'.'+key+' (missing)')
                    else:walk(x[key],y[key],path+'.'+key)
            elif isinstance(x,list):
                if len(x)!=len(y):differences.append(path+' (length)')
                for index,(left,right) in enumerate(zip(x,y)):walk(left,right,f'{path}[{index}]')
            elif x!=y:differences.append(path)
        walk(a,b,'metadata')
        raise ValueError('Checkpoint metadata differs after JSON normalization: '+', '.join(differences[:12]))
    return {'status':'matched','comparison':'complete canonical JSON; tuples represented as arrays','canonical_sha256':hashlib.sha256(actual_json.encode()).hexdigest()}


def state_hash(model):
    h=hashlib.sha256()
    for key,value in sorted(model.state_dict().items()):
        h.update(key.encode());h.update(value.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def render(out,selection,report):
    template=(ROOT/'frame_model'/('cam_layer_review.html' if selection.get('review_layout')=='per_layer_v2' else 'cam_review.html')).read_text()
    bundle={'selection':selection,'report':report}
    (out/'index.html').write_text(template.replace('__BUNDLE__',json.dumps(bundle,ensure_ascii=False).replace('<','\\u003c')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--diagnostic-good-cam',action='store_true',help='Separate diagnostic class1 CAM on GOOD; service CAM stays omitted')
    args=parser.parse_args();sel=json.loads(args.selection.read_text());out=args.selection.parent
    if sel['schema']!='frame_cam_review_v1' or sel['final_test_used'] or sel['training_performed']:raise ValueError('Invalid scope')
    if file_sha(sel['suite'])!=sel['suite_sha256']:raise ValueError('Suite differs')
    if (out/'cam_report.json').exists():raise ValueError('CAM report already exists; prepare a new review instead of overwriting')
    import numpy as np
    import torch
    import timm
    from torchvision.transforms import functional as TF
    from ai_api.diagnostics import cam
    from frame_model.experiments import load_plan
    suite=json.loads(Path(sel['suite']).read_text());_,_,experiments=load_plan(Path(suite['plan']))
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    torch.manual_seed(42);torch.cuda.manual_seed_all(42);torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
    report={'status':'running','review_id':sel['review_id'],'started_at':datetime.now(timezone.utc).isoformat(),'source_sha256':{name:file_sha(ROOT/name) for name in ['frame_model/cam_review.py','ai_api/diagnostics.py']},'selection_sha256':file_sha(args.selection),'samples':{},'models':{},'errors':[],'warnings':[],'final_test_used':False,'training_performed':False,'service_changed':False,'diagnostic_good_cam':args.diagnostic_good_cam}
    dump(out/'cam_report.json',report)
    try:
        for model_id,checkpoint_info in sel['checkpoints'].items():
            cfg=checkpoint_info['run_config'];config=cfg['config'];path=Path(checkpoint_info['path'])
            if file_sha(path)!=checkpoint_info['sha256']:raise ValueError('Checkpoint differs: '+model_id)
            versions={p:importlib.metadata.version(p) for p in cfg['versions']}
            if versions!=cfg['versions']:raise ValueError('Environment differs: '+model_id)
            # Trusted local training artifact includes optimizer/RNG metadata; never accepts network checkpoints.
            checkpoint=torch.load(path,map_location='cpu',weights_only=False)
            metadata_check=verify_metadata(checkpoint['metadata'],cfg)
            if checkpoint['epoch']!=checkpoint_info['expected_best_epoch'] or checkpoint['metrics']['f1']!=checkpoint_info['expected_best_f1']:raise ValueError('Checkpoint is not recorded F1-selected epoch')
            model=timm.create_model(config['model_name'],pretrained=False,num_classes=2)
            model.load_state_dict(checkpoint['model_state_dict'],strict=True);epoch=checkpoint['epoch'];del checkpoint
            model=model.float().cuda().eval();before=state_hash(model)
            class Adapter:
                def __init__(self):self.model=model;self.torch=torch;self.np=np
                def tensor(self,path):
                    with Image.open(path) as im:display=ImageOps.exif_transpose(im).convert('RGB')
                    padded=ImageOps.pad(display,(224,224),method=Image.Resampling.BICUBIC,color=tuple(config['fill']))
                    return TF.normalize(TF.to_tensor(padded),config['mean'],config['std'])
            engine=Adapter();full=experiments[model_id][1]['model_selection'];positions={r['image_id']:i for i,r in enumerate(full)}
            model_report={'checkpoint_sha256':checkpoint_info['sha256'],'epoch':epoch,'versions':versions,'before_state_sha256':before,'eval':True,'precision':'FP32','metadata_check':metadata_check};report['models'][model_id]=model_report
            for item in sel['items']:
                if model_id not in ['unified',item['specialist_id']]:continue
                ident=item['id'];source=item['source'];original=out/ident/'display.png';dest=out/ident/model_id;dest.mkdir()
                entry={'layers':[],'errors':[]};report['samples'].setdefault(ident,{})[model_id]=entry
                if positions.get(source['image_id']) is None or full[positions[source['image_id']]]!=source:raise ValueError('Selected image is not expected validation image')
                # Check original bytes again and compare lossless display PNG to source pixels.
                display,padded=read_image(source)
                with Image.open(original) as im:
                    if im.size!=display.size or im.convert('RGB').tobytes()!=display.tobytes():raise ValueError('Display/source pixels differ')
                torch.cuda.synchronize()
                with torch.inference_mode():
                    logits=model(engine.tensor(original).unsqueeze(0).cuda())
                    if not torch.isfinite(logits).all():raise ValueError('Nonfinite classification logits')
                    score=float(torch.softmax(logits,dim=1)[0,1])
                    position=positions[source['image_id']];start=position//config['batch_size']*config['batch_size'];rows=full[start:start+config['batch_size']]
                    batch=[]
                    for row in rows:
                        _,im=read_image(row);batch.append(TF.normalize(TF.to_tensor(im),config['mean'],config['std']))
                    batch_logits=model(torch.stack(batch).cuda())
                    if not torch.isfinite(batch_logits).all():raise ValueError('Nonfinite recreated-batch logits')
                    batch_score=float(torch.softmax(batch_logits,dim=1)[position-start,1])
                if not math.isfinite(score) or not 0<=score<=1:raise ValueError('Invalid score')
                saved=float(item['pair']['unified_score' if model_id=='unified' else 'specialist_score']);pred=int(score>=.5)
                entry.update(single_score=score,recreated_batch_score=batch_score,saved_batch_score=saved,predicted_quality='DEFECT' if pred else 'GOOD',class_matches_saved=pred==int(item['pair']['unified_prediction' if model_id=='unified' else 'specialist_prediction']),single_score_matches_saved=math.isclose(score,saved,abs_tol=1e-6,rel_tol=1e-4),batch_score_matches_saved=math.isclose(batch_score,saved,abs_tol=1e-6,rel_tol=1e-4),service_cam_status='PENDING' if pred else 'NOT_GENERATED_GOOD')
                if not entry['batch_score_matches_saved'] or not entry['class_matches_saved']:
                    report['errors'].append({'id':ident,'model':model_id,'stage':'score_reproduction'})
                if not entry['single_score_matches_saved']:report['warnings'].append({'id':ident,'model':model_id,'stage':'single_vs_saved_batch8_score'})
                if pred or args.diagnostic_good_cam:
                    for layer in sel['layers']:
                        layerdest=dest/layer;layerdest.mkdir()
                        try:
                            info,_,_=cam(engine,original,layer,layerdest,target='defect')
                            info.update(scope='predicted_DEFECT_candidate' if pred else 'diagnostic_GOOD_only',overlay=str((layerdest/'overlay.png').relative_to(out)) if info['status']=='GENERATED' else None)
                            if info['overlay']:
                                with Image.open(out/info['overlay']) as image:
                                    if list(image.size)!=item['display_size']:raise ValueError('Overlay/display size differs')
                            entry['layers'].append(info)
                        except Exception as exc:
                            entry['layers'].append({'layer':layer,'status':'FAILED','error_type':type(exc).__name__,'overlay':None,'scope':'predicted_DEFECT_candidate' if pred else 'diagnostic_GOOD_only'})
                            entry['errors'].append({'layer':layer,'error_type':type(exc).__name__})
                    if pred:entry['service_cam_status']='CANDIDATE_LAYERS_EVALUATED'  # no registered service layer selected
                print('[FRAME CAM]',ident,model_id,entry['predicted_quality'],flush=True)
                dump(out/'cam_report.json',report)
            after=state_hash(model);model_report.update(after_state_sha256=after,state_unchanged=before==after,eval=not model.training)
            if before!=after or model.training:raise RuntimeError('Model state/mode changed')
            if file_sha(path)!=checkpoint_info['sha256']:raise RuntimeError('Checkpoint file changed')
            del engine,model
            import gc
            gc.collect();torch.cuda.empty_cache()
        report['status']='completed_with_reproduction_errors' if report['errors'] else 'completed_with_cam_failures' if any(e['errors'] for row in report['samples'].values() for e in row.values()) else 'completed_with_score_warnings' if report['warnings'] else 'passed'
    except BaseException as exc:
        report['status']='failed_or_interrupted';report['errors'].append({'stage':'execution','error_type':type(exc).__name__});raise
    finally:
        dump(out/'cam_report.json',report);render(out,sel,report)
        print('[FRAME CAM REPORT]',out/'cam_report.json');print('[FRAME CAM HTML]',out/'index.html');print('[FRAME CAM RESULT]',report['status'])
    if report['errors']:raise RuntimeError('Reproduction errors preserved; review diagnostics before conclusions')

if __name__=='__main__':main()
