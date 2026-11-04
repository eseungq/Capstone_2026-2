"""GPU-only engine. Preprocessing extracted unchanged from the original training code."""
import ast
import os
import hashlib
import importlib.metadata
import json
import random
import time
from pathlib import Path

ROOT = Path(os.environ.get('AI_PROJECT_ROOT', Path(__file__).resolve().parents[1])).expanduser().resolve()
RUN = ROOT/'outputs/training/door_swin_tiny_20261008_183758_369671'
VALIDATED = ROOT/'outputs/evaluation/door_20261015_024950_271668/evaluation_config.json'
TRAINING = Path(os.environ.get('AI_LEGACY_TRAINING_SOURCE', ROOT/'private_artifacts/legacy_training_source.py'))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


class Engine:
    def __init__(self):
        import numpy as np
        import torch
        import timm
        from PIL import Image,ImageOps
        from torch.utils.data import Dataset
        from torchvision.transforms import functional as TF
        from timm.data import resolve_model_data_config
        self.torch,self.np=torch,np
        cfg=json.loads((RUN/'run_config.json').read_text())
        verified=json.loads(VALIDATED.read_text())
        versions={p:importlib.metadata.version(p) for p in cfg['versions']}
        if versions!=cfg['versions']: raise RuntimeError(f'Library version mismatch: {versions}')
        if not torch.cuda.is_available(): raise RuntimeError('CUDA GPU unavailable; no fallback prediction')
        digest=sha(RUN/'best.pt')
        if digest!=verified['model_sha256'] or sha(TRAINING)!=verified['training_source_sha256']:
            raise RuntimeError('Model/training source hash differs from validated run')
        if cfg['class_mapping']!={'양품':0,'불량품':1}: raise RuntimeError('Class mapping mismatch')
        random.seed(42);np.random.seed(42);torch.manual_seed(42);torch.cuda.manual_seed_all(42)
        torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
        checkpoint=torch.load(RUN/'best.pt',map_location='cpu',weights_only=False)
        if json.loads(json.dumps(checkpoint['metadata']))!=cfg: raise RuntimeError('Checkpoint metadata mismatch')
        self.model=timm.create_model(cfg['config']['model_name'],pretrained=False,num_classes=2)
        self.model.load_state_dict(checkpoint['model_state_dict'],strict=True)
        del checkpoint
        self.model=self.model.float().cuda().eval()
        dc=resolve_model_data_config(self.model)
        mean,std=dc['mean'],dc['std']
        if list(mean)!=cfg['normalization']['mean'] or list(std)!=cfg['normalization']['std'] or tuple(dc['input_size'])!=(3,224,224):
            raise RuntimeError('Model data configuration mismatch')
        self.fill=tuple(round(v*255) for v in mean)
        tree=ast.parse(TRAINING.read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        node=next(n for n in main.body if isinstance(n,ast.ClassDef) and n.name=='DoorDataset')
        ns=dict(Dataset=Dataset,Image=Image,ImageOps=ImageOps,TF=TF,CONFIG=cfg['config'],mean=mean,std=std,fill=self.fill)
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(TRAINING),'exec'),ns)
        self.dataset=ns['DoorDataset']
        self.metadata=dict(model_name=cfg['config']['model_name'],model_sha256=digest,
            checkpoint_epoch=20,versions=versions,gpu=torch.cuda.get_device_name(0),
            pretrained=False,strict=True,precision='FP32',batch_size=1,cutoff=0.5,
            classes=cfg['class_mapping'],normalization=cfg['normalization'],
            preprocessing=verified['preprocessing'],automatic_pass=False)
        print('[GPU 준비 완료] '+json.dumps(self.metadata,ensure_ascii=False),flush=True)

    def tensor(self,path):
        # class_id is unused by the model; only the decoded pixel tensor is passed.
        x=self.dataset([dict(image_path=str(path),class_id=0)])[0][0]
        if x.shape!=(3,224,224) or x.dtype!=self.torch.float32 or not self.torch.isfinite(x).all():
            raise RuntimeError('Invalid input tensor')
        return x

    def predict(self,path):
        torch=self.torch
        torch.cuda.synchronize()
        start=time.perf_counter()
        x=self.tensor(path).unsqueeze(0).cuda()
        with torch.inference_mode():
            logits=self.model(x)
            if logits.shape!=(1,2) or not torch.isfinite(logits).all(): raise RuntimeError('Invalid logits')
            score=torch.softmax(logits,dim=1)[0,1].item()
        torch.cuda.synchronize()
        ms=(time.perf_counter()-start)*1000
        return dict(predicted_class=int(score>=0.5),raw_defect_score=score,processing_ms=ms,
            timing_scope='잠금 대기 이후 이미지 읽기·EXIF/RGB·224 패딩·정규화·CPU→GPU·FP32 forward·softmax·GPU 동기화 포함. 업로드·모델 로딩·DB 저장·Grad-CAM 제외.',
            model=self.metadata)

    def explain(self,path,dest,cls):
        """Same math, layer and coordinate mapping as src/evaluate_door_internal.py:gradcam."""
        from PIL import Image,ImageOps
        torch,np=self.torch,self.np
        self.model.eval()
        before={k:v.detach().cpu().clone() for k,v in self.model.state_dict().items()}
        layer_name='layers.3.blocks.1.norm1'
        cache={}
        handle=self.model.get_submodule(layer_name).register_forward_hook(lambda m,a,o:cache.update(activation=o))
        try:
            with torch.enable_grad():
                x=self.tensor(path).unsqueeze(0).cuda().requires_grad_(True)
                logits=self.model(x)
                if not torch.isfinite(logits).all(): raise RuntimeError('Nonfinite Grad-CAM logits')
                activation=cache['activation']
                gradient,=torch.autograd.grad(logits[0,cls],activation)
                if tuple(activation.shape)!=(1,7,7,768) or gradient.shape!=activation.shape:
                    raise RuntimeError('Unexpected Swin feature shape')
                if not torch.isfinite(activation).all() or not torch.isfinite(gradient).all(): raise RuntimeError('Nonfinite activation/gradient')
                a,g=activation.permute(0,3,1,2),gradient.permute(0,3,1,2)
                cam=torch.relu((g.mean((2,3),keepdim=True)*a).sum(1))[0].detach().cpu().numpy()
        finally: handle.remove()
        if not np.isfinite(cam).all(): raise RuntimeError('Nonfinite CAM')
        lo,hi=float(cam.min()),float(cam.max())
        constant=hi-lo<=max(1e-12,abs(hi)*1e-6)
        info=dict(target_class=cls,layer=layer_name,activation_shape=list(activation.shape),gradient_shape=list(gradient.shape),
            activation_finite=True,gradient_finite=True,raw_min=lo,raw_max=hi,constant=constant,
            normalization='ReLU; per-map (cam-min)/(max-min); constant/zero maps have no overlay',
            warning='모델 판단 참고 영역이며 결함 위치 검출 결과가 아님',overlay=None,
            implementation_reference='src/evaluate_door_internal.py:gradcam')
        np.save(dest/f'cam{cls}_raw.npy',cam)
        if not constant:
            with Image.open(path) as source: original=ImageOps.exif_transpose(source).convert('RGB')
            contained=ImageOps.contain(original,(224,224),method=Image.Resampling.BICUBIC)
            w,h=contained.size;left,top=round((224-w)*0.5),round((224-h)*0.5)
            norm=(cam-lo)/(hi-lo)
            full=np.asarray(Image.fromarray(norm.astype('float32')).resize((224,224),Image.Resampling.BILINEAR))
            cropped=Image.fromarray(full[top:top+h,left:left+w]).resize(original.size,Image.Resampling.BILINEAR)
            values=np.clip(np.asarray(cropped),0,1)
            heat=np.stack((values,np.zeros_like(values),1-values),axis=-1)*255
            overlay=(np.asarray(original)*0.6+heat*0.4).clip(0,255).astype('uint8')
            Image.fromarray(overlay).save(dest/f'cam{cls}.png')
            info.update(overlay=f'cam{cls}.png',padding_crop=[left,top,left+w,top+h],original_size=list(original.size))
        unchanged=all(torch.equal(before[k],v.detach().cpu()) for k,v in self.model.state_dict().items())
        if not unchanged: raise RuntimeError('Model state changed during Grad-CAM')
        info.update(state_unchanged=True,eval_mode=not self.model.training)
        (dest/f'cam{cls}.json').write_text(json.dumps(info,ensure_ascii=False,indent=2))
        return info
