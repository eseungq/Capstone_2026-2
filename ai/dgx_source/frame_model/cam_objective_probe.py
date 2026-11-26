"""Compare original class1 logit CAM with a diagnostic logit-margin CAM; never trains."""
import argparse
import gc
import html
import importlib.metadata
import json
import math
from pathlib import Path
from PIL import Image,ImageOps
from frame_model.check import ROOT,read_image
from frame_model.cam_review import file_sha,state_hash,verify_metadata
from frame_model.train import dump


def render(out,plan,report):
    parts=['<!doctype html><meta charset="utf-8"><title>고정 모델 CAM 목표 진단</title><style>body{font:17px sans-serif;max-width:1400px;margin:auto}img{max-width:30%;vertical-align:top}section{border-top:1px solid #aaa;padding:18px}pre{white-space:pre-wrap}</style><h1>같은 모델·입력: 원래 logit과 진단용 margin 비교</h1><p>margin은 서비스 계약의 대체 CAM이 아닙니다. 정규화된 붉은색의 강도를 신뢰도로 해석하지 않습니다. 다른 모양이 나와도 결함 위치 정확도가 개선됐다는 증거가 아닙니다. 새로운 육안 검토 JSON은 요청하지 않습니다.</p>']
    for row in report['results']:
        item=next(x for x in plan['items'] if x['id']==row['id'])
        parts.append('<section><h2>'+html.escape(row['id']+' '+item['pair']['defect_type']+' '+row['model']+' '+row['layer'])+'</h2>')
        parts.append('<p>원천 정답: '+('DEFECT' if int(item['pair']['actual']) else 'GOOD — 두 모델 오탐 사례')+'</p>')
        parts.append('<a href="'+html.escape(item['display_path'],quote=True)+'"><img src="'+html.escape(item['display_path'],quote=True)+'"></a>')
        for target in ['defect','margin']:
            info=row.get(target,{'status':'NOT_COMPLETED','overlay':None});parts.append('<p>'+target+' — '+html.escape(info['status'])+'</p>')
            if info.get('overlay'):parts.append('<a href="'+info['overlay']+'"><img src="'+info['overlay']+'"></a>')
        parts.append('<pre>'+html.escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre></section>')
    (out/'index.html').write_text('\n'.join(parts))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True);args=parser.parse_args()
    plan=json.loads(args.plan.read_text());out=args.plan.parent
    if plan['schema']!='frame_cam_objective_probe_v1' or plan['training_performed'] or plan['final_test_used'] or plan['service_changed']:raise ValueError('Invalid probe scope')
    if (out/'probe_report.json').exists():raise ValueError('Probe already attempted; prepare a new version rather than overwrite')
    if file_sha(plan['source_selection'])!=plan['source_selection_sha256']:raise ValueError('Source selection changed')
    if file_sha(Path(plan['source_selection']).parent/'cam_report.json')!=plan['source_report_sha256']:raise ValueError('Source CAM report changed')
    import numpy as np
    import torch
    import timm
    from torchvision.transforms import functional as TF
    from ai_api.diagnostics import cam
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    torch.manual_seed(42);torch.cuda.manual_seed_all(42);torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
    report={'status':'running','plan_sha256':file_sha(args.plan),'source_sha256':{'probe':file_sha(Path(__file__)),'cam_implementation':file_sha(ROOT/'ai_api/diagnostics.py')},'results':[],'models':{},'errors':[],'warnings':[],'training_performed':False,'service_changed':False,'interpretation':'Map change is not improvement or causal proof; margin is diagnostic only.'}
    dump(out/'probe_report.json',report)
    try:
        for model_id,info in plan['checkpoints'].items():
            config=info['run_config'];cfg=config['config'];checkpoint_path=Path(info['path'])
            if file_sha(checkpoint_path)!=info['sha256']:raise ValueError('Checkpoint changed')
            if {p:importlib.metadata.version(p) for p in config['versions']}!=config['versions']:raise ValueError('Versions differ')
            checkpoint=torch.load(checkpoint_path,map_location='cpu',weights_only=False)
            verified=verify_metadata(checkpoint['metadata'],config)
            if checkpoint['epoch']!=info['expected_best_epoch'] or checkpoint['metrics']['f1']!=info['expected_best_f1']:raise ValueError('Wrong selected checkpoint')
            model=timm.create_model(cfg['model_name'],pretrained=False,num_classes=2);model.load_state_dict(checkpoint['model_state_dict'],strict=True);del checkpoint
            model=model.float().cuda().eval();before=state_hash(model)
            class Adapter:
                def __init__(self):self.model=model;self.torch=torch;self.np=np
                def tensor(self,path):
                    with Image.open(path) as im:display=ImageOps.exif_transpose(im).convert('RGB')
                    padded=ImageOps.pad(display,(224,224),method=Image.Resampling.BICUBIC,color=tuple(cfg['fill']))
                    return TF.normalize(TF.to_tensor(padded),cfg['mean'],cfg['std'])
            engine=Adapter()
            report['models'][model_id]={'checkpoint_sha256':info['sha256'],'metadata_check':verified,'before_state_sha256':before,'versions':config['versions']}
            for item in plan['items']:
                if model_id not in ['unified',item['specialist_id']]:continue
                path=Path(item['display_path'])
                if file_sha(path)!=item['display_sha256']:raise ValueError('Display changed')
                display,_=read_image(item['source'])
                with Image.open(path) as original:
                    if original.size!=display.size or original.convert('RGB').tobytes()!=display.tobytes():raise ValueError('Display/source pixels differ')
                with torch.inference_mode():
                    logits=model(engine.tensor(path).unsqueeze(0).cuda())
                    if not torch.isfinite(logits).all():raise ValueError('Nonfinite logits')
                    score=float(torch.softmax(logits,dim=1)[0,1])
                baseline_score=item['baseline_results'][model_id]['single_score'];baseline_quality=item['baseline_results'][model_id]['predicted_quality']
                score_match=math.isclose(score,baseline_score,abs_tol=1e-6,rel_tol=1e-4);class_match=('DEFECT' if score>=.5 else 'GOOD')==baseline_quality
                if not score_match or not class_match:report['errors'].append({'id':item['id'],'model':model_id,'stage':'single_reproduction'})
                for layer in plan['layers']:
                    record={'id':item['id'],'model':model_id,'layer':layer,'single_score':score,'single_reproduced':score_match,'class_reproduced':class_match,'source_class':int(item['pair']['actual'])};report['results'].append(record)
                    for target in plan['objectives']:
                        dest=out/item['id']/model_id/layer/target;dest.mkdir(parents=True)
                        try:
                            result,_,_=cam(engine,path,layer,dest,target=target)
                            result['overlay']=str((dest/'overlay.png').relative_to(out)) if result['status']=='GENERATED' else None
                            if result['overlay']:
                                with Image.open(out/result['overlay']) as image:
                                    if list(image.size)!=item['display_size']:raise ValueError('Overlay dimensions differ')
                            record[target]=result
                        except Exception as exc:
                            record[target]={'status':'FAILED','overlay':None,'error_type':type(exc).__name__}
                            report['errors'].append({'id':item['id'],'model':model_id,'layer':layer,'target':target,'stage':'cam'})
                    baseline=Path(item['baseline_root'])/item['id']/model_id/layer/'raw.npy'
                    if file_sha(baseline)!=item['baseline_raw_sha256'][model_id][layer]:raise ValueError('Baseline raw changed')
                    if record['defect']['status']!='FAILED':
                        original_raw=np.load(baseline,allow_pickle=False);new_raw=np.load(out/item['id']/model_id/layer/'defect/raw.npy',allow_pickle=False)
                        matched=original_raw.shape==new_raw.shape and bool(np.allclose(original_raw,new_raw,atol=1e-12,rtol=1e-6));record['original_raw_reproduced']=matched
                        if not matched:report['errors'].append({'id':item['id'],'model':model_id,'layer':layer,'stage':'raw_reproduction'})
                        if record['margin']['status']!='FAILED':
                            alternate=np.load(out/item['id']/model_id/layer/'margin/raw.npy',allow_pickle=False)
                            if alternate.shape!=new_raw.shape or not np.isfinite(alternate).all():raise ValueError('Invalid alternate map')
                            if record['defect']['status']=='GENERATED' and record['margin']['status']=='GENERATED':
                                a=(new_raw-new_raw.min())/(new_raw.max()-new_raw.min());b=(alternate-alternate.min())/(alternate.max()-alternate.min());a=a.ravel();b=b.ravel()
                                count=max(1,len(a)//5);top_a=set(np.argsort(a,kind='stable')[-count:].tolist());top_b=set(np.argsort(b,kind='stable')[-count:].tolist())
                                record['map_change_descriptive_only']={'normalized_mean_absolute_difference':float(np.abs(a-b).mean()),'pearson':float(np.corrcoef(a,b)[0,1]),'top_20_percent_grid_jaccard':len(top_a&top_b)/len(top_a|top_b),'warning':'Descriptive coarse feature grid comparison, no defect-location ground truth.'}
                    print('[CAM OBJECTIVE PROBE]',item['id'],model_id,layer,flush=True);dump(out/'probe_report.json',report)
            after=state_hash(model);report['models'][model_id].update(after_state_sha256=after,state_unchanged=before==after,eval=not model.training)
            if before!=after or model.training:raise RuntimeError('Model state changed')
            if file_sha(checkpoint_path)!=info['sha256']:raise RuntimeError('Checkpoint file changed')
            del engine,model;gc.collect();torch.cuda.empty_cache()
        report['status']='completed_with_errors' if report['errors'] else 'passed'
    except BaseException as exc:
        report['status']='failed_or_interrupted';report['errors'].append({'stage':'execution','error_type':type(exc).__name__});raise
    finally:
        dump(out/'probe_report.json',report);render(out,plan,report);print('[CAM PROBE REPORT]',out/'probe_report.json');print('[CAM PROBE RESULT]',report['status'])
    if report['errors']:raise RuntimeError('Probe errors preserved; no service or weight changes')

if __name__=='__main__':main()
