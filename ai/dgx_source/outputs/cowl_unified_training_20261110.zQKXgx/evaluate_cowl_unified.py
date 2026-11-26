"""Compare the trained cowl unified model with the component models on matched photos."""

from collections import Counter
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import timm
import torch

from cowl_unified_training import sha, load, save, check
from evaluate_cowl_pin_policy import extract
from frame_model.cam_review import verify_metadata
from frame_model.train import metrics
from cowl_pin_trial_api import read_csv


PIN = ("outputs/cowl_pin_official_20261109.R5u6W0",) * 2
LINK = ("outputs/cowl_linkage_official_20261110.VxAkw0",
        "outputs/cowl_linkage_validation_overlap_20261110.LqxzgI")


def reference(kind, paths):
    scored, audited = map(Path,paths)
    if kind=="fixed_pin":
        report=load(scored/"official_policy_report.json")
        model=report["frozen_policy"]["checkpoint_sha256"]
        manifest_hash, scores_hash=report["official_manifest_sha256"],report["score_sha256"]
        totals=(1294,1149)
    else:
        report=load(scored/"evaluation_report.json")
        model=report["checkpoint_sha256"]
        manifest_hash,scores_hash=report["evaluation_manifest_sha256"],report["official_scores_sha256"]
        totals=(1237,1053)
    m,s=audited/"frozen_evaluation_manifest.json",scored/"official_scores.csv"
    assert (sha(m),sha(s))==(manifest_hash,scores_hash)
    rows={r["image_id"]:r for r in load(m) if r["excluded"] is None}
    scores={r["image_id"]:r for r in read_csv(s)}
    assert rows.keys()==scores.keys()
    for i,r in rows.items():
        assert (r["class_id"],r["image_sha256"])==(scores[i]["label"],scores[i]["image_sha256"])
    assert (len(rows),sum(not r["cross_near"] for r in rows.values()))==totals
    return rows,scores,dict(checkpoint_sha256=model,manifest_sha256=manifest_hash,scores_sha256=scores_hash)


def stats(rows):
    calculated=metrics(rows)
    calculated["defect_recall"]=calculated["tp"]/(calculated["tp"]+calculated["fn"])
    return calculated


def main(stage):
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    run=stage/"runs/train"
    config,_,_=check(stage)
    status=load(run/"status.json")
    assert status["status"]=="passed" and status["mode"]=="train"
    meta=load(run/"run_config.json")
    assert meta["epochs"]==12 and meta["config"]==config and not meta["calibration_or_policy_pixels_used"]
    history=read_csv(run/"history.csv")
    assert [int(r["epoch"]) for r in history]==list(range(1,13))
    best=max(history,key=lambda r:float(r["f1"]))
    checkpoint=run/"best.pt"
    with torch.serialization.safe_globals([np._core.multiarray._reconstruct,np.ndarray,np.dtype,np.dtypes.UInt32DType]):
        ck=torch.load(checkpoint,map_location="cpu",weights_only=True)
    assert ck["epoch"]==int(best["epoch"])
    verify_metadata(ck["metadata"],meta)
    model=timm.create_model(config["model_name"],pretrained=False,num_classes=2)
    model.load_state_dict(ck["model_state_dict"],strict=True)
    model.eval()
    engine=SimpleNamespace(model=model,config=config)
    del ck
    out=stage/"official_evaluation"
    out.mkdir()
    references={kind:reference(kind,paths) for kind,paths in (("fixed_pin",PIN),("linkage",LINK))}
    fixed,link=(references[k][0] for k in ("fixed_pin","linkage"))
    assert not fixed.keys() & link.keys()
    overlap={r["display_sha256"] for r in fixed.values()} & {r["display_sha256"] for r in link.values()}
    # Preserve each official per-type comparison and disclose shared images in the pooled summary.
    all_predictions, results = {}, {}
    for kind,(rows,baseline,source) in references.items():
        photos=sorted(rows.values(),key=lambda r:r["offset"])
        output=out/f"{kind}_scores.csv"
        all_predictions[kind]={r["image_id"]:r for r in extract(engine,photos,output)}
        assert all_predictions[kind].keys()==rows.keys()
        results[kind]={"baseline_source":source,"unified_scores_sha256":sha(output),"scopes":{}}
        for scope,identifiers in (("primary",list(rows)),("sensitivity",[i for i,r in rows.items() if not r["cross_near"]])):
            predictions=all_predictions[kind]
            truth=[int(rows[i]["class_id"]) for i in identifiers]
            before=[int(baseline[i]["prediction"]) for i in identifiers]
            after=[predictions[i]["prediction"] for i in identifiers]
            compare=Counter((y,int(x!=y),int(z!=y)) for y,x,z in zip(truth,before,after,strict=True))
            results[kind]["scopes"][scope]=dict(
                individual=stats([dict(actual=y,predicted=p) for y,p in zip(truth,before,strict=True)]),
                unified=stats([dict(actual=y,predicted=p) for y,p in zip(truth,after,strict=True)]),
                fixed_defect_miss=compare[(1,1,0)],new_defect_miss=compare[(1,0,1)],
                fixed_false_alarm=compare[(0,1,0)],new_false_alarm=compare[(0,0,1)])
    pooled={}
    for scope in ("primary","sensitivity"):
        pooled[scope]={}
        for mode in ("individual","unified"):
            fields=("tp","tn","fp","fn")
            tp,tn,fp,fn=(sum(r["scopes"][scope][mode][key] for r in results.values()) for key in fields)
            pooled[scope][mode]=dict(tp=tp,tn=tn,fp=fp,fn=fn,n=tp+tn+fp+fn,
                                      f1=2*tp/(2*tp+fp+fn),accuracy=(tp+tn)/(tp+tn+fp+fn))
    summary=dict(checkpoint_sha256=sha(checkpoint),epoch=int(best["epoch"]),model_selection=best,
                 score_cutoff=.5,device="DGX CPU FP32 batch 8",per_type=results,pooled=pooled,
                 cross_type_identical_display_groups=len(overlap),
                 pooled_unit="type-labeled photos; cross-type identity is not used for a joint defect claim",
                 calibration_ready=False,autopass_ready=False)
    save(out/"comparison_report.json",summary)
    print("COWL_UNIFIED_COMPARISON_COMPLETE",flush=True)


if __name__=="__main__":
    main(Path(sys.argv[1]).resolve(strict=True))
