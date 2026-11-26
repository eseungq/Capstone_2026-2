"""Compare two frozen models on CPU using identical class-logit Grad-CAM."""
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

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def dump(path,data):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    temporary.replace(path)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);a=parser.parse_args()
    frozen=json.loads(a.manifest.read_text());out=a.manifest.parent
    assert os.environ.get('CUDA_VISIBLE_DEVICES')=='' and not torch.cuda.is_available()
    Image.MAX_IMAGE_PIXELS=120000000
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    versions={name:importlib.metadata.version(name) for name in frozen['versions']}
    assert versions==frozen['versions']
    validate_candidate()
    assert frozen['layer']=='layers.3.blocks.1.norm1' and frozen['target']=='DEFECT logit'
    source=Path(frozen['datasetSource']);assert sha(source)==frozen['datasetSourceSHA256']
    tree=ast.parse(source.read_text());main_node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');dataset_node=next(n for n in main_node.body if isinstance(n,ast.ClassDef) and n.name=='DoorDataset')
    assert hashlib.sha256(ast.dump(dataset_node,include_attributes=False).encode()).hexdigest()==frozen['datasetASTSHA256']
    report=dict(status='running',device='cpu',threads=2,manifestSHA256=sha(a.manifest),versions=versions,layer=frozen['layer'],target=frozen['target'],modelRuns=frozen['modelRuns'],modelHashes=frozen['modelHashes'],models={},samples={r['id']:dict(id=r['id'],results={}) for r in frozen['samples']},newTrainingPerformed=False,productionChanged=False,finalTestImagesRead=False,independentPerformanceEvaluation=False)
    dump(out/'report.json',report);started=time.monotonic()
    for name in ('old','new'):
        run=Path(frozen['modelRuns'][name]);checkpoint_path=run/'best.pt'
        assert sha(checkpoint_path)==frozen['modelHashes'][name]
        assert sha(run/'run_config.json')==frozen['configHashes'][name]
        cfg=json.loads((run/'run_config.json').read_text())
        assert cfg['versions']==versions and cfg['normalization']==frozen['normalization']
        torch.manual_seed(42);np.random.seed(42)
        model=timm.create_model(frozen['modelName'],pretrained=False,num_classes=2)
        checkpoint=torch.load(checkpoint_path,map_location='cpu',weights_only=False)
        assert checkpoint['epoch']==frozen['epochs'][name] and json.loads(json.dumps(checkpoint['metadata']))==cfg
        model.load_state_dict(checkpoint['model_state_dict'],strict=True);del checkpoint
        model=model.float().cpu().eval();before=digest(model)
        dc=resolve_model_data_config(model);mean,std=dc['mean'],dc['std'];fill=tuple(round(v*255) for v in mean)
        assert list(mean)==cfg['normalization']['mean'] and list(std)==cfg['normalization']['std'] and fill==(124,116,104)
        namespace=dict(Dataset=Dataset,Image=Image,ImageOps=ImageOps,TF=TF,CONFIG=cfg['config'],mean=mean,std=std,fill=fill)
        exec(compile(ast.Module(body=[dataset_node],type_ignores=[]),str(source),'exec'),namespace)
        dataset=namespace['DoorDataset']
        for sample in frozen['samples']:
            sid=sample['id'];folder=out/sid;path=Path(sample['image_path']);assert sha(path)==sample['imageSHA256']
            x=dataset([dict(image_path=str(path),class_id=1)])[0][0].unsqueeze(0).cpu()
            baseline=scores(model,x);info,raw,full=cam(model,x,frozen['layer'],'defect')
            assert raw.shape==(7,7) and info['featureShape']==[1,7,7,768]
            reference=sample['oldSavedGPUBatchScore'] if name=='old' else sample['newCPUReference']['baselineCPU']['probability']
            result=dict(model=name,modelVersion=frozen['modelVersions'][name],epoch=frozen['epochs'][name],baseline=baseline,predictedQuality='DEFECT' if baseline['probability']>=.5 else 'GOOD',referenceScore=reference,referenceScope='stored GPU batch score' if name=='old' else 'previous CPU single-image score',scoreWithinOriginalTolerance=math.isclose(baseline['probability'],reference,abs_tol=1e-6,rel_tol=1e-4),cam=info)
            np.save(folder/(name+'_raw.npy'),raw)
            if name=='new':
                ref=Path(sample['newCPURawReference']);assert sha(ref)==sample['newCPURawReferenceSHA256']
                original_raw=np.load(ref,allow_pickle=False)
                result['previousCPURawMapExactlyReproduced']=bool(np.array_equal(raw,original_raw))
                result['previousCPURawMapMaxDifference']=float(np.max(np.abs(raw-original_raw)))
                result['previousCPUScoreExactlyReproduced']=baseline['probability']==reference
                assert result['previousCPURawMapExactlyReproduced'] and result['previousCPUScoreExactlyReproduced']
            if full is not None:
                with Image.open(path) as src:original=ImageOps.exif_transpose(src).convert('RGB')
                contained=ImageOps.contain(original,(224,224),method=Image.Resampling.BICUBIC)
                w,h=contained.size;left,top=round((224-w)*.5),round((224-h)*.5)
                with Image.open(folder/'original.jpg') as image:display=image.convert('RGB')
                values=np.asarray(Image.fromarray(full[top:top+h,left:left+w]).resize(display.size,Image.Resampling.BILINEAR))
                heat=np.stack((values,np.zeros_like(values),1-values),axis=-1)*255
                Image.fromarray(np.clip(np.asarray(display,dtype=np.float32)*.6+heat*.4,0,255).astype('uint8')).save(folder/(name+'_overlay.jpg'),quality=92)
                result['overlay']=name+'_overlay.jpg'
            report['samples'][sid]['results'][name]=result
            dump(out/'report.json',report)
            print('[MODEL CAM]',name,sid,result['predictedQuality'],info['status'],flush=True)
        unchanged=digest(model)==before;assert unchanged
        checkpoint_unchanged=sha(checkpoint_path)==frozen['modelHashes'][name];assert checkpoint_unchanged
        report['models'][name]=dict(modelStateUnchanged=unchanged,checkpointUnchanged=checkpoint_unchanged)
        del model
    report['status']='completed_same_layer_cpu_comparison_human_interpretation_pending'
    report['elapsedSeconds']=time.monotonic()-started
    dump(out/'report.json',report)
    build_view(out,frozen,report)
    with zipfile.ZipFile(out/'old20_new2_comparison.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in out.rglob('*'):
            if p.is_file() and p.suffix!='.zip':archive.write(p,p.relative_to(out))
    print('[COMPARISON COMPLETE]',out,flush=True)

def build_view(out,frozen,report):
    parts=['<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>이전 20회차·재학습 2회차 CAM 비교</title><style>body{font-family:"Malgun Gothic",sans-serif;max-width:1480px;margin:24px auto;padding:0 20px;background:#f4f7fa;line-height:1.75;color:#182535}header,section{padding:20px;background:white;border-radius:10px;margin-bottom:24px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}figure{margin:0;background:#edf2f7;border:1px solid #cad5e0}img{display:block;width:100%}figcaption{padding:10px}.note{white-space:pre-wrap;padding:12px;background:#eef3f9}.warn{padding:12px;background:#fff0cf}</style></head><body><header><h1>이전 20회차 vs 재학습 2회차</h1><p>이미 결함을 확인한 공통 3장입니다. 두 모델 모두의 이미지 단위 검증 목록에 포함되어 있습니다. 같은 CPU 환경·FP32·전처리·7×7 레이어·불량 클래스 logit·색상 및 맵별 정규화를 사용했습니다.</p><p>빨간색은 각 맵 안에서의 상대적 반응입니다. 서로 다른 모델의 빨간색 진하기나 보정 전 점수를 위치 정확도처럼 비교하지 않습니다. 새 학습이나 운영 모델 교체는 하지 않았습니다. 3장만으로 전체 성능을 판단할 수 없으며 데이터의 실물 단위 독립성을 보증하지 않습니다.</p></header>']
    for sample in frozen['samples']:
        sid=sample['id'];row=report['samples'][sid];parts.append('<section><h2>'+sid+' / '+html.escape(sample['source_categories'])+'</h2><div class="grid">')
        for filename,title in [('original.jpg','원본 표시'),('input224.png','모델 입력 224×224'),('old_overlay.jpg','이전 모델 · 최고 20회차 · 7×7'),('new_overlay.jpg','재학습 모델 · 최고 2회차 · 7×7')]:
            if (out/sid/filename).exists():parts.append(f'<figure><a href="{sid}/{filename}" target="_blank"><img src="{sid}/{filename}"></a><figcaption>{title}</figcaption></figure>')
            else:parts.append('<figure><figcaption>'+title+': 유효한 활성화 맵 없음</figcaption></figure>')
        parts.append('</div>')
        for name,title in [('old','이전 20회차'),('new','재학습 2회차')]:
            result=row['results'][name]
            parts.append('<p>'+title+': '+result['predictedQuality']+' / 보정 전 불량 점수 '+format(result['baseline']['probability'],'.9f')+' / CAM '+result['cam']['status']+'</p>')
            if not result['scoreWithinOriginalTolerance']:parts.append('<p class="warn">'+title+': 저장된 기준 점수와 기존 허용오차 밖의 차이가 있습니다. 오차 기준은 변경하지 않았습니다.</p>')
        review=sample['previousHumanReview'];parts.append('<p class="note">앞선 사용자 기록 — 현재 7×7: '+html.escape(review['current'])+' / 후보 14×14: '+html.escape(review['candidate'])+'\n'+html.escape(review.get('note',''))+'</p></section>')
    parts.append('</body></html>');(out/'comparison.html').write_text('\n'.join(parts))

if __name__=='__main__':main()
