"""Internal validation only. Never trains, edits labels, or evaluates final test data."""
import argparse
import ast
import csv
import hashlib
import html
import importlib.metadata
import inspect
import json
import random
import sys
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/path/to/private/validated-project')
RUN = ROOT / 'outputs/training/door_swin_tiny_20261008_183758_369671'
MANIFEST = ROOT / 'outputs/manifests/door_internal_validation.csv'
TRAINING = Path('/path/to/private-user/다운로드/도어_SwinTiny_DGX_학습_20261009/train_door_swin.py')
REVIEW = ROOT / 'outputs/reviews/door_swin_tiny_20261008_183758_369671_internal_errors'
NAMES = {0: '양품', 1: '불량품'}
SOURCES = ['https://github.com/huggingface/pytorch-image-models/blob/v1.0.30/timm/models/swin_transformer.py', 'https://github.com/microsoft/Swin-Transformer/blob/main/models/swin_transformer.py']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def measure(rows):
    c = Counter(r['kind'] for r in rows)
    tp, tn, fp, fn = (c[k] for k in ('TP', 'TN', 'FP', 'FN'))
    ratio = lambda a, b: a / b if b else None
    return dict(accuracy=ratio(tp+tn, len(rows)), precision=ratio(tp, tp+fp),
                recall=ratio(tp, tp+fn), f1=ratio(2*tp, 2*tp+fp+fn),
                missed_defect_rate=ratio(fn, tp+fn), false_positive_rate=ratio(fp, tn+fp),
                tp=tp, tn=tn, fp=fp, fn=fn)


def audit(out, config):
    from PIL import Image, ImageOps
    rows = read_csv(MANIFEST)
    old = read_csv(RUN / 'best_internal_validation_predictions.csv')
    issues, old_map, seen = [], {}, {}
    for r in old:
        key = str(Path(r['image_path']).resolve())
        if key in old_map:
            issues.append(dict(image_path=key, problem='duplicate saved prediction'))
        old_map[key] = r
    for i, r in enumerate(rows):
        p = str(Path(r['image_path']).resolve())
        r['image_path'] = p
        try:
            y = int(r['class_id'])
            if NAMES.get(y) != r['quality']:
                raise ValueError('manifest quality/class_id conflict')
            if p in seen:
                raise ValueError('duplicate image path; labels: '+str([seen[p], y]))
            seen[p] = y
            r['class_id'] = y
            if p not in old_map or int(old_map[p]['class_id']) != y:
                raise ValueError('saved prediction missing or label conflict')
            label = json.loads(Path(r['json_path']).read_text(encoding='utf-8-sig'))
            qualities = sorted({a.get('attributes', {}).get('quality') for a in label['annotations']}, key=str)
            if qualities != [r['quality']]:
                raise ValueError('source annotation/manifest label conflict: '+str(qualities))
            parts = {a.get('attributes', {}).get('part') for a in label['annotations']}
            if parts != {'도어'}:
                raise ValueError('source annotation part conflict: '+str(parts))
            with Image.open(p) as image:
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.load()
        except Exception as e:
            issues.append(dict(index=i, image_path=p, problem=str(e)))
        if (i+1) % 200 == 0:
            print('Audit', i+1, '/', len(rows), flush=True)
    counts = Counter(r['class_id'] for r in rows)
    if len(rows) != 2039 or counts != {0: 909, 1: 1130}:
        issues.append(dict(problem='unexpected manifest row/class counts', counts=dict(counts)))
    if set(old_map) != set(seen):
        issues.append(dict(problem='saved/manifest image path sets differ'))
    if sha(MANIFEST) != config['manifests']['internal_validation']['sha256']:
        issues.append(dict(problem='manifest hash differs from training'))
    report = dict(rows=len(rows), class_counts=dict(counts), issues=issues,
                  decoded_images=len(rows)-sum('index' in x for x in issues),
                  Pillow=importlib.metadata.version('Pillow'),
                  folder_category_is_not_quality=True)
    dump(out / 'data_audit.json', report)
    if issues:
        raise RuntimeError('Data audit failed; see data_audit.json. No images skipped.')
    return rows, old_map


def report(out, rows, metrics, status):
    data = json.dumps(rows, ensure_ascii=False).replace('<', '\\u003c')
    document = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>도어 내부 검증</title><style>body{font:16px system-ui;max-width:1200px;margin:30px auto;padding:15px;background:#f2f4f7}article{background:white;padding:18px;margin:16px 0;border-radius:8px;overflow-wrap:anywhere}.photos{display:flex;gap:20px;align-items:start}img{max-width:100%}.original{width:600px}.input{width:224px;height:224px}pre{white-space:pre-wrap}select{padding:8px}table{border-collapse:collapse}td,th{padding:10px;border:1px solid #888}</style><h1>도어 내부 검증</h1><p><b>모델 선택에 이미 사용한 내부 검증 결과이며, 최종 시험 성능이 아닙니다.</b></p><p>불량 점수는 보정 전 softmax 불량 클래스 점수입니다. 분류 기준 0.5.</p>'''
    document += '<p>'+html.escape(status)+'</p><pre>'+html.escape(json.dumps(metrics, ensure_ascii=False, indent=2))+'</pre>'
    if metrics:
        document += f'<table><tr><th>정답 / 예측</th><th>양품</th><th>불량품</th></tr><tr><th>양품</th><td>TN {metrics["tn"]}</td><td>FP {metrics["fp"]}</td></tr><tr><th>불량품</th><td>FN {metrics["fn"]}</td><td>TP {metrics["tp"]}</td></tr></table>'
    document += '''<p><a href="metrics.json">지표</a> · <a href="comparison.json">비교</a> · <a href="evaluation_config.json">설정</a> · <a href="data_audit.json">데이터 검사</a> · <a href="gradcam/index.html">Grad-CAM</a></p><label>정답 <select id="truth"><option value="">전체</option><option value="0">양품</option><option value="1">불량품</option></select></label> <label>예측 <select id="pred"><option value="">전체</option><option value="0">양품</option><option value="1">불량품</option></select></label> <label>유형 <select id="kind"><option value="">전체</option><option>TP</option><option>TN</option><option>FP</option><option>FN</option></select></label><p id="count"></p><main id="list"></main><script>const rows='''+data+''';const names=['양품','불량품'];let shown=0;function add(){let selected=rows.filter(r=>(truth.value===''||r.class_id===+truth.value)&&(pred.value===''||r.predicted_class===+pred.value)&&(!kind.value||r.kind===kind.value));count.textContent=selected.length+'장';for(const r of selected.slice(shown,shown+40)){let a=document.createElement('article');let h=document.createElement('h3');h.textContent=r.kind+' · 정답 '+names[r.class_id]+' → 예측 '+names[r.predicted_class];a.append(h);let p=document.createElement('p');p.textContent='보정 전 불량 점수: '+r.raw_defect_score+' / '+r.image_path;a.append(p);if(r.original){let d=document.createElement('div');d.className='photos';for(const [src,title,cls] of [[r.original,'EXIF 보정 RGB 원본','original'],[r.input,'정규화 직전 224×224','input']]){let f=document.createElement('figure'),c=document.createElement('figcaption'),l=document.createElement('a'),im=document.createElement('img');c.textContent=title;im.loading='lazy';im.src=cls==='original'?(r.preview||src):src;im.className=cls;l.href=src;l.target='_blank';l.append(im);f.append(c,l);d.append(f);}a.append(d)}list.append(a)}shown+=40}function reset(){shown=0;list.replaceChildren();add()}for(const s of [truth,pred,kind])s.onchange=reset;window.onscroll=()=>{if(innerHeight+scrollY>document.body.offsetHeight-1000)add()};reset();</script></html>'''
    (out / 'index.html').write_text(document, encoding='utf-8')


def gradcam(model, dataset, predictions, out, torch, np, Image, ImageOps):
    dest = out / 'gradcam'
    dest.mkdir()
    import timm.models.swin_transformer as swin
    source = inspect.getsourcefile(swin)
    (dest / 'installed_swin_transformer.py').write_text(Path(source).read_text(), encoding='utf-8')
    layer_name = 'layers.3.blocks.1.norm1'
    layer = model.get_submodule(layer_name)
    randomizer = random.Random(42)
    selected = []
    for kind in ('TP', 'TN', 'FP', 'FN'):
        pool = sorted((i for i, r in enumerate(predictions) if r['kind'] == kind), key=lambda i: predictions[i]['image_path'])
        selected.extend(randomizer.sample(pool, min(2, len(pool))))
    records, cards = [], []
    before = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    cache = {}
    def hook(module, args, output):
        cache['activation'] = output
    handle = layer.register_forward_hook(hook)
    try:
        for i in selected:
            r = predictions[i]
            print(f'[Grad-CAM] {r["kind"]} index={i} / {r["image_path"]}', flush=True)
            with Image.open(r['image_path']) as src:
                original = ImageOps.exif_transpose(src).convert('RGB')
            # Exact Pillow contain dimensions and ImageOps.pad centering rounding.
            contained = ImageOps.contain(original, (224, 224), method=Image.Resampling.BICUBIC)
            w, h = contained.size
            left, top = round((224-w)*0.5), round((224-h)*0.5)
            pictures = []
            for cls in (0, 1):
                with torch.enable_grad():
                    x = dataset[i][0].unsqueeze(0).to('cuda').requires_grad_(True)
                    logits = model(x)
                    activation = cache['activation']
                    gradient, = torch.autograd.grad(logits[0, cls], activation)
                    if tuple(activation.shape) != (1, 7, 7, 768) or gradient.shape != activation.shape:
                        raise RuntimeError('Unexpected installed Swin feature shape: '+str(activation.shape))
                    if not torch.isfinite(activation).all() or not torch.isfinite(gradient).all():
                        raise RuntimeError('Nonfinite activation/gradient')
                    a, g = activation.permute(0, 3, 1, 2), gradient.permute(0, 3, 1, 2)
                    cam = torch.relu((g.mean((2, 3), keepdim=True)*a).sum(1))[0].detach().cpu().numpy()
                if not np.isfinite(cam).all():
                    raise RuntimeError('Nonfinite Grad-CAM map')
                lo, hi = float(cam.min()), float(cam.max())
                constant = hi-lo <= max(1e-12, abs(hi)*1e-6)
                filename = f'{i:04d}_class{cls}.png'
                np.save(dest / f'{i:04d}_class{cls}_raw.npy', cam)
                if not constant:
                    norm = (cam-lo)/(hi-lo)
                    full = np.asarray(Image.fromarray(norm.astype('float32')).resize((224,224), Image.Resampling.BILINEAR))
                    cropped = Image.fromarray(full[top:top+h, left:left+w]).resize(original.size, Image.Resampling.BILINEAR)
                    values = np.clip(np.asarray(cropped), 0, 1)
                    # Fixed blue-to-red color scale; per-map min/max recorded below.
                    heat = np.stack((values, np.zeros_like(values), 1-values), axis=-1)*255
                    overlay = (np.asarray(original)*0.6 + heat*0.4).clip(0,255).astype('uint8')
                    Image.fromarray(overlay).save(dest / filename)
                    pictures.append(f'<figure><figcaption>{NAMES[cls]} logit</figcaption><a href="{filename}"><img width="500" src="{filename}"></a></figure>')
                else:
                    pictures.append(f'<p>{NAMES[cls]} logit: 0 또는 일정한 맵, 색상 오버레이 생성하지 않음.</p>')
                records.append(dict(image_path=r['image_path'], kind=r['kind'], target_class=cls,
                    layer=layer_name, activation_shape=list(activation.shape), gradient_shape=list(gradient.shape),
                    activation_finite=True, gradient_finite=True, gradient_abs_max=float(gradient.abs().max()),
                    raw_min=lo, raw_max=hi, constant=constant, overlay=None if constant else filename,
                    padding_crop=[left,top,left+w,top+h], original_size=list(original.size)))
            cards.append('<article><h2>'+html.escape(r['kind']+' '+r['image_path'])+'</h2>'+''.join(pictures)+'</article>')
    finally:
        handle.remove()
    unchanged = all(torch.equal(before[k], v.detach().cpu()) for k,v in model.state_dict().items())
    if not unchanged:
        raise RuntimeError('Model state changed during Grad-CAM')
    dump(dest / 'metadata.json', dict(status='complete', seed=42, sources=SOURCES,
        installed_source_sha256=sha(source), layer=layer_name,
        rationale='Last Swin block pre-attention norm1, spatial NHWC 7x7x768; permute to NCHW. Runtime asserted.',
        normalization='ReLU(weighted activations), per-map (cam-min)/(max-min); zero/constant maps omitted',
        weights='spatial mean of target logit gradients; no optimizer or parameter backward',
        overlay='bilinear upsample to 224, remove exact Pillow padding, resize to EXIF RGB coordinates; blue=0 red=1; alpha=0.4',
        state_unchanged=unchanged, samples=records))
    (dest / 'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>Grad-CAM</h1><p>모델 판단 참고 영역이며 결함 위치 검출 결과가 아님. 양품·불량 logit 맵은 각각 정규화되므로 색상 강도를 서로 직접 비교할 수 없습니다.</p><a href="metadata.json">구현 및 실제 shape 기록</a>'+''.join(cards), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-only', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = args.output or ROOT / 'outputs/evaluation' / datetime.now().strftime('door_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=False)
    print('OUTPUT:', out, flush=True)
    status = dict(evaluation_complete=False, expected_images=2039, processed_images=0, gradcam='not_started')
    dump(out / 'status.json', status)
    def stage(name, message):
        status['stage'] = name
        status['updated_at'] = datetime.now().isoformat()
        dump(out / 'status.json', status)
        print(message, flush=True)
    stage('initializing', '[시작] 내부 검증 실행 초기화 / 기존 CSV 참고값 및 해시 확인')
    config = json.loads((RUN / 'run_config.json').read_text())
    saved_rows = read_csv(RUN / 'best_internal_validation_predictions.csv')
    for r in saved_rows:
        y, p = int(r['class_id']), int(r['predicted_class'])
        r['kind'] = ('TP' if p else 'FN') if y else ('FP' if p else 'TN')
    saved_metrics = measure(saved_rows)
    baseline = json.loads((RUN / 'best_metrics.json').read_text())
    dump(out / 'saved_reference_metrics.json', dict(source='Existing saved predictions only; NOT new model inference',
        rows=len(saved_rows), metrics=saved_metrics,
        differences_from_saved_metrics={k: saved_metrics[k]-baseline[k] for k in saved_metrics if k in baseline}))
    evaluation_config = dict(model_name=config['config']['model_name'], model_sha256=sha(RUN/'best.pt'),
        manifest_sha256=sha(MANIFEST), training_source_sha256=sha(TRAINING),
        saved_predictions_sha256=sha(RUN/'best_internal_validation_predictions.csv'),
        observations_sha256=sha(REVIEW/'observations.csv'), observations_path=str(REVIEW/'observations.csv'),
        pretrained=False, strict=True, classes={'양품':0,'불량품':1}, precision='FP32', batch_size=8,
        shuffle=False, cutoff=0.5, score='softmax(logits)[:,1], uncalibrated',
        preprocessing='ImageOps.exif_transpose -> RGB -> unchanged training DoorDataset: ImageOps.pad BICUBIC 224x224 fill RGB(124,116,104) -> tensor -> ImageNet normalize',
        normalization=config['normalization'], recorded_versions=config['versions'], scope='internal validation used for model selection; not final test performance', gradcam_sources=SOURCES)
    dump(out / 'evaluation_config.json', evaluation_config)
    try:
        stage('data_audit', '[검사 시작] 내부 검증 2,039장 이미지·라벨 검사')
        rows, old_map = audit(out, config)
        stage('data_audit_complete', '[검사 완료] 2,039장 전체 확인 / 신규 GPU 추론은 아직 시작 전')
        if args.audit_only:
            status.update(blocker='Docker socket permission denied; sudo no-new-privileges; GPU evaluation not run', data_audit='complete')
            dump(out / 'metrics.json', dict(evaluation_complete=False, processed_images=0, metrics=None))
            dump(out / 'comparison.json', dict(status='not_run', reason='No new inference; existing metrics are not remeasurements'))
            report(out, [], None, '데이터 사전 검사 완료. Docker 실행 권한 제한으로 재평가 및 Grad-CAM 미실행. 신규 측정 지표 없음.')
            return
        stage('environment', '[환경 시작] 평가 라이브러리·CUDA 확인')
        import numpy as np
        import torch
        import timm
        from PIL import Image, ImageOps
        from torch.utils.data import DataLoader, Dataset
        from torchvision.transforms import functional as TF
        from timm.data import resolve_model_data_config
        versions = {p:importlib.metadata.version(p) for p in config['versions']}
        evaluation_config.update(environment_versions=versions,
            version_differences={p:dict(recorded=config['versions'][p],actual=v) for p,v in versions.items() if config['versions'][p]!=v},
            cuda_build=torch.version.cuda, cudnn_version=torch.backends.cudnn.version())
        dump(out/'evaluation_config.json', evaluation_config)
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; use existing NVIDIA GPU Docker environment')
        print('[환경 버전] '+json.dumps(versions, ensure_ascii=False), flush=True)
        print('[GPU] '+torch.cuda.get_device_name(0), flush=True)
        stage('checkpoint_loading', '[모델 시작] best.pt 로딩 / pretrained=False, strict=True')
        random.seed(42); np.random.seed(42); torch.manual_seed(42); torch.cuda.manual_seed_all(42)
        torch.backends.cudnn.benchmark=False
        torch.backends.cudnn.deterministic=True
        evaluation_config['gpu']=torch.cuda.get_device_name(0)
        checkpoint=torch.load(RUN/'best.pt',map_location='cpu',weights_only=False)
        evaluation_config.update(checkpoint_keys=list(checkpoint), checkpoint_epoch=checkpoint['epoch'])
        if json.loads(json.dumps(checkpoint['metadata'])) != config:
            raise RuntimeError('Checkpoint metadata differs from run configuration')
        model=timm.create_model(config['config']['model_name'],pretrained=False,num_classes=2)
        model.load_state_dict(checkpoint['model_state_dict'],strict=True)
        del checkpoint
        model=model.float().cuda().eval()
        stage('model_loaded', '[모델 완료] FP32·eval 모델 준비 완료')
        dc=resolve_model_data_config(model)
        mean,std=dc['mean'],dc['std']
        if list(mean)!=config['normalization']['mean'] or list(std)!=config['normalization']['std'] or tuple(dc['input_size'])!=(3,224,224):
            raise RuntimeError('Normalization/input configuration mismatch')
        fill=tuple(round(v*255) for v in mean)
        tree=ast.parse(TRAINING.read_text(encoding='utf-8'))
        config_node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIG' for t in n.targets))
        namespace={}
        exec(compile(ast.Module(body=[config_node],type_ignores=[]),str(TRAINING),'exec'),namespace)
        if namespace['CONFIG']!=config['config']:
            raise RuntimeError('Training source CONFIG mismatch')
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        dataset_node=next(n for n in node.body if isinstance(n,ast.ClassDef) and n.name=='DoorDataset')
        namespace.update(Dataset=Dataset,Image=Image,ImageOps=ImageOps,TF=TF,mean=mean,std=std,fill=fill)
        exec(compile(ast.Module(body=[dataset_node],type_ignores=[]),str(TRAINING),'exec'),namespace)
        dataset=namespace['DoorDataset'](rows)
        loader=DataLoader(dataset,batch_size=8,shuffle=False,num_workers=0,pin_memory=True)
        dump(out/'evaluation_config.json', evaluation_config)
        predictions=[]
        stage('gpu_evaluation', '[GPU 평가 시작] 2,039장 / FP32 / batch=8 / shuffle=False / inference_mode')
        with torch.inference_mode():
            for images,labels,indices in loader:
                if images.dtype!=torch.float32 or not torch.isfinite(images).all():
                    raise RuntimeError('Invalid input tensor')
                logits=model(images.cuda())
                if logits.shape!=(len(labels),2) or not torch.isfinite(logits).all():
                    raise RuntimeError('Invalid logits')
                scores=torch.softmax(logits,dim=1)[:,1].cpu().tolist()
                for i,y,s in zip(indices.tolist(),labels.tolist(),scores):
                    p=int(s>=0.5)
                    predictions.append(dict(image_path=rows[i]['image_path'],class_id=y,predicted_class=p,
                        raw_defect_score=s,correct=int(y==p),kind=('TP' if p else 'FN') if y else ('FP' if p else 'TN')))
                status['processed_images']=len(predictions)
                dump(out/'status.json',status)
                if len(predictions)==len(labels) or len(predictions)%200==0 or len(predictions)==2039:
                    dump(out/'status.json',status)
                    print('Evaluated',len(predictions),flush=True)
        fields=list(predictions[0])
        write_csv(out/'predictions.csv',predictions,fields)
        write_csv(out/'errors.csv',[r for r in predictions if not r['correct']],fields)
        if len(predictions)!=2039:
            raise RuntimeError('Not all 2039 images processed')
        metrics=measure(predictions)
        dump(out/'metrics.json',dict(evaluation_complete=True,processed_images=len(predictions),**metrics))
        diffs=[abs(r['raw_defect_score']-float(old_map[r['image_path']]['raw_defect_score'])) for r in predictions]
        baseline=json.loads((RUN/'best_metrics.json').read_text())
        mismatches=[r['image_path'] for r in predictions if r['predicted_class']!=int(old_map[r['image_path']]['predicted_class'])]
        dump(out/'comparison.json',dict(join='resolved absolute image_path',matched_images=len(predictions),
            prediction_class_mismatch_count=len(mismatches),prediction_class_mismatch_paths=mismatches,
            mean_absolute_score_difference=sum(diffs)/len(diffs),max_absolute_score_difference=max(diffs),
            metric_deltas={k:metrics[k]-baseline[k] for k in metrics if k in baseline},
            baseline=baseline,confirmed_environment_differences=evaluation_config['version_differences'],
            causes='No causal attribution from environment differences alone; numerical cause unconfirmed if scores differ'))
        status['evaluation_complete']=True
        stage('evaluation_complete', '[GPU 평가·비교 완료] 2,039장 처리 / metrics.json, predictions.csv, errors.csv, comparison.json 저장')
        print('[측정 지표] '+json.dumps(metrics,ensure_ascii=False),flush=True)
        report(out, predictions, metrics, '2,039장 전체 GPU 재평가 완료. 사진 자료 생성 중.')
        stage('report_assets', '[사진 보고서 시작] EXIF 원본·224×224 입력 저장 (원본 PNG 생성은 시간이 걸릴 수 있습니다)')
        for folder in ('originals','inputs','previews'):
            (out/folder).mkdir()
        for i,r in enumerate(predictions):
            with Image.open(r['image_path']) as source:
                original=ImageOps.exif_transpose(source).convert('RGB')
            r['original']=f'originals/{i:04d}.png'
            r['input']=f'inputs/{i:04d}.png'
            original.save(out/r['original'])
            preview=original.copy()
            preview.thumbnail((1000,1000),Image.Resampling.LANCZOS)
            r['preview']=f'previews/{i:04d}.jpg'
            preview.save(out/r['preview'],quality=90)
            ImageOps.pad(original,(224,224),method=Image.Resampling.BICUBIC,color=fill).save(out/r['input'])
            if i==0 or (i+1)%50==0 or i+1==2039:
                print('Report assets',i+1,flush=True)
        report(out,predictions,metrics,'2,039장 전체 GPU 재평가 완료. 원본은 EXIF 보정 RGB 무손실 PNG입니다.')
        status['report_complete']=True
        stage('gradcam', '[사진 보고서 완료] index.html 저장 / Grad-CAM 시작 (최대 8장, 각 2개 logit)')
        status['gradcam']='running'
        dump(out/'status.json',status)
        try:
            gradcam(model,dataset,predictions,out,torch,np,Image,ImageOps)
            status['gradcam']='complete'
            stage('complete', '[전체 완료] GPU 평가·비교·사진 보고서·Grad-CAM 저장 완료')
            print('REPORT: '+str(out/'index.html'),flush=True)
        except Exception:
            status['gradcam']='failed'
            status['gradcam_error']=traceback.format_exc()
            stage('partial_completion', '[부분 완료] GPU 평가 및 사진 보고서는 보존 / Grad-CAM 실패')
            print(status['gradcam_error'], file=sys.stderr, flush=True)
            (out/'gradcam').mkdir(exist_ok=True)
            (out/'gradcam/index.html').write_text('<meta charset="utf-8"><h1>Grad-CAM 미완료</h1><pre>'+html.escape(status['gradcam_error'])+'</pre>',encoding='utf-8')
            dump(out/'gradcam_failure.json',dict(error=status['gradcam_error'],evaluation_preserved=True))
        if sha(REVIEW/'observations.csv')!=evaluation_config['observations_sha256']:
            raise RuntimeError('Existing observations hash changed')
    except Exception:
        status['error']=traceback.format_exc()
        status['stage']='failed'
        print('[실패] 평가 처리 중 오류. 완료된 평가 파일은 보존합니다.',file=sys.stderr,flush=True)
        print(status['error'],file=sys.stderr,flush=True)
        dump(out/'failure.json',status)
        raise
    finally:
        dump(out/'status.json',status)
        print(json.dumps(status,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
