"""Evaluate the frozen 9-epoch linkage model once on the audited Validation photos."""

import csv
import importlib.metadata
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import timm
import torch

from cowl_pin_trial_api import read_csv, sha, write_json
from evaluate_cowl_pin_policy import extract
from frame_model.cam_review import verify_metadata
from frame_model.train import metrics


MODEL_SHA = "af324ae8956197a042f11cb0b1ee65b114919d4ea1bb75a1d6d6cc14b77b06c3"
CONFIG_SHA = "c3bb63166f0e99cd596db2c01feafcae6d4955631665e75728f97b32cdd1d178"
MANIFEST_SHA = "2acfa732cdc4f636bcc392d963592f134f8e86cac7187cb17ed4d871dfa571f6"


def score_metrics(rows):
    result = metrics([{**r, "actual":r["label"], "predicted":r["prediction"]} for r in rows])
    result["defect_recall"] = result["tp"]/(result["tp"]+result["fn"])
    return result


def main(run, audit, out):
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    checkpoint_path, config_path = run/"best.pt", run/"run_config.json"
    manifest_path = audit/"frozen_evaluation_manifest.json"
    assert (sha(checkpoint_path), sha(config_path), sha(manifest_path)) == (MODEL_SHA, CONFIG_SHA, MANIFEST_SHA)
    recorded = json.loads(config_path.read_bytes())
    config = recorded["config"]
    assert config["inspection_types"] == ["연계 불량"]
    assert (config["image_size"], config["prediction_cutoff"], config["class_mapping"]) == (
        224, .5, {"GOOD":0,"DEFECT":1})
    with torch.serialization.safe_globals([np._core.multiarray._reconstruct, np.ndarray, np.dtype, np.dtypes.UInt32DType]):
        ck = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    assert ck["epoch"] == 9
    verify_metadata(ck["metadata"], recorded)
    model = timm.create_model(config["model_name"], pretrained=False, num_classes=2)
    model.load_state_dict(ck["model_state_dict"], strict=True)
    del ck
    model.eval()
    engine = SimpleNamespace(model=model, config=config)

    manifest = json.loads(manifest_path.read_bytes())
    assert len(manifest) == 1254 and len({r["image_id"] for r in manifest}) == 1254
    selected = [r for r in manifest if r["excluded"] is None]
    strict_ids = {r["image_id"] for r in selected if not r["cross_near"]}
    assert (len(selected),len(strict_ids)) == (1237,1053)
    assert len({r["image_sha256"] for r in selected}) == len(selected)
    assert [sum(r["class_id"]=="0" and (not strict or r["image_id"] in strict_ids) for r in selected)
            for strict in (False,True)] == [606,530]

    artifacts = json.loads((run/"artifacts.json").read_bytes())
    for name in ("model_selection_used.csv","best_model_selection_predictions.csv"):
        assert sha(run/name) == artifacts[name]
    selection = read_csv(run/"model_selection_used.csv")
    gpu = {r["image_id"]:r for r in read_csv(run/"best_model_selection_predictions.csv")}
    assert len(gpu) == len(selection) == 989 and all(r["class_id"] == gpu[r["image_id"]]["actual"] for r in selection)
    assert not {r["image_sha256"] for r in selection} & {r["image_sha256"] for r in selected}
    near = sorted(selection, key=lambda r:abs(float(gpu[r["image_id"]]["raw_defect_score"])-.5))[:16]
    near_ids = {r["image_id"] for r in near}
    random_sample = sorted((r for r in selection if r["image_id"] not in near_ids), key=lambda r:r["image_sha256"])[:48]
    checks = extract(engine, near+random_sample,out/"cpu_parity.csv")
    parity = dict(count=len(checks), near_cutoff_count=len(near),
                  mismatches=[r["image_id"] for r in checks if r["prediction"] != int(gpu[r["image_id"]]["predicted"])],
                  max_abs_raw_error=max(abs(r["raw_score"]-float(gpu[r["image_id"]]["raw_defect_score"])) for r in checks))
    print("CPU_PARITY",json.dumps(parity),flush=True)

    scores = extract(engine,sorted(selected,key=lambda r:r["offset"]),out/"official_scores.csv")
    assert sha(manifest_path) == MANIFEST_SHA
    by_set = {"primary":scores,"sensitivity":[r for r in scores if r["image_id"] in strict_ids],
              "cross_near_only":[r for r in scores if r["image_id"] not in strict_ids]}
    summary = {k:score_metrics(rows) for k,rows in by_set.items()}
    for key in ("tp","tn","fp","fn"):
        assert summary["primary"][key] == summary["sensitivity"][key]+summary["cross_near_only"][key]
    with (out/"official_errors.csv").open("x",encoding="utf-8-sig",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=["image_id","label","prediction","raw_score","cross_near"])
        writer.writeheader()
        for r in scores:
            if r["label"] != r["prediction"]:
                writer.writerow({k:r[k] for k in ("image_id","label","prediction","raw_score")}
                                | {"cross_near":r["image_id"] not in strict_ids})
    report = dict(epoch=9, checkpoint_sha256=MODEL_SHA, training_config_sha256=CONFIG_SHA,
                  evaluation_manifest_sha256=MANIFEST_SHA, threshold=.5, temperature_applied=False,
                  mode="DGX CPU FP32 batch 8", cpu_parity=parity,
                  versions={k:importlib.metadata.version(k) for k in ("torch","torchvision","timm","Pillow","numpy")},
                  metrics=summary, official_scores_sha256=sha(out/"official_scores.csv"),
                  error_list_sha256=sha(out/"official_errors.csv"),
                  limitations=["Classification uses the source photo label, not a physical assembly identity.",
                               "Similarity candidates are not confirmed duplicates.",
                               "The 0.5 cutoff is classification only, not an AUTO_PASS threshold."])
    write_json(out/"evaluation_report.json",report)
    print("LINKAGE_OFFICIAL_COMPLETE",json.dumps(summary),flush=True)


if __name__ == "__main__":
    main(*(Path(x).resolve(strict=True) for x in sys.argv[1:]))
