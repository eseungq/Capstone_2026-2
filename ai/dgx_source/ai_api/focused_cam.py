"""Human-ROI occlusion and Grad-CAM objective comparison; fixed model only."""
import argparse
import hashlib
import json
import math
import os
import random
import traceback
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw,ImageFilter
from ai_api.diagnostics import ROOT,LAYERS,cam
from ai_api.verify_gpu import dump,state_hash


def roi_to_input(box,display_size):
    if len(box)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in box):raise ValueError('Invalid ROI')
    x0,y0,x1,y1=box
    if not 0<=x0<x1<=1 or not 0<=y0<y1<=1:raise ValueError('Draw a nonempty ROI inside image')
    w,h=ImageOps.contain(Image.new('L',tuple(display_size)),(224,224),Image.Resampling.BICUBIC).size
    left,top=round((224-w)*.5),round((224-h)*.5)
    rect=(left+int(x0*w),top+int(y0*h),min(left+w,left+math.ceil(x1*w)),min(top+h,top+math.ceil(y1*h)))
    return rect,(left,top,left+w,top+h)


def controls(rect,valid,seed=42):
    x0,y0,x1,y1=rect;left,top,right,bottom=valid;w,h=x1-x0,y1-y0
    choices=[]
    for y in range(top,bottom-h+1):
        for x in range(left,right-w+1):
            if x+w<=x0 or x>=x1 or y+h<=y0 or y>=y1:choices.append((x,y,x+w,y+h))
    if not choices:raise ValueError('ROI too large for an equal-size nonoverlapping control; draw a tighter region')
    return random.Random(seed).sample(choices,min(3,len(choices)))


def validate_roi(payload):
    if payload.get('schema')=='door-cam-regions-v2':return validate_regions(payload)
    if payload.get('schema')!='door-cam-roi-v1':raise ValueError('Wrong ROI format')
    source=Path(payload['sourceReport']).resolve()
    if not source.is_relative_to((ROOT/'ai_api/verification').resolve()):raise ValueError('Invalid diagnostic source')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=payload['sourceReportSha256']:raise ValueError('Source report changed')
    samples={s['id']:s for s in json.loads(source.read_text())['samples']}
    requested=payload['cases']
    if len(requested)!=3 or {c['id'] for c in requested}!={'sample_00','sample_01','sample_02'}:raise ValueError('Expected three selected TP cases')
    selected=[]
    for case in requested:
        sample=samples[case['id']]
        if sample['savedKind']!='TP' or case['imageSha256']!=sample['imageSha256']:raise ValueError('ROI image mismatch')
        if hashlib.sha256(Path(sample['imagePath']).read_bytes()).hexdigest()!=case['imageSha256']:raise ValueError('Source image changed')
        rect,valid=roi_to_input(case['box'],sample['displaySize']);comparisons=controls(rect,valid)
        selected.append((sample,rect,comparisons))
    return selected


def matched_control(rect,valid,center):
    if len(center)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in center):
        raise ValueError('Invalid comparison center')
    left,top,right,bottom=valid;w,h=rect[2]-rect[0],rect[3]-rect[1]
    x=round(left+center[0]*(right-left)-w/2);y=round(top+center[1]*(bottom-top)-h/2)
    control=(x,y,x+w,y+h)
    if not (left<=x and top<=y and x+w<=right and y+h<=bottom):raise ValueError('Comparison rectangle reaches padding; choose a center farther from image edge')
    if not (x+w<=rect[0] or x>=rect[2] or y+h<=rect[1] or y>=rect[3]):raise ValueError('Target and comparison overlap')
    return control


def validate_regions(payload):
    source=Path(payload['sourceReport']).resolve()
    if not source.is_relative_to((ROOT/'ai_api/verification').resolve()):raise ValueError('Invalid region source')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=payload['sourceReportSha256']:raise ValueError('Source report changed')
    samples={s['id']:s for s in json.loads(source.read_text())['samples']};cases=payload['cases']
    if len(cases)!=3 or {c['id'] for c in cases}!={'sample_08','sample_09','sample_13'}:raise ValueError('Expected selected FP/FP/FN cases')
    selected=[]
    for case in cases:
        sample=samples[case['id']]
        if case['imageSha256']!=sample['imageSha256'] or hashlib.sha256(Path(sample['imagePath']).read_bytes()).hexdigest()!=case['imageSha256']:raise ValueError('Region image mismatch')
        if not 1<=len(case['regions'])<=4:raise ValueError('Specify 1 to 4 observable regions per image; no forced defect ROI')
        for i,region in enumerate(case['regions']):
            if region['type'] not in ('defect','reflection','structure','background','uncertain'):raise ValueError('Unsupported region category')
            if region.get('controlContent') not in ('flat','reflection','structure','background','uncertain'):raise ValueError('Record comparison content')
            rect,valid=roi_to_input(region['box'],sample['displaySize']);control=matched_control(rect,valid,region['controlCenter'])
            ident=case['id']+f'_region_{i:02d}'
            selected.append((dict(sample,id=ident,_sourceSampleId=case['id'],_regionType=region['type'],
                                 _controlContent=region['controlContent'],_regionNotes=region.get('notes','')),rect,[control]))
    return selected


def scores(engine,x):
    torch=engine.torch
    with torch.inference_mode():
        logits=engine.model(x)
        if not torch.isfinite(logits).all():raise ValueError('Nonfinite diagnostic logits')
        return dict(probability=torch.softmax(logits,1)[0,1].item(),defectLogit=logits[0,1].item(),margin=(logits[0,1]-logits[0,0]).item())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--roi-file',type=Path,default=os.environ.get('DOOR_API_ROI_FILE'))
    parser.add_argument('--model-version',required=True);args=parser.parse_args()
    if args.roi_file is None:parser.error('--roi-file or DOOR_API_ROI_FILE required')
    payload=json.loads(args.roi_file.read_text());selected=validate_roi(payload)
    output=ROOT/'ai_api/verification'/('focused_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    dump(output/'human_roi_original.json',payload)
    report=dict(finalTestUsed=False,training=False,serviceChanged=False,modelVersion=args.model_version,
                modelVersionRegistration='unregistered diagnostic identifier',roiSourceSha256=hashlib.sha256(args.roi_file.read_bytes()).hexdigest(),
                result='running',samples=[],limitations='ROI neighborhood masking changes image distribution; controls can contain other defects; no causal or localization guarantee')
    try:
        from prototype.engine import Engine
        engine=Engine();torch,np=engine.torch,engine.np;before=state_hash(engine);report['model']=engine.metadata
        for sample,rect,comparisons in selected:
            ident=sample['id'];dest=output/ident;dest.mkdir();path=Path(sample['imagePath'])
            x=engine.tensor(path).unsqueeze(0).cuda();baseline=scores(engine,x)
            with Image.open(path) as source:original=ImageOps.exif_transpose(source).convert('RGB')
            input_image=ImageOps.pad(original,(224,224),Image.Resampling.BICUBIC,color=engine.fill)
            input_image.save(dest/'input224.png');preview=original.copy();preview.thumbnail((1200,1200));preview.save(dest/'original.jpg')
            marked=input_image.copy();draw=ImageDraw.Draw(marked)
            target_name=sample.get('_regionType','defect')
            for label,box,color in [(target_name,rect,'red')]+[(f'control{i}',r,'lime') for i,r in enumerate(comparisons)]:
                draw.rectangle((box[0],box[1],box[2]-1,box[3]-1),outline=color,width=2);draw.text((box[0],box[1]),label,fill=color)
            marked.save(dest/'regions.png')
            blurred=input_image.filter(ImageFilter.GaussianBlur(radius=7))
            from torchvision.transforms import functional as TF
            blur_tensor=TF.normalize(TF.to_tensor(blurred),engine.metadata['normalization']['mean'],engine.metadata['normalization']['std']).unsqueeze(0).cuda()
            record=dict(id=ident,role=sample.get('_regionType','comparison_success' if ident=='sample_00' else 'explanation_failure'),
                        sourceSampleId=sample.get('_sourceSampleId',ident),savedKind=sample['savedKind'],controlContent=sample.get('_controlContent'),notes=sample.get('_regionNotes',''),baseline=baseline,regions=[],cams=[])
            report['samples'].append(record)
            for name,box in [(target_name,rect)]+[(f'control{i}',r) for i,r in enumerate(comparisons)]:
                x0,y0,x1,y1=box
                for fill in ('mean','blur'):
                    masked=x.clone();masked[:,:,y0:y1,x0:x1]=0 if fill=='mean' else blur_tensor[:,:,y0:y1,x0:x1]
                    result=scores(engine,masked)
                    record['regions'].append(dict(name=name,box=list(box),pixels=(x1-x0)*(y1-y0),fill=fill,scores=result,
                        drop={k:baseline[k]-result[k] for k in baseline}))
                    # Save the actual perturbed model input for visual sanity checking.
                    restored=masked[0].detach().cpu().clone()
                    for channel,mean,std in zip(restored,engine.metadata['normalization']['mean'],engine.metadata['normalization']['std']):channel.mul_(std).add_(mean)
                    TF.to_pil_image(restored.clamp(0,1)).save(dest/f'masked_{name}_{fill}.png')
            for layer in LAYERS:
                for target in ('defect','margin'):
                    folder=dest/(layer.replace('.','_')+'_'+target);folder.mkdir()
                    info,full,eligible=cam(engine,path,layer,folder,target=target)
                    info['folder']=folder.name
                    if full is not None:
                        x0,y0,x1,y1=rect
                        info['roiNormalizedCamMean']=float(full[y0:y1,x0:x1].mean())
                        info['roiNormalizedCamMax']=float(full[y0:y1,x0:x1].max())
                        info['roiInterpolatedRawCamMean']=info['rawMin']+(info['rawMax']-info['rawMin'])*info['roiNormalizedCamMean']
                    else:
                        info['roiNormalizedCamMean']=None;info['roiNormalizedCamMax']=None
                        info['roiInterpolatedRawCamMean']=info['rawMin']
                        # This measures relative map response, not defect-location accuracy.
                    record['cams'].append(info);dump(folder/'cam.json',info)
            dump(output/'focused.json',report);print('[FOCUSED SAMPLE]',ident,'complete',flush=True)
        report['modelStateUnchanged']=state_hash(engine)==before and not engine.model.training
        if not report['modelStateUnchanged']:raise ValueError('Model state changed')
        report['result']='diagnostic_complete_requires_review'
    except BaseException as exc:
        report.update(result='failed_or_interrupted',failureType=type(exc).__name__,failure=str(exc));(output/'failure.txt').write_text(traceback.format_exc());raise
    finally:
        dump(output/'focused.json',report)
        import html
        parts=['<!doctype html><meta charset="utf-8"><title>결함 ROI 진단</title><style>img{max-width:30%;max-height:360px;object-fit:contain}pre{white-space:pre-wrap}</style><h1>결함 ROI 진단</h1><p>실험용 비교이며 서비스 변경이나 결함 위치 성능 보증이 아닙니다.</p>']
        for record in report['samples']:
            ident=record['id'];parts.extend([f'<h2>{ident}</h2>',f'<img src="{ident}/original.jpg"><img src="{ident}/regions.png">','<details><summary>가림 시험 수치</summary><pre>'+html.escape(json.dumps(record['regions'],ensure_ascii=False,indent=2))+'</pre></details>'])
            for info in record['cams']:
                parts.append('<h3>'+html.escape(info['layer']+' / '+info['targetObjective']+' / '+info['status'])+'</h3>')
                if info['status']=='GENERATED':parts.append(f'<a href="{ident}/{info["folder"]}/overlay.png"><img src="{ident}/{info["folder"]}/overlay.png"></a>')
        (output/'index.html').write_text('\n'.join(parts));print('[FOCUSED REPORT]',output/'focused.json',flush=True);print('[FOCUSED HTML]',output/'index.html',flush=True)


if __name__=='__main__':main()
