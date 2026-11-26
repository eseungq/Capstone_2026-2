"""Evaluate the frozen e08 checkpoint once and compare nested Validation scopes."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import torch
from torchvision.transforms import functional as TF
from frame_model.check import read_image


FULL_SHA = "33300dbaae7c7f1897a68be622abb6d2e75c762475fd8a0d54818de25942f00f"
JET_SERVER = "outputs/frame_test_api_jet_20261108.0mqEHz"
RUN = "outputs/frame_training/comparison_train_20261022T160533_169658Z/unified"


def load(path):
    raw = path.read_bytes()
    return [json.loads(line) for line in raw.splitlines()], hashlib.sha256(raw).hexdigest()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def counts(rows):
    matrix = Counter((row["actual"], row["prediction"]) for row in rows)
    tn, fp, fn, tp = (matrix[0, 0], matrix[0, 1], matrix[1, 0], matrix[1, 1])
    divide = lambda n, d: n / d if d else None
    return dict(total=len(rows), good=tn + fp, defect=tp + fn,
                tp=tp, tn=tn, fp=fp, fn=fn, accuracy=divide(tp + tn, len(rows)),
                precision=divide(tp, tp + fp), recall=divide(tp, tp + fn),
                falseNegativeRate=divide(fn, tp + fn), falsePositiveRate=divide(fp, tn + fp),
                f1=divide(2 * tp, 2 * tp + fp + fn))


def report(rows):
    return dict(overall=counts(rows), byType={kind: counts([r for r in rows if r["type"] == kind])
                                             for kind in sorted({r["type"] for r in rows})})


def main(project, full_path, subset_path, output):
    start = time.monotonic()
    full, full_hash = load(full_path)
    subset, subset_hash = load(subset_path)
    full_by_id = {row["imageSHA256"]: row for row in full}
    subset_ids = {row["imageSHA256"] for row in subset}
    if full_hash != FULL_SHA or len(full) != len(full_by_id) or len(full) != 3241:
        raise ValueError("Main evaluation set differs from the frozen reviewed manifest")
    if len(subset) != len(subset_ids) or len(subset) != 1535 or not subset_ids.issubset(full_by_id):
        raise ValueError("Conservative set is not an exact subset")
    for row in subset:
        original = full_by_id[row["imageSHA256"]]
        if any(original[key] != row[key] for key in (
            "imageArchive", "imageMember", "offset", "size", "labelSHA256", "quality", "defectType"
        )):
            raise ValueError("Conservative sample metadata differs")
    expected = {0: 1439, 1: 1802}
    mapping = {"양품": 0, "불량품": 1}
    if Counter(mapping[row["quality"]] for row in full) != expected:
        raise ValueError("Unexpected full class counts")
    if Counter(mapping[row["quality"]] for row in subset) != {0: 396, 1: 1139}:
        raise ValueError("Unexpected conservative class counts")

    sys.path.insert(0, str(project / JET_SERVER))
    from frame_unified_test_api_20261107 import FRAME_SHA256, MODEL_VERSION, create_engine

    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    engine = create_engine(project)
    config = json.loads((project / RUN / "run_config.json").read_text())["config"]
    if config["image_size"] != 224 or config["prediction_cutoff"] != .5:
        raise ValueError("Unapproved preprocessing or decision threshold")
    def tensor(row):
        image = dict(image_archive=row["imageArchive"], offset=row["offset"], size=row["size"],
                     image_sha256=row["imageSHA256"], image_id=row["imageSHA256"])
        _, padded = read_image(image)
        return TF.normalize(TF.to_tensor(padded), config["mean"], config["std"])

    records = []
    batch_size = 8
    ordered = sorted(full, key=lambda row: (row["imageArchive"], row["offset"]))
    print("Starting GPU FP32 evaluation:", MODEL_VERSION, len(ordered), flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool, (output / "predictions.jsonl").open("x", encoding="utf-8") as stream:
        for start_index in range(0, len(ordered), batch_size):
            rows = ordered[start_index:start_index + batch_size]
            batch = torch.stack(list(pool.map(tensor, rows))).cuda()
            with torch.inference_mode():
                logits = engine.model(batch)
                scores = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()
            if len(scores) != len(rows) or not all(math.isfinite(score) and 0 <= score <= 1 for score in scores):
                raise ValueError("Invalid inference output")
            for row, score in zip(rows, scores):
                record = dict(id=row["imageSHA256"], type=row["defectType"], actual=mapping[row["quality"]],
                              prediction=int(score >= .5), rawDefectScore=score,
                              conservative=row["imageSHA256"] in subset_ids)
                records.append(record)
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            if len(records) % 400 == 0 or len(records) == len(full):
                stream.flush()
                print("Scored", len(records), "/", len(full), flush=True)
    if digest(engine.checkpoint_path) != FRAME_SHA256 or digest(full_path) != full_hash or digest(subset_path) != subset_hash:
        raise RuntimeError("Frozen inputs changed during evaluation")
    retained = [row for row in records if row["conservative"]]
    removed = [row for row in records if not row["conservative"]]
    result = dict(modelVersion=MODEL_VERSION, checkpointSHA256=FRAME_SHA256,
                  modelInput=224, rawDefectCutoff=.5, batchSize=batch_size, device=engine.metadata["gpu"],
                  runtimeVersions=engine.metadata["versions"], mainManifestSHA256=full_hash,
                  conservativeManifestSHA256=subset_hash, elapsedSeconds=time.monotonic() - start,
                  scope="Frozen e08. One offline FP32 GPU pass over photo-level FRAME Validation.",
                  main=report(records), conservative=report(retained), excludedByConservativeScreen=report(removed),
                  predictionsSHA256=digest(output / "predictions.jsonl"))
    with (output / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print("Evaluation complete", flush=True)


if __name__ == "__main__":
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
