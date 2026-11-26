"""Diagnose signed Grad-CAM and compare explanation methods without model updates."""
import argparse,ast,hashlib,html,importlib.metadata,json,math,os,time,zipfile
from pathlib import Path
import numpy as np
import torch,timm
from PIL import Image,ImageOps
from torch.utils.data import Dataset
from torchvision.transforms import functional as TF
from timm.data import resolve_model_data_config
from ai_api.e02_engine import validate_candidate,ROOT
from ai_api.e02_integration.diagnose_cam_cpu import digest,scores

METHODS=('GradCAM','HiResCAM','LayerCAM')

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def dump(path,data):
 temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n');temporary.replace(path)

def map_status(raw):
 lo,hi=float(raw.min()),float(raw.max())
 constant=hi-lo<=max(1e-12,abs(hi)*1e-6)
 return ('ZERO_MAP' if lo==hi==0 else 'CONSTANT_MAP') if constant else 'GENERATED'

def equations(a,g):
 return dict(GradCAM=(g.mean((2,3),keepdim=True)*a).sum(1)[0],HiResCAM=(g*a).sum(1)[0],LayerCAM=(g.clamp(min=0)*a).sum(1)[0])

def self_test():
 a=torch.ones(1,2,2,2);positive=torch.ones_like(a)
 e=equations(a,positive);assert torch.equal(e['GradCAM'],e['HiResCAM']) and torch.equal(e['HiResCAM'],e['LayerCAM'])
 negative=-positive;e=equations(a,negative)
 assert torch.count_nonzero(negative)>0 and all(map_status(torch.relu(v).numpy())=='ZERO_MAP' for v in e.values())
 varying=torch.tensor([[[[1.,-1.],[1.,-1.]],[[1.,-1.],[1.,-1.]]]])
 e=equations(a,varying);assert torch.count_nonzero(e['GradCAM'])==0 and torch.relu(e['HiResCAM']).max()>0
 return dict(constantPositiveGradient='passed',nonzeroNegativeGradientCanYieldZeroMap='passed',spatialAveragingCancellation='passed')

def load_reference_functions(frozen):
 result={};namespace=dict(np=np)
 for name,cls,method in [('grad_cam.py','GradCAM','get_cam_weights'),('hirescam.py','HiResCAM','get_cam_image'),('layer_cam.py','LayerCAM','get_cam_image')]:
  meta=frozen['references'][name];path=Path(meta['path']);assert sha(path)==meta['sha256']
  tree=ast.parse(path.read_text());c=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls);f=next(n for n in c.body if isinstance(n,ast.FunctionDef) and n.name==method)
  exec(compile(ast.Module(body=[f],type_ignores=[]),str(path),'exec'),namespace)
  result[cls]=namespace[method]
 return result

def reference_equations(a,g,functions):
 weights=functions['GradCAM'](None,None,None,None,a,g)
 return dict(GradCAM=(weights[:,:,None,None]*a).sum(axis=1)[0],HiResCAM=functions['HiResCAM'](None,None,None,None,a,g,False)[0],LayerCAM=functions['LayerCAM'](None,None,None,None,a,g,False)[0])

def analyse(model,x,layer):
 cache={};hook=model.get_submodule(layer).register_forward_hook(lambda module,args,output:cache.update(a=output))
 try:
  with torch.enable_grad():
   z=model(x.detach().clone().requires_grad_(True));activation=cache['a'];gradient,=torch.autograd.grad(z[0,1],activation)
   a=activation.permute(0,3,1,2);g=gradient.permute(0,3,1,2)
   assert torch.isfinite(a).all() and torch.isfinite(g).all()
   signed={key:value.detach().cpu().numpy().copy() for key,value in equations(a,g).items()}
   raw={key:torch.relu(value).detach().cpu().numpy().copy() for key,value in equations(a,g).items()}
   assert all(np.isfinite(value).all() for value in list(signed.values())+list(raw.values()))
   aa=a.detach().cpu().numpy().copy();gg=g.detach().cpu().numpy().copy()
 finally:hook.remove()
 gc=signed['GradCAM'];nonzero=int(np.count_nonzero(gg));status=map_status(raw['GradCAM'])
 if status!='ZERO_MAP':reason='positive_gradcam_values_present'
 elif nonzero==0:reason='all_gradient_entries_zero'
 elif np.any(gc<0) and not np.any(gc>0):reason='nonzero_gradient_but_signed_gradcam_nonpositive_removed_by_relu'
 else:reason='nonzero_gradient_but_averaged_weighted_sum_zero'
 stats=dict(featureShape=list(activation.shape),gradientMin=float(gg.min()),gradientMax=float(gg.max()),gradientMeanAbs=float(np.abs(gg).mean()),nonzeroGradientEntries=nonzero,totalGradientEntries=int(gg.size),signedGradCAMMin=float(gc.min()),signedGradCAMMax=float(gc.max()),signedGradCAMPositiveCells=int(np.count_nonzero(gc>0)),signedGradCAMNegativeCells=int(np.count_nonzero(gc<0)),gradcamZeroReason=reason)
 return signed,raw,aa,gg,stats

def colours(values,palette):
 if palette=='legacy':return np.stack((values,np.zeros_like(values),1-values),axis=-1)*255
 return np.stack([np.clip(1.5-np.abs(4*values-centre),0,1) for centre in (3,2,1)],axis=-1)*255

def render_styles(folder,raw,original_size):
 lo,hi=float(raw.min()),float(raw.max())
 full=np.asarray(Image.fromarray(((raw-lo)/(hi-lo)).astype('float32')).resize((224,224),Image.Resampling.BILINEAR)).copy()
 before=hashlib.sha256(full.tobytes()).hexdigest()
 with Image.open(folder.parents[2]/'original.jpg') as src:display=src.convert('RGB')
 width,height=original_size
 # Same Pillow integer contain/pad coordinates as the fixed training preprocessor.
 contained=ImageOps.contain(Image.new('RGB',(width,height)),(224,224),method=Image.Resampling.BICUBIC)
 w,h=contained.size;left,top=round((224-w)*.5),round((224-h)*.5)
 values=np.asarray(Image.fromarray(full[top:top+h,left:left+w]).resize(display.size,Image.Resampling.BILINEAR))
 pixels=np.asarray(display,dtype=np.float32)
 files={}
 for name,alpha in [('legacy',.4),('jet',.5),('jet_strong',.65)]:
  heat=colours(values,'legacy' if name=='legacy' else 'jet')
  filename=name+'.jpg';Image.fromarray(np.clip(pixels*(1-alpha)+heat*alpha,0,255).astype('uint8')).save(folder/filename,quality=92);files[name]=filename
 assert hashlib.sha256(full.tobytes()).hexdigest()==before
 return dict(files=files,normalized224SHA256=before,styleChangesOnlyColourAndOpacity=True,paddingCrop=[left,top,left+w,top+h])

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);arg=parser.parse_args();frozen=json.loads(arg.manifest.read_text());out=arg.manifest.parent
 assert os.environ.get('CUDA_VISIBLE_DEVICES')=='' and not torch.cuda.is_available()
 Image.MAX_IMAGE_PIXELS=120000000;torch.set_num_threads(2);torch.set_num_interop_threads(1)
 tests=self_test();functions=load_reference_functions(frozen)
 versions={key:importlib.metadata.version(key) for key in frozen['versions']};assert versions==frozen['versions'];validate_candidate()
 source=Path(frozen['datasetSource']);assert sha(source)==frozen['datasetSourceSHA256']
 tree=ast.parse(source.read_text());mn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');dn=next(n for n in mn.body if isinstance(n,ast.ClassDef) and n.name=='DoorDataset')
 assert hashlib.sha256(ast.dump(dn,include_attributes=False).encode()).hexdigest()==frozen['datasetASTSHA256']
 report=dict(status='running',device='cpu',threads=2,manifestSHA256=sha(arg.manifest),versions=versions,selfTests=tests,models={},cases=[],productionChanged=False,newTrainingPerformed=False,finalTestImagesRead=False,independentPerformanceEvaluation=False,packageInstalled=False,referenceScope=frozen['referenceScope']);dump(out/'report.json',report);started=time.monotonic()
 for model_name in ('old','new'):
  run=Path(frozen['modelRuns'][model_name]);assert sha(run/'best.pt')==frozen['modelHashes'][model_name] and sha(run/'run_config.json')==frozen['configHashes'][model_name]
  cfg=json.loads((run/'run_config.json').read_text());torch.manual_seed(42);np.random.seed(42)
  model=timm.create_model(frozen['modelName'],pretrained=False,num_classes=2);checkpoint=torch.load(run/'best.pt',map_location='cpu',weights_only=False)
  assert checkpoint['epoch']==frozen['epochs'][model_name] and json.loads(json.dumps(checkpoint['metadata']))==cfg
  model.load_state_dict(checkpoint['model_state_dict'],strict=True);del checkpoint;model=model.float().cpu().eval();before=digest(model)
  dc=resolve_model_data_config(model);mean,std=dc['mean'],dc['std'];fill=tuple(round(v*255) for v in mean)
  assert list(mean)==cfg['normalization']['mean'] and list(std)==cfg['normalization']['std'] and fill==(124,116,104)
  ns=dict(Dataset=Dataset,Image=Image,ImageOps=ImageOps,TF=TF,CONFIG=cfg['config'],mean=mean,std=std,fill=fill);exec(compile(ast.Module(body=[dn],type_ignores=[]),str(source),'exec'),ns);dataset=ns['DoorDataset']
  for sample in frozen['samples']:
   sid=sample['id'];path=Path(sample['image_path']);assert sha(path)==sample['imageSHA256'];x=dataset([dict(image_path=str(path),class_id=1)])[0][0].unsqueeze(0).cpu();baseline=scores(model,x)
   assert baseline['probability']==sample['sameLayerReference'][model_name]['score']
   for layer_index,layer in enumerate(frozen['layers']):
    resolution='7' if layer_index==0 else '14';signed,raw,a,g,stats=analyse(model,x,layer);assert raw['GradCAM'].shape==(int(resolution),int(resolution))
    refs=reference_equations(a,g,functions)
    row=dict(id=sid,model=model_name,layer=layer,resolution=resolution,baseline=baseline,predictedQuality='DEFECT' if baseline['probability']>=.5 else 'GOOD',diagnostics=stats,methods={})
    for method in METHODS:
     dest=out/sid/model_name/resolution/method;dest.mkdir(parents=True,exist_ok=False)
     np.save(dest/'signed.npy',signed[method]);np.save(dest/'raw.npy',raw[method])
     ref=np.maximum(refs[method],0);difference=float(np.max(np.abs(raw[method]-ref)))
     tolerance=frozen['equationReferenceTolerance'];close=bool(np.allclose(raw[method],ref,**tolerance));assert close,(model_name,sid,layer,method,difference)
     info=dict(status=map_status(raw[method]),rawMin=float(raw[method].min()),rawMax=float(raw[method].max()),equationReferenceMaxAbsDifference=difference,equationReferenceWithinTolerance=close)
     if method=='GradCAM' and resolution=='7':
      prior=sample['sameLayerReference'][model_name];assert sha(Path(prior['rawPath']))==prior['rawSHA256'];info['previousRawExactlyReproduced']=bool(np.array_equal(raw[method],np.load(prior['rawPath'],allow_pickle=False)));assert info['previousRawExactlyReproduced']
     if method=='GradCAM' and resolution=='14' and model_name=='new':
      prior=sample['new14Reference'];assert sha(Path(prior['path']))==prior['sha256'];info['previousRawExactlyReproduced']=bool(np.array_equal(raw[method],np.load(prior['path'],allow_pickle=False)));assert info['previousRawExactlyReproduced']
     if info['status']=='GENERATED':info.update(render_styles(dest,raw[method],sample['displaySize']))
     row['methods'][method]=info
    report['cases'].append(row);dump(out/'report.json',report);print('[CAM METHODS]',model_name,sid,resolution,{key:v['status'] for key,v in row['methods'].items()},stats['gradcamZeroReason'],flush=True)
  report['models'][model_name]=dict(modelStateUnchanged=digest(model)==before,checkpointUnchanged=sha(run/'best.pt')==frozen['modelHashes'][model_name]);assert all(report['models'][model_name].values());del model
 report['status']='completed_cpu_methods_and_style_diagnostic_not_deployed';report['elapsedSeconds']=time.monotonic()-started;dump(out/'report.json',report)
 build_view(out,frozen,report)
 with zipfile.ZipFile(out/'cam_methods_style.zip','w',zipfile.ZIP_DEFLATED) as archive:
  for p in out.rglob('*'):
   if p.is_file() and p.suffix!='.zip':archive.write(p,p.relative_to(out))
 print('[METHODS COMPLETE]',out,flush=True)

def build_view(out,frozen,report):
 payload=dict(cases=report['cases'],samples=[dict(id=r['id'],category=r['source_categories'],review=r['previousHumanReview']) for r in frozen['samples']])
 page='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CAM 기법과 JET 스타일 비교</title><style>body{font-family:"Malgun Gothic",sans-serif;max-width:1500px;margin:24px auto;padding:0 20px;background:#f2f5f9;color:#182535;line-height:1.7}header,section{background:white;border-radius:10px;padding:20px;margin-bottom:24px}.controls{position:sticky;top:0;background:#e3eaf3;padding:12px;display:flex;gap:14px;flex-wrap:wrap;z-index:3}select{font:inherit;padding:6px;max-width:100%}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}figure{margin:0;background:#eef2f8;border:1px solid #c6d1df;min-height:180px}img{display:block;width:100%}figcaption{padding:10px}.diagnosis{background:#fff2d4;padding:12px}.legend{height:18px;max-width:440px;background:linear-gradient(to right,#000080,#0000ff,#00ffff,#ffff00,#ff0000,#800000)}small{display:block}.oldstyle{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}h2{margin-top:0}</style></head><body><header><h1>Grad-CAM · HiResCAM · LayerCAM</h1><p>동일한 도어 사진 3장과 고정 가중치로 계산했습니다. 첨부 예시의 색상 표현을 참고한 JET 계열 스타일입니다. 색상·겹침 강도를 바꾸어도 같은 방법의 원시 맵과 강조 위치는 유지됩니다.</p><p>각 맵 내부의 상대 반응을 표시합니다. 빨간색은 불량 확률이나 결함 확정 경계가 아닙니다. 0맵·상수맵에는 임의의 색상 이미지를 만들지 않습니다. 새 기법은 비교 후보이며 운영에 반영하지 않았습니다.</p><div class="legend"></div><small>상대 반응 낮음 ← 파랑 · 초록 · 노랑 · 빨강 → 높음 (표현 예시)</small></header><div class="controls"><label>모델 <select id="model"><option value="new">재학습 2회차</option><option value="old">이전 20회차</option></select></label><label>레이어 <select id="layer"><option value="7">현재 7×7</option><option value="14">후보 14×14</option></select></label><label>색상 스타일 <select id="style"><option value="jet">JET 계열 · 50%</option><option value="jet_strong">JET 계열 · 강조 65%</option><option value="legacy">기존 빨강·파랑 · 40%</option></select></label></div><main id="cases"></main><section><h2>같은 원시 맵에서 스타일만 비교</h2><p>첫 번째 사진의 Grad-CAM 원시 맵은 동일합니다. 모델·레이어 선택을 바꾸면 아래 두 스타일도 같은 맵으로 함께 갱신됩니다.</p><div id="styles" class="oldstyle"></div></section><script>
const data=PAYLOAD;
const titles={GradCAM:'Grad-CAM',HiResCAM:'HiResCAM',LayerCAM:'LayerCAM'};
function escapeText(value){const p=document.createElement('p');p.textContent=value;return p.innerHTML}
function imageFigure(src,title){return '<figure><a target="_blank" href="'+src+'"><img src="'+src+'"></a><figcaption>'+escapeText(title)+'</figcaption></figure>'}
function missing(title,status){return '<figure><figcaption>'+escapeText(title)+'<br>'+escapeText(status)+' — 유효한 강조 영역 없음</figcaption></figure>'}
function reasonText(d){if(d.gradcamZeroReason==='nonzero_gradient_but_signed_gradcam_nonpositive_removed_by_relu')return '기울기는 존재하지만, 현재 Grad-CAM의 평균·합산 결과가 모두 0 이하라 음수 제거 후 0맵이 됐습니다.';if(d.gradcamZeroReason==='all_gradient_entries_zero')return '이 층에서 불량 logit에 대한 기울기가 모두 0입니다.';if(d.gradcamZeroReason==='nonzero_gradient_but_averaged_weighted_sum_zero')return '기울기는 존재하지만 평균·가중합 결과가 0입니다.';return '현재 Grad-CAM에서 양의 반응 값이 존재합니다. 색상 맵 생성이 실제 결함 위치 일치를 보장하지는 않습니다.'}
function draw(){const model=document.getElementById('model').value,resolution=document.getElementById('layer').value,style=document.getElementById('style').value;let result='';for(const sample of data.samples){const row=data.cases.find(r=>r.id===sample.id&&r.model===model&&r.resolution===resolution);let figures=imageFigure(sample.id+'/original.jpg','원본 표시');for(const method of ['GradCAM','HiResCAM','LayerCAM']){const item=row.methods[method];const title=titles[method]+' / '+resolution+'×'+resolution;if(item.files)figures+=imageFigure(sample.id+'/'+model+'/'+resolution+'/'+method+'/'+item.files[style],title);else figures+=missing(title,item.status)}result+='<section data-id="'+sample.id+'"><h2>'+sample.id+' / '+escapeText(sample.category)+'</h2><p>분류: '+row.predictedQuality+' / 보정 전 불량 점수 '+row.baseline.probability.toFixed(9)+'</p><div class="grid">'+figures+'</div><p class="diagnosis">'+reasonText(row.diagnostics)+'</p><p>앞선 사용자 메모: '+escapeText(sample.review.note||'별도 메모 없음')+'</p></section>'}document.getElementById('cases').innerHTML=result;const first=data.samples[0],row=data.cases.find(r=>r.id===first.id&&r.model===model&&r.resolution===resolution),item=row.methods.GradCAM;document.getElementById('styles').innerHTML=item.files?imageFigure(first.id+'/'+model+'/'+resolution+'/GradCAM/'+item.files.legacy,'기존 빨강·파랑 40%')+imageFigure(first.id+'/'+model+'/'+resolution+'/GradCAM/'+item.files.jet,'동일 맵 · JET 계열 50%'):missing('기존 스타일',item.status)+missing('JET 스타일',item.status)}
document.querySelectorAll('select').forEach(input=>input.addEventListener('change',draw));draw();
</script></body></html>'''
 page=page.replace('PAYLOAD',json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('<','\\u003c'))
 (out/'comparison.html').write_text(page)

if __name__=='__main__':main()
