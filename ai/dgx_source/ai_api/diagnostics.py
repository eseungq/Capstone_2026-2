"""Offline fixed-model diagnostic automation. No training, policy or serving changes."""
import argparse
import csv
import hashlib
import html
import json
import math
import os
import random
import subprocess
import sys
import traceback
from datetime import datetime,timezone
from pathlib import Path

from PIL import Image,ImageOps
from ai_api.verify_gpu import ROOT,RUN,dump,state_hash

LAYERS=('layers.3.blocks.1.norm1','layers.3.blocks.0.norm1','layers.2.blocks.5.norm1')


def normalize_predictions(rows):
    normalized=[]
    for row in rows:
        truth,pred=int(row['class_id']),int(row['predicted_class'])
        score=float(row['raw_defect_score'])
        if truth not in (0,1) or pred not in (0,1) or not math.isfinite(score) or not 0<=score<=1 or pred!=int(score>=.5):
            raise ValueError('Invalid saved prediction: '+row['image_path'])
        kind=('TP' if pred else 'FN') if truth else ('FP' if pred else 'TN')
        if row.get('kind') is not None and row['kind']!=kind:
            raise ValueError('Conflicting saved confusion kind: '+row['image_path'])
        normalized.append(dict(row,kind=kind))
    return normalized


def reuse_http_report(path,version):
    path=path.resolve()
    if not path.is_relative_to((ROOT/'ai_api/verification').resolve()):
        raise ValueError('Reuse report must be under ai_api/verification')
    report=json.loads(path.read_text())
    expected=json.loads((ROOT/'outputs/evaluation/door_20261015_024950_271668/evaluation_config.json').read_text())
    if (report.get('modelVersion')!=version or report.get('model',{}).get('model_sha256')!=expected['model_sha256']
        or report.get('contractProfile')!='development-proposal-v4-pending'
        or not report.get('independentHttpCamChecksPassed') or not report.get('modelStateUnchanged')
        or report.get('finalTestUsed') is not False):
        raise ValueError('Reuse report model/version/profile or independent check evidence mismatch')
    return report


def choose(rows,internal,cam):
    eligible=[r for r in rows if str(Path(r['image_path']).resolve()) in internal]
    chosen=[]
    # Three from each saved confusion class; include prior CAM examples first.
    prior={str(Path(s['image_path']).resolve()) for s in cam['samples'] if s['target_class']==1}
    for kind in ('TP','TN','FP','FN'):
        candidates=[r for r in eligible if r['kind']==kind]
        candidates.sort(key=lambda r:(str(Path(r['image_path']).resolve()) not in prior,r['image_path']))
        if len(candidates)<3:raise ValueError('Insufficient internal cases: '+kind)
        chosen.extend(candidates[:3])
    return chosen


def mask_indices(values,eligible,fraction=.2,seed=42):
    """Equal-area experimental masks; no labels or ground-truth positions used."""
    count=max(1,int(len(eligible)*fraction))
    ranked=sorted(eligible,key=lambda i:(values[i],i))
    return dict(top=ranked[-count:],low=ranked[:count],random=random.Random(seed).sample(list(eligible),count))


def read(path):
    with path.open(encoding='utf-8-sig') as stream:return list(csv.DictReader(stream))


def cam(engine,path,layer,dest,target='defect'):
    torch,np=engine.torch,engine.np
    captured={}
    handle=engine.model.get_submodule(layer).register_forward_hook(lambda m,a,o:captured.update(activation=o))
    try:
        with torch.enable_grad():
            tensor=engine.tensor(path).unsqueeze(0).cuda().requires_grad_(True)
            logits=engine.model(tensor);activation=captured['activation']
            if activation.ndim!=4 or activation.shape[0]!=1 or activation.shape[1]!=activation.shape[2]:
                raise ValueError('Expected Swin NHWC square spatial activation')
            if target not in ('defect','margin'):raise ValueError('Unknown diagnostic target')
            objective=logits[0,1] if target=='defect' else logits[0,1]-logits[0,0]
            gradient,=torch.autograd.grad(objective,activation)
            if not torch.isfinite(activation).all() or not torch.isfinite(gradient).all():raise ValueError('Nonfinite features')
            a,g=activation.permute(0,3,1,2),gradient.permute(0,3,1,2)
            raw=torch.relu((g.mean((2,3),keepdim=True)*a).sum(1))[0].detach().cpu().numpy()
    finally:handle.remove()
    lo,hi=float(raw.min()),float(raw.max());constant=hi-lo<=max(1e-12,abs(hi)*1e-6)
    if not np.isfinite(raw).all():raise ValueError('Nonfinite CAM')
    np.save(dest/'raw.npy',raw)
    info=dict(layer=layer,targetClass=1,targetObjective=target,featureShape=list(activation.shape),rawMin=lo,rawMax=hi,
              status=('ZERO_MAP' if lo==hi==0 else 'CONSTANT_MAP') if constant else 'GENERATED')
    if constant:return info,None,None
    full=np.asarray(Image.fromarray(((raw-lo)/(hi-lo)).astype('float32')).resize((224,224),Image.Resampling.BILINEAR))
    with Image.open(path) as source:original=ImageOps.exif_transpose(source).convert('RGB')
    contained=ImageOps.contain(original,(224,224),method=Image.Resampling.BICUBIC)
    w,h=contained.size;left,top=round((224-w)*.5),round((224-h)*.5)
    values=np.clip(np.asarray(Image.fromarray(full[top:top+h,left:left+w]).resize(original.size,Image.Resampling.BILINEAR)),0,1)
    heat=np.stack((values,np.zeros_like(values),1-values),axis=-1)*255
    Image.fromarray((np.asarray(original)*.6+heat*.4).clip(0,255).astype('uint8')).save(dest/'overlay.png')
    eligible=[y*224+x for y in range(top,top+h) for x in range(left,left+w)]
    info.update(paddingCrop=[left,top,left+w,top+h],displaySize=list(original.size))
    return info,full,eligible


def occlusion(engine,path,full,eligible):
    torch=engine.torch
    masks=mask_indices(full.reshape(-1).tolist(),eligible)
    x=engine.tensor(path).unsqueeze(0).cuda()
    with torch.inference_mode():
        baseline=engine.model(x);base_score=torch.softmax(baseline,1)[0,1].item()
        result=dict(baselineProbability=base_score,baselineDefectLogit=baseline[0,1].item(),
                    method='replace equal-area 20% non-padding pixels with normalized zero (ImageNet mean); diagnostic only',comparisons={})
        for name,indices in masks.items():
            masked=x.clone();masked.view(1,3,-1)[:,:,indices]=0
            logits=engine.model(masked);score=torch.softmax(logits,1)[0,1].item()
            result['comparisons'][name]=dict(maskedPixels=len(indices),probability=score,probabilityDrop=base_score-score,
                                            defectLogit=logits[0,1].item(),defectLogitDrop=baseline[0,1].item()-logits[0,1].item())
    return result


def render(output,report):
    parts=['<!doctype html><meta charset="utf-8"><title>도어 CAM 진단</title>',
           '<style>body{font-family:sans-serif;max-width:1400px;margin:auto}img{max-width:30%;vertical-align:top}pre{white-space:pre-wrap}section{border-top:1px solid #aaa;padding:16px}</style>',
           '<h1>고정 모델 Grad-CAM 진단</h1><p>오프라인 실험입니다. 후보 레이어는 서비스에 적용되지 않습니다. GOOD의 클래스 1 CAM도 진단용으로만 계산합니다. 결함 위치 정답·성능 개선 증명이 아닙니다.</p>']
    for sample in report['samples']:
        ident=sample['id'];parts.append('<section><h2>'+html.escape(ident+' '+sample['savedKind'])+'</h2>')
        parts.append(f'<img src="{ident}/original_preview.jpg"><img src="{ident}/input224.png">')
        parts.append('<pre>'+html.escape(json.dumps({k:v for k,v in sample.items() if k not in ('layers',)},ensure_ascii=False,indent=2))+'</pre>')
        for layer in sample.get('layers',[]):
            parts.append('<h3>'+html.escape(layer['layer'])+'</h3>')
            if layer.get('status')=='GENERATED':parts.append(f'<a href="{ident}/{layer["slug"]}/overlay.png"><img src="{ident}/{layer["slug"]}/overlay.png"></a>')
            parts.append('<pre>'+html.escape(json.dumps(layer,ensure_ascii=False,indent=2))+'</pre>')
        parts.append('</section>')
    parts.append('<p>촬영범위·각도·반사·결함 가시성은 review.csv에 사람이 기록합니다. 가림 시험은 사진 분포를 바꾸므로 인과나 정확한 결함 위치를 확정하지 않습니다.</p>')
    (output/'index.html').write_text('\n'.join(parts))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model-version',required=True)
    parser.add_argument('--reuse-http-report',type=Path,default=os.environ.get('DOOR_API_REUSE_HTTP_REPORT'),
                        help='Reuse matching completed independent HTTP/CAM checks; preserve score failures')
    parser.add_argument('--selection-file',type=Path,default=os.environ.get('DOOR_API_SELECTION_FILE'),help='Validated disjoint additional sample list')
    args=parser.parse_args()
    output=ROOT/'ai_api/verification'/('diagnose_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir(parents=True)
    report=dict(scope='fixed-model offline diagnostic; not final test or production contract certification',
                finalTestUsed=False,trainingPerformed=False,serviceSettingsChanged=False,modelVersion=args.model_version,
                modelVersionRegistration='unregistered development identifier unless separately registered',samples=[],errors=[],result='running')
    dump(output/'diagnostic.json',report)
    try:
        if args.reuse_http_report:
            cached=reuse_http_report(args.reuse_http_report,args.model_version)
            report.update(httpReport=str(args.reuse_http_report.resolve()),httpReused=True,
                          httpReportSha256=hashlib.sha256(args.reuse_http_report.read_bytes()).hexdigest(),
                          httpExitCode=0 if cached.get('result')=='passed' else 1)
            dump(output/'reused_http_report.json',cached)
            print('[DIAG] Reusing independent HTTP/CAM evidence; previous score failure remains recorded',flush=True)
        else:
            print('[DIAG] HTTP/CAM verification; saved-score failure does not skip later diagnostics',flush=True)
            with (output/'http_verification.log').open('w') as log:
                process=subprocess.Popen([sys.executable,'-u','-m','ai_api.verify_gpu','--model-version',args.model_version],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                try:
                    for line in process.stdout:
                        print(line,end='',flush=True);log.write(line);log.flush()
                        if line.startswith('Verification report:'):report['httpReport']=line.split(':',1)[1].strip()
                    report['httpExitCode']=process.wait()
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:process.kill();process.wait()
        with (ROOT/'outputs/manifests/door_internal_validation.csv').open(encoding='utf-8-sig') as stream:
            internal={str(Path(r['image_path']).resolve()) for r in csv.DictReader(stream)}
        rows=normalize_predictions(read(RUN/'best_internal_validation_predictions.csv'))
        if len(internal)!=2039 or len(rows)!=2039 or {str(Path(r['image_path']).resolve()) for r in rows}!=internal:
            raise ValueError('Internal-validation prediction/manifest set mismatch')
        old_cam=json.loads((ROOT/'outputs/evaluation/door_20261015_024950_271668/gradcam/metadata.json').read_text())
        if args.selection_file:
            from ai_api.setup_followup import load_selection
            selected=load_selection(args.selection_file,rows)
            report['additionalSelectionSource']=str(args.selection_file)
        else:selected=choose(rows,internal,old_cam)
        dump(output/'selection.json',selected)
        from prototype.engine import Engine
        engine=Engine();before=state_hash(engine);torch=engine.torch
        report['model']=engine.metadata
        frame_assignments=json.loads(args.selection_file.read_text()).get('frames',{}) if args.selection_file else {}
        for index,row in enumerate(selected):
            ident=f'sample_{index:02d}';dest=output/ident;dest.mkdir();path=Path(row['image_path'])
            sample=dict(id=ident,imagePath=str(path),savedKind=row['kind'],imageSha256=hashlib.sha256(path.read_bytes()).hexdigest(),layers=[])
            if str(path) in frame_assignments:sample['framingAssessment']=frame_assignments[str(path)]
            report['samples'].append(sample)
            try:
                tensor=engine.tensor(path);sample['inputTensorSha256']=hashlib.sha256(tensor.contiguous().numpy().tobytes()).hexdigest()
                with Image.open(path) as source:original=ImageOps.exif_transpose(source).convert('RGB')
                sample['displaySize']=list(original.size);preview=original.copy();preview.thumbnail((1200,1200));preview.save(dest/'original_preview.jpg')
                ImageOps.pad(original,(224,224),method=Image.Resampling.BICUBIC,color=engine.fill).save(dest/'input224.png')
                direct=engine.predict(path);sample['singleScore']=direct['raw_defect_score'];sample['savedBatch8Score']=float(row['raw_defect_score'])
                # Reconstruct original ordered batch (last batch may be smaller).
                position=next(i for i,r in enumerate(rows) if r['image_path']==row['image_path']);start=position//8*8;batch_rows=rows[start:start+8]
                batch=torch.stack([engine.tensor(Path(r['image_path'])) for r in batch_rows]).cuda()
                with torch.inference_mode():
                    logits=engine.model(batch);scores=torch.softmax(logits,1);score=scores[position-start,1].item()
                sample.update(recreatedBatch8Score=score,recreatedBatchSize=len(batch_rows),batchIndex=position-start,
                    singleVsSavedWithinOriginalTolerance=math.isclose(sample['singleScore'],sample['savedBatch8Score'],abs_tol=1e-6,rel_tol=1e-4),
                    recreatedBatchVsSavedWithinOriginalTolerance=math.isclose(score,sample['savedBatch8Score'],abs_tol=1e-6,rel_tol=1e-4))
                sample['batchInputTensorSha256']=hashlib.sha256(batch[position-start].detach().cpu().contiguous().numpy().tobytes()).hexdigest()
                del batch,logits,scores
                memory_before=torch.cuda.memory_allocated()
                for layer in LAYERS:
                    slug=layer.replace('.','_');folder=dest/slug;folder.mkdir()
                    try:
                        info,full,eligible=cam(engine,path,layer,folder);info['slug']=slug
                        if full is not None:info['occlusion']=occlusion(engine,path,full,eligible)
                        if layer==LAYERS[0]:
                            reference=dest/'production_reference';reference.mkdir()
                            existing=engine.explain(path,reference,1)
                            saved_raw=engine.np.load(reference/'cam1_raw.npy');new_raw=engine.np.load(folder/'raw.npy')
                            info['productionRawMaxDifference']=float(engine.np.max(engine.np.abs(saved_raw-new_raw)))
                            info['productionRawMatches']=bool(engine.np.allclose(saved_raw,new_raw,atol=1e-12,rtol=1e-6))
                            info['productionConstantMatches']=existing['constant']==(full is None)
                            if not info['productionRawMatches'] or not info['productionConstantMatches']:report['errors'].append(ident+': production CAM mismatch')
                    except Exception as exc:
                        info=dict(layer=layer,slug=slug,status='DIAGNOSTIC_ERROR',error=type(exc).__name__+': '+str(exc))
                        report['errors'].append(ident+': '+layer+': '+str(exc))
                    sample['layers'].append(info);dump(folder/'diagnostic.json',info)
                torch.cuda.synchronize();sample.update(gpuAllocatedBefore=memory_before,gpuAllocatedAfter=torch.cuda.memory_allocated(),gpuReserved=torch.cuda.memory_reserved())
            except Exception as exc:
                sample['error']=type(exc).__name__+': '+str(exc);report['errors'].append(ident+': '+str(exc))
            dump(output/'diagnostic.json',report);render(output,report)
            print('[DIAG SAMPLE]',ident,row['kind'],'complete',flush=True)
        report['modelStateUnchanged']=state_hash(engine)==before and not engine.model.training
        if not report['modelStateUnchanged']:raise RuntimeError('Model state changed')
        with (output/'review.csv').open('w',newline='') as stream:
            fields=['id','image_path','saved_kind','original_visibility','input224_visibility','framing','angle','reflection','cam_relevance','notes']
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for sample in report['samples']:writer.writerow(dict(id=sample['id'],image_path=sample['imagePath'],saved_kind=sample['savedKind']))
        report['singleVsSavedMismatchCount']=sum(not s.get('singleVsSavedWithinOriginalTolerance',False) for s in report['samples'])
        report['recreatedBatchVsSavedMismatchCount']=sum(not s.get('recreatedBatchVsSavedWithinOriginalTolerance',False) for s in report['samples'])
        report['result']='diagnostic_complete_with_findings' if not report['errors'] else 'diagnostic_incomplete'
        report['readyForProduction']=False;report['humanReviewComplete']=False
    except BaseException as exc:
        report.update(result='failed_or_interrupted',failureType=type(exc).__name__,failure=str(exc))
        (output/'failure_traceback.txt').write_text(traceback.format_exc())
        raise
    finally:
        dump(output/'diagnostic.json',report);render(output,report)
        print('[DIAGNOSTIC REPORT]',output/'diagnostic.json',flush=True)
        print('[REVIEW HTML]',output/'index.html',flush=True)
    try:
        from ai_api.prepare_review import build
        build(output/'diagnostic.json')
    except Exception as exc:
        report['errors'].append('Review preparation: '+str(exc))
        dump(output/'diagnostic.json',report)
    if report['errors'] or report.get('httpExitCode')!=0 or report['recreatedBatchVsSavedMismatchCount'] or report['singleVsSavedMismatchCount']:
        raise SystemExit(1)  # Findings never turn failed reproduction into a pass.


if __name__=='__main__':main()
