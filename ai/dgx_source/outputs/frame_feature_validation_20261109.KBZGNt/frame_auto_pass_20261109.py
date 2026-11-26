"""Fit and freeze a FRAME-specific offline policy before evaluating it."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import torch
from torchvision.transforms import functional as TF

from frame_model.check import read_image


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def score(model, config, rows, output, name):
    def tensor(row):
        _, padded = read_image(row)
        return TF.normalize(TF.to_tensor(padded), config["mean"], config["std"])

    rows = sorted(rows, key=lambda row: (row["image_archive"], int(row["offset"])))
    records = []
    with ThreadPoolExecutor(max_workers=3) as pool, (output / f"{name}_scores.jsonl").open("x", encoding="utf-8") as stream:
        for start in range(0, len(rows), 8):
            batch = rows[start:start+8]
            pixels = torch.stack(list(pool.map(tensor, batch))).cuda()
            with torch.inference_mode():
                logits = model(pixels)
                margins = (logits[:, 1] - logits[:, 0]).cpu().tolist()
                raw = logits.softmax(dim=1)[:, 1].cpu().tolist()
            for row, margin, prob in zip(batch, margins, raw):
                if not math.isfinite(margin) or not math.isfinite(prob):
                    raise ValueError("Invalid inference output")
                record = dict(imageSHA256=row["image_sha256"], label=int(row["class_id"]),
                              defectType=row["defect_type"], groupId=row.get("group_id"),
                              margin=margin, rawScore=prob, goodPrediction=prob < .5)
                records.append(record)
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            if len(records) % 400 == 0 or len(records) == len(rows):
                stream.flush()
                print(name, len(records), "/", len(rows), flush=True)
    return records


def probability(margin, temperature):
    z = margin / temperature
    e = math.exp(-abs(z))
    return 1 / (1 + e) if z >= 0 else e / (1 + e)


def nll(rows, temperature):
    return float(np.mean(np.logaddexp(0, [(1 - 2*r["label"])*r["margin"]/temperature for r in rows])))


def metrics(rows, temperature, threshold):
    counts = Counter()
    for row in rows:
        counts["defect" if row["label"] else "good"] += 1
        passed = (threshold is not None and row["goodPrediction"]
                  and probability(row["margin"], temperature) <= threshold)
        if passed:
            counts["defectAutoPass" if row["label"] else "goodAutoPass"] += 1
    def brier(t):
        return sum((probability(row["margin"], t)-row["label"])**2 for row in rows) / len(rows)
    return dict(total=len(rows), good=counts["good"], defect=counts["defect"], goodAutoPass=counts["goodAutoPass"],
                defectAutoPass=counts["defectAutoPass"], rawNLL=nll(rows, 1), calibratedNLL=nll(rows, temperature),
                rawBrier=brier(1), calibratedBrier=brier(temperature))


def main(root, out):
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    sys.path.insert(0, str(root / "outputs/frame_test_api_jet_20261108.0mqEHz"))
    from frame_unified_test_api_20261107 import FRAME_SHA256, MODEL_VERSION, create_engine
    run = root / "outputs/frame_training/comparison_train_20261022T160533_169658Z/unified"
    config = json.loads((run / "run_config.json").read_text())["config"]
    artifacts = json.loads((run / "artifacts.json").read_text())
    sets, hashes, used_ids, used_groups = {}, {}, set(), set()
    for role in ("train", "model_selection", "calibration_fit", "policy_development"):
        if role in ("train", "model_selection"):
            path = run / f"{role}_used.csv"
            expected = artifacts[path.name]
        else:
            item = config["manifests"][role]
            path, expected = Path(item["path"]), item["sha256"]
        hashes[role] = digest(path)
        if hashes[role] != expected:
            raise ValueError(f"Frozen source manifest mismatch for {role}")
        with path.open(newline="", encoding="utf-8-sig") as stream:
            data = list(csv.DictReader(stream))
        ids, groups = {r["image_sha256"] for r in data}, {r["group_id"] for r in data}
        if len(ids) != len(data) or ids & used_ids or groups & used_groups or "" in groups:
            raise ValueError(f"Known image or proposed group overlap for {role}")
        used_ids.update(ids)
        used_groups.update(groups)
        sets[role] = data
    final_path = root / "outputs/frame_validation_review_closed_20261108.ROVWqL/evaluation_confirmed_duplicates_excluded.jsonl"
    final_hash = digest(final_path)
    if final_hash != "33300dbaae7c7f1897a68be622abb6d2e75c762475fd8a0d54818de25942f00f":
        raise ValueError("Frozen final photo manifest differs")
    print("Manifest roles verified:", {role: len(data) for role, data in sets.items()}, flush=True)
    engine = create_engine(root)
    calibration = score(engine.model, config, sets["calibration_fit"], out, "calibration")
    temperature = min(np.geomspace(.1, 10, 201).tolist(), key=lambda value: nll(calibration, value))
    development = score(engine.model, config, sets["policy_development"], out, "policy_development")
    defect = [probability(r["margin"], temperature) for r in development if r["label"] and r["goodPrediction"]]
    normal = [probability(r["margin"], temperature) for r in development if not r["label"] and r["goodPrediction"]]
    ceiling = min(defect, default=math.inf)
    threshold = max((value for value in normal if value < ceiling), default=None)
    policy = dict(scope="offline candidate only", modelVersion=MODEL_VERSION, checkpointSHA256=FRAME_SHA256,
                  temperature=temperature, passThreshold=threshold, rawGoodGate=0.5,
                  ready=False, active=False, manifestHashes=hashes, finalManifestSHA256=final_hash,
                  selection="Fit temperature on reserved calibration; largest observed normal score below every eligible defective score on reserved policy development.",
                  development=metrics(development, temperature, threshold))
    assert policy["development"]["defectAutoPass"] == 0
    policy_path = out / "frozen_candidate.json"
    dump(policy_path, policy)
    policy_sha = digest(policy_path)
    print("FRAME policy frozen:", policy_sha, "threshold", threshold, flush=True)
    final_source = [json.loads(line) for line in final_path.read_text().splitlines()]
    if len(final_source) != 3241 or used_ids & {row["imageSHA256"] for row in final_source}:
        raise ValueError("Final set has known cross-role exact overlap")
    final = [dict(image_archive=row["imageArchive"], offset=row["offset"], size=row["size"],
                  image_sha256=row["imageSHA256"], image_id=row["imageSHA256"],
                  class_id=int(row["quality"] == "불량품"), defect_type=row["defectType"]) for row in final_source]
    final_scores = score(engine.model, config, final, out, "final")
    if digest(policy_path) != policy_sha:
        raise ValueError("Policy changed during final scoring")
    conservative_path = root / "outputs/frame_validation_audit_20261108.AuDWbR/eligible_cross_and_internal_conservative.jsonl"
    conservative_ids = {row["imageSHA256"] for row in map(json.loads, conservative_path.read_text().splitlines())}
    conservative = [row for row in final_scores if row["imageSHA256"] in conservative_ids]
    if len(conservative) != 1535:
        raise ValueError("Conservative manifest differs")
    report = dict(policy=policy, policySHA256=policy_sha, calibration=metrics(calibration, temperature, threshold),
                  final=metrics(final_scores, temperature, threshold),
                  conservative=metrics(conservative, temperature, threshold),
                  finalByType={kind: metrics([r for r in final_scores if r["defectType"] == kind],
                                             temperature, threshold)
                               for kind in config["inspection_types"]},
                  limits=["Photo-level counts; physical IDs are unavailable.",
                          "Final photos were previously scored for classification; the AUTO_PASS candidate was frozen using only the reserved roles.",
                          "Training-derived group IDs are capture heuristics.",
                          "Conservative visual screen covers training and model selection; reserved roles were checked for exact bytes.",
                          "Offline batch scoring; verify serving parity and activation separately."])
    dump(out / "report.json", report)
    print("AUTO_PASS offline evaluation complete", flush=True)


if __name__ == "__main__":
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
