"""CPU-only frozen-model CAM comparison; production service and GPU are untouched."""
import argparse,ast,hashlib,html,json,math,time,importlib.metadata
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import torch,timm
from PIL import Image,ImageOps
from torch.utils.data import Dataset
from torchvision.transforms import functional as TF
from timm.data import resolve_model_data_config
from ai_api.e02_engine import validate_candidate,ROOT
LAYERS=['layers.3.blocks.1.norm1','layers.3.blocks.0.norm1','layers.2.blocks.5.norm1']
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def digest(model):
 h=hashlib.sha256()
 for k,v in model.state_dict().items():h.update(k.encode());h.update(v.detach().cpu().contiguous().numpy().tobytes())
 return h.hexdigest()
def scores(model,x):
 with torch.inference_mode():z=model(x)
 return dict(probability=torch.softmax(z,1)[0,1].item(),defectLogit=z[0,1].item(),margin=(z[0,1]-z[0,0]).item())
def cam(model,x,layer,target):
 cache={};hook=model.get_submodule(layer).register_forward_hook(lambda m,a,o:cache.update(a=o))
 try:
  with torch.enable_grad():
   z=model(x.detach().clone().requires_grad_(True));a=cache['a'];objective=z[0,1] if target=='defect' else z[0,1]-z[0,0]
   g,=torch.autograd.grad(objective,a)
   raw=torch.relu((g.permute(0,3,1,2).mean((2,3),keepdim=True)*a.permute(0,3,1,2)).sum(1))[0].detach().numpy()
 finally:hook.remove()
 lo,hi=float(raw.min()),float(raw.max());constant=hi-lo<=max(1e-12,abs(hi)*1e-6)
 if not np.isfinite(raw).all():raise RuntimeError('Nonfinite CAM')
 info=dict(layer=layer,targetObjective=target,featureShape=list(a.shape),rawMin=lo,rawMax=hi,status=('ZERO_MAP' if lo==hi==0 else 'CONSTANT_MAP') if constant else 'GENERATED')
 full=None if constant else np.asarray(Image.fromarray(((raw-lo)/(hi-lo)).astype('float32')).resize((224,224),Image.Resampling.BILINEAR)).copy()
 return info,raw,full

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=False)
 torch.set_num_threads(2);torch.set_num_interop_threads(1)
 if torch.cuda.is_available():raise RuntimeError('CPU diagnostic must have CUDA_VISIBLE_DEVICES empty')
 m,run,cfg=validate_candidate()
 versions={name:importlib.metadata.version(name) for name in cfg['versions']}
 if versions!=cfg['versions']:raise RuntimeError('Diagnostic package versions differ from training')
 torch.manual_seed(42);np.random.seed(42)
 model=timm.create_model(cfg['config']['model_name'],pretrained=False,num_classes=2)
 checkpoint=torch.load(run/'best.pt',map_location='cpu',weights_only=False);assert checkpoint['epoch']==2;model.load_state_dict(checkpoint['model_state_dict'],strict=True);del checkpoint;model=model.float().cpu().eval();before=digest(model)
 dc=resolve_model_data_config(model);mean,std=dc['mean'],dc['std'];fill=tuple(round(v*255) for v in mean)
 src=ROOT/m['trainingSource'];tree=ast.parse(src.read_text());mainnode=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');node=next(n for n in mainnode.body if isinstance(n,ast.ClassDef) and n.name=='DoorDataset')
 ns=dict(Dataset=Dataset,Image=Image,ImageOps=ImageOps,TF=TF,CONFIG=cfg['config'],mean=mean,std=std,fill=fill);exec(compile(ast.Module(body=[node],type_ignores=[]),str(src),'exec'),ns);dataset=ns['DoorDataset']
 report=dict(status='running',device='cpu',threads=2,scope='three fixed connection fixtures; not independent evaluation or production CAM replacement',modelVersion=m['modelVersion'],checkpointSHA256=m['checkpointSHA256'],trainingPerformed=False,productionChanged=False,finalTestRead=False,samples=[])
 dump(out/'report.json',report)
 for index in [3,0,1]:
  sample=m['samples'][index];path=Path(sample['image_path']);blob=path.read_bytes();assert hashlib.sha256(blob).hexdigest()==sample['image_sha256']
  folder=out/f'sample_{index}';folder.mkdir();x=dataset([dict(image_path=str(path),class_id=0)])[0][0].unsqueeze(0).cpu();base=scores(model,x)
  with Image.open(path) as im:original=ImageOps.exif_transpose(im).convert('RGB')
  contained=ImageOps.contain(original,(224,224),method=Image.Resampling.BICUBIC);w,h=contained.size;left,top=round((224-w)*.5),round((224-h)*.5)
  display=original.copy();display.thumbnail((1200,1200));display.save(folder/'original.jpg')
  inputimage=ImageOps.pad(original,(224,224),method=Image.Resampling.BICUBIC,color=fill);inputimage.save(folder/'input224.png')
  original224=np.asarray(inputimage,dtype=np.float32)
  expected=sample.get('verified_single_score')
  if expected is None and index==3:expected=.9999741315841675
  row=dict(id=f'sample_{index}',storedKind=sample['kind'],sourceSHA256=sample['image_sha256'],displaySize=list(original.size),baselineCPU=base,referenceGPUScore=expected,cpuVsGPUWithinOriginalTolerance=math.isclose(base['probability'],expected,abs_tol=1e-6,rel_tol=1e-4) if expected is not None else None,layers=[])
  report['samples'].append(row)
  for layer in LAYERS:
   for target in ['defect','margin']:
    slug=layer.replace('.','_')+'_'+target;dest=folder/slug;dest.mkdir();info,raw,full=cam(model,x,layer,target);np.save(dest/'raw.npy',raw);info['slug']=slug;row['layers'].append(info)
    if full is not None:
     heat=np.stack((full,np.zeros_like(full),1-full),axis=-1)*255
     Image.fromarray(np.clip(original224*.6+heat*.4,0,255).astype('uint8')).save(dest/'input_cam.png')
     vals=np.asarray(Image.fromarray(full[top:top+h,left:left+w]).resize(display.size,Image.Resampling.BILINEAR));pixels=np.asarray(display,dtype=np.float32)
     colors=np.stack((vals,np.zeros_like(vals),1-vals),axis=-1)*255
     Image.fromarray(np.clip(pixels*.6+colors*.4,0,255).astype('uint8')).save(dest/'overlay.jpg',quality=90)
     info['leftSeventhMeanRelativeCAM']=float(full[top:top+h,left:left+max(1,w//7)].mean())
     if index==3:
      # Annotation A was visually checked against EXIF-corrected display in the separate CPU diagnostic.
      box=[2099.7224209938036,736.7441860465116,2709.240310077519,877.9534883720928]
      sx,sy=w/original.width,h/original.height
      rect=(left+int(box[0]*sx),top+int(box[1]*sy),left+math.ceil(box[2]*sx),top+math.ceil(box[3]*sy));x0,y0,x1,y1=rect;rw,rh=x1-x0,y1-y0
      choices=[]
      for yy in range(top,top+h-rh+1):
       for xx in range(left,left+w-rw+1):
        if xx+rw<=x0 or xx>=x1 or yy+rh<=y0 or yy>=y1:choices.append((float(full[yy:yy+rh,xx:xx+rw].mean()),(xx,yy,xx+rw,yy+rh)))
      high=max(choices)[1];low=min(choices)[1]
      regions=dict(scratch_annotation_A=rect,high_cam_equal_area_control=high,low_cam_equal_area_control=low)
      blur=TF.gaussian_blur(x,[7,7],[2.,2.]);effects=[]
      for name,rect2 in regions.items():
       xa,ya,xb,yb=rect2
       for method in ['imagenet_mean','blur']:
        altered=x.clone();altered[:,:,ya:yb,xa:xb]=0 if method=='imagenet_mean' else blur[:,:,ya:yb,xa:xb]
        sc=scores(model,altered);effects.append(dict(region=name,rect224=list(rect2),pixels=(xb-xa)*(yb-ya),method=method,**sc,probabilityDrop=base['probability']-sc['probability'],defectLogitDrop=base['defectLogit']-sc['defectLogit'],marginDrop=base['margin']-sc['margin']))
      info['scratchROI224']=list(rect);info['roiProvenance']='source annotation A visually checked on corrected display, analyst observation; not whole-image ground truth';info['occlusion']=effects;info['roiMeanRelativeCAM']=float(full[y0:y1,x0:x1].mean());info['occlusionWarning']='input perturbations are diagnostic and out-of-distribution; controls are not certified defect-free'
    dump(dest/'cam.json',info);dump(out/'report.json',report);print('[CPU CAM]',index,layer,target,info['status'],flush=True)
 report['modelStateUnchanged']=digest(model)==before;assert report['modelStateUnchanged'];report['status']='completed_cpu_diagnostic_not_production_improvement_verified';report['checkpointUnchanged']=hashlib.sha256((run/'best.pt').read_bytes()).hexdigest()==m['checkpointSHA256'];assert report['checkpointUnchanged'];dump(out/'report.json',report)
 parts=['<!doctype html><meta charset="utf-8"><title>고정 e02 CAM 비교</title><style>body{font-family:sans-serif;max-width:1400px;margin:auto}img{max-width:460px}section{border-top:1px solid #aaa;padding:18px}pre{white-space:pre-wrap}</style><h1>e02 CPU 진단용 CAM 비교</h1><p>운영 서버·가중치·전처리 변경 없음. 같은 사진의 색상이 흠집 근처에 나온다는 이유로 운영 레이어를 선택하지 않습니다. GOOD CAM은 진단 전용입니다.</p>']
 for row in report['samples']:
  sid=row['id'];parts.append('<section><h2>'+sid+' '+html.escape(row['storedKind'])+'</h2><img src="'+sid+'/original.jpg"><img src="'+sid+'/input224.png"><p>'+html.escape(str(row['baselineCPU']))+'</p>')
  for info in row['layers']:
   parts.append('<h3>'+html.escape(info['layer']+' / '+info['targetObjective'])+'</h3>')
   if info['status']=='GENERATED':parts.append('<img src="'+sid+'/'+info['slug']+'/overlay.jpg"><img src="'+sid+'/'+info['slug']+'/input_cam.png">')
   parts.append('<pre>'+html.escape(json.dumps(info,ensure_ascii=False,indent=2))+'</pre>')
  parts.append('</section>')
 (out/'index.html').write_text('\n'.join(parts));print('[CPU DIAG DONE]',out,flush=True)
if __name__=='__main__':main()
