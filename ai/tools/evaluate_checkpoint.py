"""Re-evaluate only frozen model_selection. Explicit execution and GPU lock required."""
import argparse
import csv
import fcntl
import hashlib
import json
import math
from pathlib import Path


def state_hash(model):
    h=hashlib.sha256()
    for name,value in model.state_dict().items():h.update(name.encode());h.update(value.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:raise SystemExit('No model loaded. Add --execute only in the recorded GPU environment after stopping other GPU jobs.')
    if a.output.exists():raise SystemExit('Output exists; use a new path')
    from ai_api.e02_engine import ROOT,validate_candidate,CandidateEngine
    from door_experiment.preflight import audit_manifests
    from door_experiment.train_10 import metrics
    lock=ROOT/'outputs/door_next_runtime/.gpu.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest,run,cfg=validate_candidate();tables,_=audit_manifests(ROOT,cfg['manifests']['provenance']['config_path']);rows=tables['model_selection']
        with (run/'best_model_selection_predictions.csv').open(encoding='utf-8-sig',newline='') as f:saved=list(csv.DictReader(f))
        if len(rows)!=len(saved) or any(r['image_path']!=s['image_path'] for r,s in zip(rows,saved)):raise ValueError('Saved selection alignment mismatch')
        engine=CandidateEngine();torch=engine.torch;before=state_hash(engine.model);scores=[]
        with torch.inference_mode():
            for i in range(0,len(rows),8):
                batch=torch.stack([engine.tensor(r['image_path']) for r in rows[i:i+8]]).cuda();z=engine.model(batch)
                if not torch.isfinite(z).all():raise ValueError('Nonfinite model output')
                scores.extend(torch.softmax(z,dim=1)[:,1].cpu().tolist())
        warnings=[i for i,(score,s) in enumerate(zip(scores,saved)) if not math.isclose(score,float(s['raw_defect_score']),abs_tol=1e-6,rel_tol=1e-4)]
        labels=[r['class_id'] for r in rows];predictions=[int(x>=.5) for x in scores]
        unchanged=state_hash(engine.model)==before
        if not unchanged:raise RuntimeError('Model state changed')
        report=dict(modelVersion=manifest['modelVersion'],checkpointSHA256=manifest['checkpointSHA256'],dataRole='model_selection',sampleCount=len(rows),
                    metrics=metrics(labels,predictions),outsideOriginalScoreTolerance=len(warnings),tolerance={'abs':1e-6,'rel':1e-4},
                    maxAbsDifference=max(abs(x-float(s['raw_defect_score'])) for x,s in zip(scores,saved)),
                    modelStateUnchanged=unchanged,finalTestRead=False,calibrationOrPolicyRead=False,productionModified=False,
                    independentPerformanceEvaluation=False)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
        print('Frozen model_selection evaluation saved; original tolerance retained.')


if __name__=='__main__':main()
