"""Fixed new DOOR checkpoint verification; model-selection data only."""
import argparse,csv,hashlib,html,importlib.metadata,json,math
from datetime import datetime,timezone
from pathlib import Path
from door_experiment.preflight import audit_manifests

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];run=args.run.resolve()
    if not run.is_relative_to(root/'outputs/door_next_training'):raise ValueError('Local new training artifact required')
    cfg=json.loads((run/'run_config.json').read_text());best=json.loads((run/'best_metrics.json').read_text())
    if cfg['mode']!='train':raise ValueError('Full training run required')
    tables,audit=audit_manifests(root,cfg['manifests'].get('provenance',{}).get('config_path'));rows=tables['model_selection']
    for role in ('train','model_selection'):
        if cfg['manifests'][role]['sha256']!=audit[role]['sha256']:raise ValueError('Manifest lineage differs')
    with (run/'best_model_selection_predictions.csv').open(encoding='utf-8-sig') as f:saved=list(csv.DictReader(f))
    if len(saved)!=len(rows):raise ValueError('Prediction coverage differs')
    for r,s in zip(rows,saved):
        if r['image_path']!=s['image_path'] or r['class_id']!=int(s['class_id']):raise ValueError('Prediction alignment differs')
    import numpy as np,torch,timm
    from PIL import Image,ImageOps
    from torchvision.transforms import functional as TF
    from ai_api.diagnostics import cam
    from frame_model.cam_review import verify_metadata,state_hash
    for p,v in cfg['versions'].items():
        if importlib.metadata.version(p)!=v:raise ValueError('Version differs: '+p)
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    torch.manual_seed(42);torch.cuda.manual_seed_all(42);torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
    out=root/'outputs/door_next_review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    report=dict(status='running',run=str(run),checkpoint_sha256=sha(run/'best.pt'),epoch=best['epoch'],samples=[],final_test_read=False,training_performed=False,api_model_changed=False,tolerance={'abs':1e-6,'rel':1e-4})
    dump(out/'report.json',report);print('[DOOR REVIEW OUTPUT]',out,flush=True)
    checkpoint=torch.load(run/'best.pt',map_location='cpu',weights_only=False)
    verify_metadata(checkpoint['metadata'],cfg)
    if checkpoint['epoch']!=best['epoch'] or checkpoint['metrics']!=best:raise ValueError('Not recorded best epoch')
    model=timm.create_model(cfg['config']['model_name'],pretrained=False,num_classes=2)
    model.load_state_dict(checkpoint['model_state_dict'],strict=True);del checkpoint
    model=model.float().cuda().eval();before=state_hash(model)
    class Adapter:
        def tensor(self,path):
            with Image.open(path) as im:display=ImageOps.exif_transpose(im).convert('RGB')
            padded=ImageOps.pad(display,(224,224),method=Image.Resampling.BICUBIC,color=(124,116,104))
            return TF.normalize(TF.to_tensor(padded),[.485,.456,.406],[.229,.224,.225])
    engine=Adapter();engine.model=model;engine.torch=torch;engine.np=np
    reproduced=[]
    with torch.inference_mode():
        for start in range(0,len(rows),8):
            logits=model(torch.stack([engine.tensor(r['image_path']) for r in rows[start:start+8]]).cuda())
            if not torch.isfinite(logits).all():raise ValueError('Nonfinite logits')
            reproduced.extend(torch.softmax(logits,dim=1)[:,1].cpu().tolist())
    diffs=[abs(p-float(s['raw_defect_score'])) for p,s in zip(reproduced,saved)]
    mismatches=[i for i,(p,s) in enumerate(zip(reproduced,saved)) if not math.isclose(p,float(s['raw_defect_score']),abs_tol=1e-6,rel_tol=1e-4)]
    report['batch8_comparison']=dict(n=len(rows),max_abs=max(diffs),median_abs=float(np.median(diffs)),p95_abs=float(np.quantile(diffs,.95)),outside_tolerance=len(mismatches),class_changes=sum(int(p>=.5)!=int(s['predicted_class']) for p,s in zip(reproduced,saved)),nearest_boundary=min(abs(p-.5) for p in reproduced))
    errors=[i for i,s in enumerate(saved) if s['correct']=='0'];errors.sort(key=lambda i:(0 if saved[i]['class_id']=='1' else 1,rows[i]['image_path']))
    correct=[]
    for label in (0,1):correct.extend([i for i,s in enumerate(saved) if s['correct']=='1' and int(s['class_id'])==label][:2])
    for index in errors+correct:
        row,s=rows[index],saved[index];ident=f'sample_{index:04d}';dest=out/ident;dest.mkdir()
        with Image.open(row['image_path']) as im:display=ImageOps.exif_transpose(im).convert('RGB')
        display.save(dest/'display.jpg',quality=95)
        ImageOps.pad(display,(224,224),method=Image.Resampling.BICUBIC,color=(124,116,104)).save(dest/'input224.png')
        with torch.inference_mode():score=float(torch.softmax(model(engine.tensor(row['image_path']).unsqueeze(0).cuda()),dim=1)[0,1])
        if not math.isfinite(score) or not 0<=score<=1:raise ValueError('Invalid single score')
        kind=('FN' if row['class_id']==1 else 'FP') if index in errors else ('TP' if row['class_id']==1 else 'TN')
        item=dict(id=ident,index=index,kind=kind,group_id=row['group_id'],image_path=row['image_path'],image_sha256=sha(row['image_path']),display_size=list(display.size),saved_score=float(s['raw_defect_score']),batch8_score=reproduced[index],single_score=score,single_class_changed=int(score>=.5)!=int(s['predicted_class']),single_outside_tolerance=not math.isclose(score,float(s['raw_defect_score']),abs_tol=1e-6,rel_tol=1e-4),service_cam='DEFECT_CAM_ELIGIBLE' if score>=.5 else 'NOT_GENERATED_GOOD',layers=[])
        for layer in ('layers.3.blocks.1.norm1','layers.2.blocks.5.norm1'):
            folder=dest/layer;folder.mkdir()
            try:
                info,_,_=cam(engine,Path(row['image_path']),layer,folder,target='defect')
                info['diagnostic_only']=score<.5
                if info['status']=='GENERATED':
                    with Image.open(folder/'overlay.png') as overlay:
                        if overlay.size!=display.size:raise ValueError('Overlay size differs')
                item['layers'].append(info)
            except Exception as exc:item['layers'].append(dict(layer=layer,status='FAILED',error_type=type(exc).__name__))
        report['samples'].append(item);dump(out/'report.json',report)
        print('[DOOR REVIEW SAMPLE]',ident,kind,flush=True)
    report['state_unchanged']=before==state_hash(model)
    if not report['state_unchanged'] or model.training:raise RuntimeError('Model state changed')
    report['status']='completed_with_score_warnings' if mismatches or any(s['single_outside_tolerance'] or s['single_class_changed'] for s in report['samples']) else 'completed'
    report['cam_failures']=sum(l['status']=='FAILED' for s in report['samples'] for l in s['layers'])
    if report['cam_failures']:report['status']+='__cam_failures_open'
    dump(out/'report.json',report)
    parts=['<!doctype html><meta charset="utf-8"><title>DOOR 오판·CAM 검토</title><h1>DOOR 오판·CAM 검토</h1><p>FN 우선. GOOD의 CAM은 진단 전용이며 서비스 제공 대상이 아닙니다. 원본과 224 입력의 손상 가시성, 배경 반응, 설명 유용성을 기록하세요. CAM은 결함 마스크가 아닙니다.</p><label>검토자 <input id="reviewer"></label><button onclick="save()">검토 JSON 내보내기</button>']
    for s in report['samples']:
        ident=s['id'];parts.append(f'<section data-id="{ident}"><h2>{ident} {s["kind"]}</h2><pre>'+html.escape(json.dumps(s,ensure_ascii=False,indent=2))+'</pre>')
        parts.append(f'<a href="{html.escape(Path(s["image_path"]).as_uri(),quote=True)}">원본 파일</a><br><img width="480" src="{ident}/display.jpg"><img src="{ident}/input224.png">')
        for l in s['layers']:
            parts.append('<h3>'+html.escape(l['layer'])+' '+l['status']+'</h3>')
            if l['status']=='GENERATED':parts.append(f'<img width="480" src="{ident}/{l["layer"]}/overlay.png">')
        parts.append('<p>원본·224 결함 가시성 / 배경 반응 / 레이어별 설명 유용성 / 라벨 의심과 근거:</p><textarea rows="5" cols="100"></textarea></section><hr>')
    parts.append('''<script>
const key=location.href;
function collect(){return {reviewer:document.getElementById('reviewer').value,report:location.href,items:[...document.querySelectorAll('section')].map(s=>({id:s.dataset.id,notes:s.querySelector('textarea').value}))}}
function save(){const data=collect();if(!data.reviewer.trim()||data.items.some(x=>!x.notes.trim())){alert('검토자와 모든 사례의 메모를 입력하세요.');return}const u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='door_next_review.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
try{const old=JSON.parse(localStorage.getItem(key)||'null');if(old){document.getElementById('reviewer').value=old.reviewer||'';document.querySelectorAll('section').forEach(s=>{s.querySelector('textarea').value=(old.items.find(x=>x.id===s.dataset.id)||{}).notes||''})}document.addEventListener('input',()=>localStorage.setItem(key,JSON.stringify(collect())))}catch(e){}
</script>''')
    (out/'index.html').write_text('\n'.join(parts))
    print('[DOOR REVIEW REPORT]',out/'report.json');print('[DOOR REVIEW HTML]',out/'index.html');print('[DOOR REVIEW RESULT]',report['status'])
if __name__=='__main__':main()
