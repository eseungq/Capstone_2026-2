"""Use a separate CPU model in the exact training container; do not touch live service state."""
import argparse, ast, hashlib, html, importlib.metadata, json, math, os, time, zipfile
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import torch, timm
from PIL import Image, ImageOps
from torch.utils.data import Dataset
from torchvision.transforms import functional as TF
from timm.data import resolve_model_data_config
from ai_api.e02_engine import validate_candidate, ROOT
from ai_api.e02_integration.diagnose_cam_cpu import cam, scores, digest

def dump(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--selection',type=Path,required=True);args=parser.parse_args()
    selection=json.loads(args.selection.read_text());out=args.selection.parent
    Image.MAX_IMAGE_PIXELS=120000000
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == ''
    assert not torch.cuda.is_available(), 'CPU required'
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    versions={name:importlib.metadata.version(name) for name in selection['expectedVersions']}
    assert versions == selection['expectedVersions'], (versions,selection['expectedVersions'])
    manifest,run,cfg=validate_candidate()
    assert selection['checkpointSHA256']==manifest['checkpointSHA256']
    torch.manual_seed(42);np.random.seed(42)
    model=timm.create_model(cfg['config']['model_name'],pretrained=False,num_classes=2)
    checkpoint=torch.load(run/'best.pt',map_location='cpu',weights_only=False)
    # Match the production engine's exact JSON-normalized metadata check.
    assert checkpoint['epoch']==2 and json.loads(json.dumps(checkpoint['metadata']))==cfg
    model.load_state_dict(checkpoint['model_state_dict'],strict=True);del checkpoint
    model=model.float().cpu().eval();before=digest(model)
    dc=resolve_model_data_config(model);mean,std=dc['mean'],dc['std'];fill=tuple(round(v*255) for v in mean)
    assert fill==(124,116,104)
    source=ROOT/manifest['trainingSource'];tree=ast.parse(source.read_text());mainnode=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');node=next(n for n in mainnode.body if isinstance(n,ast.ClassDef) and n.name=='DoorDataset')
    ns=dict(Dataset=Dataset,Image=Image,ImageOps=ImageOps,TF=TF,CONFIG=cfg['config'],mean=mean,std=std,fill=fill)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
    dataset=ns['DoorDataset']
    report=dict(status='running',startedUTC=datetime.now(timezone.utc).isoformat(),device='cpu',threads=2,versions=versions,selectionSHA256=sha(args.selection),checkpointSHA256=manifest['checkpointSHA256'],modelVersion=manifest['modelVersion'],newTrainingPerformed=False,operatingLayerChanged=False,finalTestImagesRead=False,calibrationOrPolicyImagesRead=False,samples=[])
    dump(out/'report.json',report)
    started=time.monotonic()
    for sample in selection['samples']:
        folder=out/sample['id'];assert sha(Path(sample['image_path']))==sample['imageSHA256']
        x=dataset([dict(image_path=sample['image_path'],class_id=int(sample['class_id']))])[0][0].unsqueeze(0).cpu()
        baseline=scores(model,x);expected=float(sample['raw_defect_score']);predicted=int(baseline['probability']>=.5)
        row=dict(id=sample['id'],savedKind=sample['savedKind'],sourceCategory=sample['source_categories'],imageSHA256=sample['imageSHA256'],baselineCPU=baseline,referenceGPUBatchScore=expected,withinOriginalScoreTolerance=math.isclose(baseline['probability'],expected,abs_tol=1e-6,rel_tol=1e-4),predictionUnchanged=predicted==int(sample['predicted_class']),layers=[])
        report['samples'].append(row)
        with Image.open(sample['image_path']) as src:image=ImageOps.exif_transpose(src).convert('RGB')
        contained=ImageOps.contain(image,(224,224),method=Image.Resampling.BICUBIC);w,h=contained.size;left,top=round((224-w)*.5),round((224-h)*.5)
        display=image.copy();display.thumbnail((1400,1000));pixels=np.asarray(display,dtype=np.float32)
        for index,layer in enumerate(selection['layers']):
            info,raw,full=cam(model,x,layer,'defect')
            prefix='current' if index==0 else 'candidate'
            np.save(folder/(prefix+'_raw.npy'),raw)
            info['rawFile']=prefix+'_raw.npy'
            if full is not None:
                values=np.asarray(Image.fromarray(full[top:top+h,left:left+w]).resize(display.size,Image.Resampling.BILINEAR))
                colors=np.stack((values,np.zeros_like(values),1-values),axis=-1)*255
                overlay=Image.fromarray(np.clip(pixels*.6+colors*.4,0,255).astype('uint8'))
                overlay.save(folder/(prefix+'.jpg'),quality=92)
                info['overlay']=prefix+'.jpg'
            row['layers'].append(info)
            dump(out/'report.json',report)
        print('[FOLLOWUP CPU]',sample['id'],sample['savedKind'],'score_match',row['withinOriginalScoreTolerance'],'prediction_same',row['predictionUnchanged'],flush=True)
    report['modelStateUnchanged']=digest(model)==before
    report['checkpointUnchanged']=sha(run/'best.pt')==manifest['checkpointSHA256']
    assert report['modelStateUnchanged'] and report['checkpointUnchanged']
    report['elapsedSeconds']=time.monotonic()-started
    report['scoreWarnings']=[r['id'] for r in report['samples'] if not r['withinOriginalScoreTolerance']]
    report['predictionChanges']=[r['id'] for r in report['samples'] if not r['predictionUnchanged']]
    report['status']='completed_cpu_diagnostic_human_review_pending'
    dump(out/'report.json',report)
    build_view(out,selection,report)
    with zipfile.ZipFile(out/'CAM_followup_review.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in out.rglob('*'):
            if path.is_file() and path.suffix not in ('.zip','.npy'):
                archive.write(path,path.relative_to(out))
    print('[FOLLOWUP COMPLETE]',str(out),flush=True)

def build_view(out,selection,report):
    sections=[]
    for sample,row in zip(selection['samples'],report['samples']):
        sid=sample['id']
        sections.append(f'<section data-id="{sid}"><h2>{sid} / '+('불량' if sample['savedKind']=='TP' else '정상 대조')+f' / {html.escape(sample["source_categories"])}</h2><p>원천 라벨은 확정 재검토 전입니다. 정상 사진의 검사항목 명칭은 실제 결함이 있다는 뜻이 아닙니다.</p>')
        if sample['savedKind']=='TN':sections.append('<p class="warn">정상 예측의 CAM은 이번 원인 분석용입니다. 앱에서는 GOOD의 CAM을 제공하지 않습니다.</p>')
        if not row['withinOriginalScoreTolerance']:sections.append('<p class="warn">CPU 점수와 저장된 GPU 배치 점수의 차이가 기존 허용오차 밖입니다. 허용오차를 변경하지 않았으며 위치 설명 비교용으로만 보세요.</p>')
        if not row['predictionUnchanged']:sections.append('<p class="warn">CPU에서 분류 결과도 달라졌습니다. 운영 GPU 재확인이 필요한 사례입니다.</p>')
        sections.append('<div class="grid">')
        for filename,title in [('original.jpg','원본 표시'),('input224.png','모델 입력 224×224'),('current.jpg','현재 레이어 7×7'),('candidate.jpg','후보 레이어 14×14')]:
            if (out/sid/filename).exists():sections.append(f'<figure><a href="{sid}/{filename}" target="_blank"><img loading="lazy" src="{sid}/{filename}"></a><figcaption>{title}</figcaption></figure>')
            else:sections.append(f'<figure><p>{title}: 유효한 활성화 맵 없음</p></figure>')
        sections.append('</div><div class="form"><label>결함 가시성 <select data-field="visibility"><option value="">선택</option><option>224에서도 확인 가능</option><option>원본에서만 확인 가능</option><option>결함 여부 애매</option><option>정상 대조</option></select></label>')
        options=['O','X','판단 어려움'] if sample['savedKind']=='TP' else ['정상 부위 강조 적음','정상 부위 강조 많음','판단 어려움']
        for field,title in [('current','현재 레이어'),('candidate','후보 레이어')]:
            title += ' 참고 유용성' if sample['savedKind']=='TP' else ' 정상 부위 반응'
            sections.append('<label>'+title+' <select data-field="'+field+'"><option value="">선택</option>'+''.join('<option>'+value+'</option>' for value in options)+'</select></label>')
        sections.append('<label>메모 <textarea data-field="note" placeholder="흠집 강조 여부, 배경·반사·경계 반응 등을 기록"></textarea></label></div></section>')
    html_text='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>추가 18장 Grad-CAM 비교</title><style>body{font-family:"Malgun Gothic",sans-serif;background:#f4f7fa;color:#182535;max-width:1520px;margin:24px auto;padding:0 20px;line-height:1.65}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:12px}figure{margin:0;background:#eef2f6;border:1px solid #cbd4df}img{width:100%;display:block}figcaption{padding:9px}section{background:white;padding:20px;margin:24px 0;border-radius:10px}.form{display:flex;flex-wrap:wrap;gap:16px;margin-top:18px}label{display:flex;flex-direction:column;gap:6px}select,textarea,button{font:inherit;padding:8px}textarea{min-width:260px}.warn{background:#fff1d2;padding:12px}header{background:white;padding:20px;border-radius:10px}.bar{position:sticky;top:0;padding:10px;background:#e1eaf4;z-index:1}button{cursor:pointer}#status{margin-left:12px}</style></head><body><header><h1>추가 18장 Grad-CAM 비교</h1><p>스크래치·외관 손상 정분류 불량 12장 + 정상 대조 6장. 기존 49건과 연결 시험 사진을 제외해 미리 선정했습니다. 후보 CAM 결과를 보기 전에 선정 규칙을 고정했습니다.</p><p>같은 e02 가중치와 전처리를 사용한 CPU 진단입니다. 운영 서버의 레이어 교체나 성능 개선 입증이 아닙니다. 사진 비율은 실제 촬영 거리·구도를 의미하지 않습니다. 정확한 결함 경계가 아니라 작업자에게 참고가 되는지를 확인해 주세요.</p><p>기록은 이 브라우저에 임시 저장됩니다. 완료 후 확인 기록을 내려받아야 전달할 수 있습니다. 같은 사진·같은 부품으로 보이는 사례가 있으면 메모해 주세요.</p></header><div class="bar"><button id="download">확인 기록 내려받기</button><span id="status"></span></div>'''+''.join(sections)+'''<script>
const meta=META_JSON;
const key='cam-followup-'+meta.selectionSHA256;
let state={};try{state=JSON.parse(localStorage.getItem(key)||'{}')}catch(error){}
function save(){try{localStorage.setItem(key,JSON.stringify(state))}catch(error){}update()}
function update(){const n=meta.ids.filter(id=>state[id]&&state[id].visibility&&state[id].current&&state[id].candidate).length;document.getElementById('status').textContent=n+' / '+meta.ids.length+'건 필수 항목 기록'}
document.querySelectorAll('section[data-id]').forEach(section=>{const id=section.dataset.id;section.querySelectorAll('[data-field]').forEach(input=>{const field=input.dataset.field;input.value=(state[id]||{})[field]||'';input.addEventListener('input',()=>{state[id]=state[id]||{};state[id][field]=input.value;save()})})});
document.getElementById('download').addEventListener('click',()=>{const result={schema:'cam-followup-human-review-v1',selectionSHA256:meta.selectionSHA256,modelVersion:meta.modelVersion,createdAt:new Date().toISOString(),cases:meta.ids.map(id=>({id,...(state[id]||{})}))};const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='CAM_followup_review_'+new Date().toISOString().slice(0,10)+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});update();
</script></body></html>'''
    meta=dict(selectionSHA256=report['selectionSHA256'],modelVersion=selection['modelVersion'],ids=[r['id'] for r in report['samples']])
    html_text=html_text.replace('META_JSON',json.dumps(meta,ensure_ascii=False).replace('<','\\u003c'))
    guide='<p><strong>기록 기준:</strong> 불량 사진의 O는 실제 결함 확인에 도움이 되는 강조, X는 결함 대신 배경·반사·경계 등이 주로 강조되는 경우입니다. 정상 대조 사진은 O/X 대신 정상 부위의 불필요한 강조 정도를 기록합니다. 두 종류의 기록을 한 비율로 합산하지 않습니다.</p>'
    html_text=html_text.replace('</header>',guide+'</header>')
    html_text=html_text.replace('link.href=url;link.download=', 'document.body.appendChild(link);link.href=url;link.download=')
    html_text=html_text.replace('setTimeout(()=>URL.revokeObjectURL(url),1000)', 'setTimeout(()=>{URL.revokeObjectURL(url);link.remove()},60000)')
    (out/'review.html').write_text(html_text)

if __name__=='__main__':main()
