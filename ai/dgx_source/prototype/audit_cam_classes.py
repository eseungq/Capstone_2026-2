"""Compare saved CAMs, optionally recompute via the unchanged production Engine.
Writes only a new storage/audits directory. No DB/review writes or service restart.
"""
import argparse
import hashlib
import html
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps,ImageDraw,ImageFont

BASE=Path(__file__).resolve().parent
IDS=('843a532c20154f9b8ca7728172aa315e','2c6a3442cfd14a5792f2c0452d2c80ff')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def compare(a,b):
    a,b=a.astype('float64'),b.astype('float64');d=np.abs(a-b)
    return dict(equal=bool(np.array_equal(a,b)),mean_absolute_difference=float(d.mean()),max_absolute_difference=float(d.max()),
        correlation=None if a.min()==a.max() or b.min()==b.max() else float(np.corrcoef(a.ravel(),b.ravel())[0,1]))


def describe(a):return dict(shape=list(a.shape),finite=bool(np.isfinite(a).all()),min=float(a.min()),max=float(a.max()))


def normalized(a):
    lo,hi=float(a.min()),float(a.max())
    return None if hi-lo<=max(1e-12,abs(hi)*1e-6) else (a-lo)/(hi-lo)


def snapshot():
    c=sqlite3.connect(f'file:{BASE}/storage/history.sqlite3?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:return dict(inspections=[dict(c.execute('SELECT * FROM inspections WHERE id=?',(ident,)).fetchone()) for ident in IDS],
        reviews=[dict(r) for ident in IDS for r in c.execute('SELECT * FROM reviews WHERE inspection_id=? ORDER BY id',(ident,))])
    finally:c.close()


def render(dest,folder,statistics):
    images=[]
    for file in ('original.png','cam0.png','cam1.png'):
        with Image.open(folder/file) as im:
            im=im.convert('RGB');im.thumbnail((700,500),Image.Resampling.LANCZOS);images.append(im.copy())
    canvas=Image.new('RGB',(2160,560),'white');draw=ImageDraw.Draw(canvas)
    try:font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
    except OSError:font=ImageFont.load_default()
    for i,(im,label) in enumerate(zip(images,('Same EXIF-corrected original','Class 0 logit CAM (independent scale)','Class 1 logit CAM (independent scale)'))):
        draw.text((i*720+10,12),label,font=font,fill='black');canvas.paste(im,(i*720+10,50))
        im.save(dest/('original.jpg','class0.jpg','class1.jpg')[i],quality=95)
    canvas.save(dest/'comparison.png')
    page='''<!doctype html><meta charset="utf-8"><title>클래스별 Grad-CAM 비교</title><style>body{font:15px system-ui;margin:24px}.row{display:flex;gap:18px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:270px}img{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f9;padding:18px}</style><h1>같은 이미지의 양품·불량 logit Grad-CAM</h1><p>모델 판단 참고 영역이며 결함 위치 검출 결과가 아닙니다. 각 맵은 독립적으로 min/max 정규화됩니다. 색의 강도를 클래스 점수 크기로 해석하면 안 됩니다.</p>'''
    page+='<div class="row">'+''.join(f'<figure><figcaption>{label}</figcaption><img src="{file}"></figure>' for label,file in [('EXIF 보정 원본','original.jpg'),('양품(0) logit CAM','class0.jpg'),('불량(1) logit CAM','class1.jpg')])+'</div>'
    page+='<p><a href="comparison.json">측정 결과 JSON</a></p><pre>'+html.escape(json.dumps(statistics,ensure_ascii=False,indent=2))+'</pre>'
    (dest/'index.html').write_text(page)


def main():
    p=argparse.ArgumentParser();p.add_argument('--saved-only',action='store_true');args=p.parse_args()
    dest=BASE/'storage/audits'/datetime.now().strftime('cam_classes_%Y%m%d_%H%M%S_%f');dest.mkdir(parents=True,exist_ok=False)
    print('OUTPUT: '+str(dest),flush=True)
    before=snapshot();folders=[BASE/'storage/records'/i for i in IDS];input_hashes=[];original_hashes=[];asset_before={}
    for folder in folders:
        for f in folder.iterdir():
            if f.is_file():asset_before[str(f)]=sha(f)
        with Image.open(folder/'upload.bin') as im:
            original=ImageOps.exif_transpose(im).convert('RGB')
            original_hashes.append(hashlib.sha256(original.tobytes()).hexdigest())
            padded=ImageOps.pad(original,(224,224),method=Image.Resampling.BICUBIC,color=(124,116,104))
            input_hashes.append(hashlib.sha256(padded.tobytes()).hexdigest())
    raw=[np.load(folders[0]/f'cam{cls}_raw.npy',allow_pickle=False) for cls in (0,1)]
    norm=[normalized(r) for r in raw]
    if any(r.shape!=(7,7) or not np.isfinite(r).all() for r in raw):raise RuntimeError('Invalid saved raw map')
    statistics=dict(source='saved production CAMs; no fresh GPU calculation yet',inspection_ids=list(IDS),
        upload_sha256=[sha(f/'upload.bin') for f in folders],upload_bytes_identical=sha(folders[0]/'upload.bin')==sha(folders[1]/'upload.bin'),
        corrected_original_pixel_hashes=original_hashes,padded_224_rgb_pixel_hashes=input_hashes,
        padded_224_inputs_identical=input_hashes[0]==input_hashes[1],
        saved_maps=[dict(target_class=cls,**describe(raw[cls])) for cls in (0,1)],
        saved_raw_cam_comparison=compare(*raw),
        saved_normalized_cam_comparison=compare(*norm) if all(n is not None for n in norm) else None,
        normalized_correlation_note='null for constant/zero maps',
        same_class_cross_record_equal={str(cls):bool(np.array_equal(raw[cls],np.load(folders[1]/f'cam{cls}_raw.npy',allow_pickle=False))) for cls in (0,1)},
        production_target='torch.autograd.grad(logits[0,cls],activation); no argmax',
        cache='records/<inspection_id>/cam<target_class>.json / .png / _raw.npy',
        gradient_handling='fresh forward graph per explain; autograd.grad w.r.t. activation does not accumulate model parameter .grad; own hook removed in finally',
        fresh_gpu_calculation=False,logits=None,gradient_comparison=None)
    if not args.saved_only:
        from engine import Engine
        engine=Engine();torch=engine.torch
        actual_inputs=[engine.tensor(f/'upload.bin') for f in folders]
        statistics['actual_normalized_tensor_hashes']=[hashlib.sha256(x.numpy().tobytes()).hexdigest() for x in actual_inputs]
        statistics['actual_normalized_tensors_equal']=bool(torch.equal(*actual_inputs))
        if not statistics['actual_normalized_tensors_equal']:raise RuntimeError('Inputs differ')
        layer=engine.model.get_submodule('layers.3.blocks.1.norm1');captured=[];recomputed=[];hook_records=[]
        for cls in (0,1):
            class_dest=dest/f'class{cls}';class_dest.mkdir()
            data={};tensor_handles=[];baseline_hooks=len(layer._forward_hooks)
            def feature_hook(module,args,out):
                data['activation']=out.detach().cpu().numpy().copy()
                tensor_handles.append(out.register_hook(lambda gradient:data.update(gradient=gradient.detach().cpu().numpy().copy())))
            def logits_hook(module,args,out):data['logits']=out.detach().cpu().numpy().copy()
            feature_handle=layer.register_forward_hook(feature_hook);logits_handle=engine.model.register_forward_hook(logits_hook)
            param_grads_before=sum(p.grad is not None for p in engine.model.parameters())
            try:
                # Use the unchanged real production method, not a diagnostic CAM implementation.
                info=engine.explain(folders[0]/'upload.bin',class_dest,cls)
                hook_records.append(dict(target_class=cls,baseline_feature_hooks=baseline_hooks,
                    hooks_after_production_explain=len(layer._forward_hooks),parameter_grads_before=param_grads_before,
                    parameter_grads_after=sum(p.grad is not None for p in engine.model.parameters())))
            finally:
                feature_handle.remove();logits_handle.remove()
                for handle in tensor_handles:handle.remove()
            hook_records[-1]['hooks_after_diagnostic_cleanup']=len(layer._forward_hooks)
            assert len(layer._forward_hooks)==baseline_hooks
            assert hook_records[-1]['parameter_grads_after']==param_grads_before==0
            np.save(class_dest/'activation.npy',data['activation']);np.save(class_dest/'gradient.npy',data['gradient'])
            a,g=data['activation'].transpose(0,3,1,2),data['gradient'].transpose(0,3,1,2)
            signed=(g.mean((2,3),keepdims=True)*a).sum(1)[0];np.save(class_dest/'signed_cam.npy',signed)
            data['signed_cam']=signed;data['info']=info;captured.append(data)
            recomputed.append(np.load(class_dest/f'cam{cls}_raw.npy',allow_pickle=False))
            print(f'[클래스 {cls} 완료] logits={data["logits"].tolist()} target={cls}',flush=True)
        fresh_norm=[normalized(r) for r in recomputed]
        statistics.update(source='saved CAM comparison plus fresh GPU production Engine.explain calls on same image for classes 0 and 1',
            fresh_gpu_calculation=True,model=engine.metadata,
            logits=[d['logits'].tolist() for d in captured],selected_logit=[float(d['logits'][0,cls]) for cls,d in enumerate(captured)],
            logits_between_passes=compare(captured[0]['logits'],captured[1]['logits']),
            gradient_descriptions=[describe(d['gradient']) for d in captured],gradient_comparison=compare(captured[0]['gradient'],captured[1]['gradient']),
            activation_comparison=compare(captured[0]['activation'],captured[1]['activation']),
            signed_pre_relu_cam_comparison=compare(captured[0]['signed_cam'],captured[1]['signed_cam']),
            fresh_raw_cam_descriptions=[describe(r) for r in recomputed],fresh_raw_cam_comparison=compare(*recomputed),
            fresh_normalized_cam_comparison=compare(*fresh_norm) if all(n is not None for n in fresh_norm) else None,
            fresh_vs_saved=[compare(recomputed[cls],raw[cls]) for cls in (0,1)],hook_checks=hook_records)
    statistics['selected_db_records_unchanged']=before==snapshot()
    statistics['original_record_files_unchanged']=all(sha(Path(f))==digest for f,digest in asset_before.items())
    (dest/'comparison.json').write_text(json.dumps(statistics,ensure_ascii=False,indent=2,allow_nan=False))
    render(dest,folders[0],statistics)
    print(json.dumps(statistics,ensure_ascii=False,indent=2),flush=True);print('REPORT: '+str(dest/'index.html'),flush=True)


if __name__=='__main__':main()
