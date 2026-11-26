"""Separate frame training. Smoke runs are execution checks, never model evaluations."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import random
import shutil
import time
from frame_model.check import ROOT, read_image


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def metrics(rows):
    tp=sum(r['actual']==1 and r['predicted']==1 for r in rows)
    tn=sum(r['actual']==0 and r['predicted']==0 for r in rows)
    fp=sum(r['actual']==0 and r['predicted']==1 for r in rows)
    fn=sum(r['actual']==1 and r['predicted']==0 for r in rows)
    return dict(n=len(rows),tp=tp,tn=tn,fp=fp,fn=fn,
                accuracy=(tp+tn)/len(rows) if rows else None,
                precision=tp/(tp+fp) if tp+fp else None,
                false_positive_rate=fp/(tn+fp) if tn+fp else None,
                f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                false_negative_rate=fn/(tp+fn) if tp+fn else None)


def subset(rows, per_cell):
    cells={}
    for row in rows:
        key=(row['defect_type'],row['class_id'])
        cells.setdefault(key,[]).append(row)
    types={key[0] for key in cells}
    if not types or any((kind,y) not in cells for kind in types for y in ['0','1']):
        raise ValueError('Each included inspection type needs both classes')
    return [r for key in sorted(cells) for r in sorted(cells[key],key=lambda r:r['image_id'])[:per_cell]]


def manifests(prep):
    config=json.loads((prep/'config.json').read_text())
    for name, stat in config['archive_stats'].items():
        actual=Path(name).stat()
        if (actual.st_size,actual.st_mtime_ns)!=(stat['bytes'],stat['mtime_ns']):
            raise ValueError('Source archive changed: '+name)
    tables={}; groups=set(); hashes=set()
    for role,m in config['manifests'].items():
        data=Path(m['path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=m['sha256']: raise ValueError('Manifest changed: '+role)
        rows=list(csv.DictReader(io.StringIO(data.decode())))
        gs={r['group_id'] for r in rows}; hs={r['image_sha256'] for r in rows}
        if groups & gs or hashes & hs or len(hs)!=len(rows): raise ValueError('Split overlap')
        if len(rows)!=config['roles'][role]: raise ValueError('Manifest count differs')
        groups.update(gs); hashes.update(hs)
        if role in ('train','model_selection'): tables[role]=rows
    return config,tables


def write_csv(path,rows):
    if not rows: return
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['smoke','train'],default='smoke')
    parser.add_argument('--preparation',type=Path)
    parser.add_argument('--start-training',action='store_true',help='Required for full 20-epoch training')
    args=parser.parse_args()
    if args.mode=='train' and not args.start_training: parser.error('Full training requires --start-training')
    prep=args.preparation or Path(json.loads((ROOT/'frame_model/latest_preparation.json').read_text())['preparation'])
    config,tables=manifests(prep)
    smoke=args.mode=='smoke'
    if smoke:
        tables={role:subset(rows,16 if role=='train' else 8) for role,rows in tables.items()}
    out=ROOT/'outputs/frame_training'/f"{args.mode}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')}"
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'status.json',{'status':'starting','mode':args.mode,'quality_evaluation':not smoke})
    print('[FRAME RUN]',out,flush=True)
    try:
        execute(config,tables,prep,out,smoke)
    except BaseException as exc:
        dump(out/'status.json',{'status':'failed_or_interrupted','mode':args.mode,'error_type':type(exc).__name__,'quality_evaluation':not smoke})
        raise


def execute(config,tables,prep,out,smoke,*,context=None,initial_state=None):
    import importlib.metadata as metadata
    import numpy as np
    import torch
    import timm
    from torch.utils.data import Dataset,DataLoader
    from torchvision.transforms import functional as TF
    if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
    random.seed(config['seed']);np.random.seed(config['seed']);torch.manual_seed(config['seed']);torch.cuda.manual_seed_all(config['seed'])
    torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
    generator=torch.Generator().manual_seed(config['seed'])
    class Images(Dataset):
        def __init__(self,rows): self.rows=rows
        def __len__(self): return len(self.rows)
        def __getitem__(self,index):
            row=self.rows[index]
            _,image=read_image(row)
            return TF.normalize(TF.to_tensor(image),config['mean'],config['std']),int(row['class_id']),index
    loaders={role:DataLoader(Images(rows),batch_size=config['batch_size'],shuffle=role=='train',num_workers=0,generator=generator if role=='train' else None) for role,rows in tables.items()}
    if shutil.disk_usage(out).free < 3*1024**3: raise RuntimeError('Need at least 3 GiB free; no files deleted')
    print('[INITIAL STATE] '+(str(initial_state) if initial_state else 'Loading base ImageNet weights; first run may download. Door weights are not used.'),flush=True)
    model=timm.create_model(config['model_name'],pretrained=initial_state is None,num_classes=2)
    if initial_state is not None:
        model.load_state_dict(torch.load(initial_state,map_location='cpu',weights_only=True),strict=True)
    initial_digest=hashlib.sha256()
    for name,tensor in sorted(model.state_dict().items()):
        initial_digest.update(name.encode());initial_digest.update(str(tensor.dtype).encode());initial_digest.update(str(tuple(tensor.shape)).encode())
        initial_digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    model=model.cuda()
    # Preserve the exact initialization for provenance, including the newly initialized head.
    torch.save(model.state_dict(),out/'initial_state.pt')
    provenance={'mode':'smoke' if smoke else 'train','preparation':str(prep),'config':config,'sample_counts':{k:len(v) for k,v in tables.items()},'epochs':1 if smoke else config['epochs'],'versions':{p:metadata.version(p) for p in ['torch','torchvision','timm','Pillow','numpy']},'gpu':torch.cuda.get_device_name(0),'cuda':torch.version.cuda,'pretrained_configuration':model.pretrained_cfg,'initial_state_sha256':hashlib.sha256((out/'initial_state.pt').read_bytes()).hexdigest(),'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['frame_model/train.py','frame_model/check.py','frame_model/run_gpu.sh']},'quality_evaluation':not smoke,'precision':'FP32','checkpoint_retention':'initial_state plus last and best; smoke saves smoke_last only','calibration_or_policy_pixels_used':False,'limitations':config['limitations']}
    provenance.update(experiment_context=context,initial_tensor_sha256=initial_digest.hexdigest(),initial_state_source=str(initial_state) if initial_state else 'ImageNet initialization with seed-controlled head')
    provenance['source_sha256']['frame_model/experiments.py']=hashlib.sha256((ROOT/'frame_model/experiments.py').read_bytes()).hexdigest() if (ROOT/'frame_model/experiments.py').exists() else None
    dump(out/'run_config.json',provenance)
    for role,rows in tables.items(): write_csv(out/f'{role}_used.csv',rows)
    optimizer=torch.optim.AdamW(model.parameters(),lr=config['learning_rate'],weight_decay=config['weight_decay'])
    criterion=torch.nn.CrossEntropyLoss();history=[];best=-1
    for epoch in range(1,provenance['epochs']+1):
        torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start=time.perf_counter();model.train();loss_sum=0;seen=0
        for step,(images,labels,_) in enumerate(loaders['train'],1):
            images=images.cuda();labels=labels.cuda();optimizer.zero_grad(set_to_none=True)
            loss=criterion(model(images),labels)
            if not torch.isfinite(loss): raise RuntimeError('Nonfinite training loss')
            loss.backward();optimizer.step();loss_sum+=loss.item()*len(labels);seen+=len(labels)
            if step==1 or step%100==0: print(f'[TRAIN] epoch={epoch} batch={step}/{len(loaders["train"])} loss={loss_sum/seen:.6f}',flush=True)
        torch.cuda.synchronize();train_seconds=time.perf_counter()-start
        model.eval();predictions=[];val_start=time.perf_counter()
        with torch.inference_mode():
            for images,labels,indices in loaders['model_selection']:
                logits=model(images.cuda())
                if not torch.isfinite(logits).all(): raise RuntimeError('Nonfinite validation logits')
                scores=torch.softmax(logits,dim=1)[:,1].cpu().tolist()
                for idx,y,score in zip(indices.tolist(),labels.tolist(),scores):
                    if not math.isfinite(score) or not 0<=score<=1: raise RuntimeError('Invalid score')
                    row=tables['model_selection'][idx]
                    predictions.append(dict(image_id=row['image_id'],defect_type=row['defect_type'],actual=y,predicted=int(score>=config['prediction_cutoff']),raw_defect_score=score))
        torch.cuda.synchronize();val_seconds=time.perf_counter()-val_start
        result=dict(epoch=epoch,train_loss=loss_sum/seen,train_seconds=train_seconds,validation_seconds=val_seconds,peak_allocated_bytes=torch.cuda.max_memory_allocated(),**metrics(predictions))
        history.append(result);write_csv(out/'history.csv',history)
        type_metrics={kind:metrics([r for r in predictions if r['defect_type']==kind]) for kind in config['inspection_types']}
        dump(out/f'epoch_{epoch:02d}_type_metrics.json',type_metrics)
        checkpoint=dict(epoch=epoch,model_state_dict=model.state_dict(),optimizer_state_dict=optimizer.state_dict(),metadata=provenance,metrics=result,python_rng_state=random.getstate(),numpy_rng_state=np.random.get_state(),torch_rng_state=torch.get_rng_state(),cuda_rng_state=torch.cuda.get_rng_state_all(),train_loader_rng_state=generator.get_state())
        save_start=time.perf_counter()
        torch.save(checkpoint,out/('smoke_last.pt' if smoke else 'last.pt'))
        f1=result['f1'] if result['f1'] is not None else -1
        write_csv(out/'last_model_selection_predictions.csv',predictions)
        if smoke:
            write_csv(out/'smoke_predictions_NOT_EVALUATION.csv',predictions)
        elif f1>best:
            best=f1;torch.save(checkpoint,out/'best.pt');write_csv(out/'best_model_selection_predictions.csv',predictions);dump(out/'best_type_metrics.json',type_metrics)
        save_seconds=time.perf_counter()-save_start
        print('[EPOCH]',json.dumps(result),flush=True)
        if smoke:
            # Small run uses first deterministic samples per cell, not a representative speed/quality evaluation.
            estimate=config['roles']['train']/seen*train_seconds+config['roles']['model_selection']/len(predictions)*val_seconds+save_seconds
            dump(out/'timing.json',{'train_images':seen,'validation_images':len(predictions),'train_seconds':train_seconds,'validation_seconds':val_seconds,'save_seconds':save_seconds,'rough_seconds_per_full_epoch':estimate,'rough_seconds_for_20_epochs':estimate*config['epochs'],'limitations':'Small cold-start sample; rough extrapolation, not a promised duration. Excludes initial weight download/startup. Includes measured read/decode/optimizer/validation/checkpoint, whose costs vary by image and cache.'})
    artifacts={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['run_config.json','train_used.csv','model_selection_used.csv','last_model_selection_predictions.csv','best_model_selection_predictions.csv','smoke_predictions_NOT_EVALUATION.csv'] if (out/name).exists()}
    dump(out/'artifacts.json',artifacts)
    dump(out/'status.json',{'status':'passed','mode':'smoke' if smoke else 'train','quality_evaluation':not smoke,'calibration_ready':False,'policy_ready':False})
    print('[FRAME SMOKE PASSED]' if smoke else '[FRAME TRAINING COMPLETE]',out,flush=True)

if __name__=='__main__': main()
