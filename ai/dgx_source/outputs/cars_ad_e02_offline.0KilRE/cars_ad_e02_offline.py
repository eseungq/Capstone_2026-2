"""Score the development set, freeze an offline policy, then evaluate the holdout."""

from collections import Counter, defaultdict
import importlib.metadata
import json
import math
from pathlib import Path
import sys

import numpy as np
import torch

from cars_ad_e02_pilot import (
    EXPECTED_SHA256, EXPECTED_VERSION, load_engine, scores, sha, validate_candidate,
    weight_digest,
)


def save(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def grouped(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row)
    return groups.values()


def sigmoid(margin):
    exponent = math.exp(-abs(margin))
    return 1 / (1 + exponent) if margin >= 0 else exponent / (1 + exponent)


def probability(row, temperature):
    return sigmoid(row["margin"] / temperature)


def nll(rows, temperature):
    # Each photo group contributes one unit of weight.
    group_losses = []
    for group in grouped(rows):
        losses = [np.logaddexp(0, (-1 if row["decision"] == "DEFECT_DOOR" else 1)
                              * row["margin"] / temperature) for row in group]
        group_losses.append(float(np.mean(losses)))
    return float(np.mean(group_losses))


def choose_policy(rows, split_hash, development_hash):
    # Temperature fit is limited to the development split and the fixed candidate grid.
    temperature = min(np.geomspace(0.1, 10, 201).tolist(), key=lambda t: nll(rows, t))
    defective = [probability(row, temperature) for row in rows
                 if row["decision"] == "DEFECT_DOOR" and row["prediction"] == "GOOD"]
    ceiling = min(defective, default=math.inf)
    normal = [max(probability(row, temperature) for row in group)
              for group in grouped(rows)
              if group[0]["decision"] == "GOOD_DOOR"
              and all(row["prediction"] == "GOOD" for row in group)]
    threshold = max((value for value in normal if value < ceiling), default=None)
    return dict(scope="offline_research", ready=False, active=False,
                modelVersion=EXPECTED_VERSION, checkpointSHA256=EXPECTED_SHA256,
                splitSHA256=split_hash, developmentScoresSHA256=development_hash,
                temperature=temperature, passThreshold=threshold, rawDefectCutoff=0.5,
                developmentLowestDefectiveEligibleScore=min(defective, default=None),
                thresholdRule="Maximize complete normal-group passes with zero defective-group passes on development")


def evaluate(rows, policy):
    threshold, temperature = policy["passThreshold"], policy["temperature"]
    for row in rows:
        row["experimentalDefectProbability"] = probability(row, temperature)
        row["simulatedAutoPass"] = (threshold is not None and row["prediction"] == "GOOD"
                                    and row["experimentalDefectProbability"] <= threshold)
    photos = Counter()
    groups = Counter()
    for group in grouped(rows):
        label = group[0]["decision"]
        passes = [row["simulatedAutoPass"] for row in group]
        photos[label] += len(group)
        photos[f"{label}_PASS"] += sum(passes)
        groups[label] += 1
        groups[f"{label}_PASS"] += any(passes) if label == "DEFECT_DOOR" else all(passes)
    confusion = Counter(f"{row['decision']}__{row['prediction']}" for row in rows)
    return dict(photos=dict(photos), groups=dict(groups), classification=dict(confusion),
                rawNLL=nll(rows, 1.0), calibratedNLL=nll(rows, temperature),
                rawBrier=brier(rows, 1.0), calibratedBrier=brier(rows, temperature),
                rows=rows)


def brier(rows, temperature):
    losses = [np.mean([(probability(row, temperature) - (row["decision"] == "DEFECT_DOOR")) ** 2
                       for row in group]) for group in grouped(rows)]
    return float(np.mean(losses))


def score_partition(engine, bundle, rows):
    results = []
    for index, row in enumerate(rows, 1):
        image = bundle / row["image"]
        if sha(image) != row["sha256"]:
            raise ValueError(f"Hash mismatch for {row['id']}")
        result = scores(engine.model, engine.tensor(image).unsqueeze(0))
        if not all(math.isfinite(value) for value in result.values()):
            raise ValueError(f"Nonfinite output for {row['id']}")
        results.append(dict(row, **result, prediction="DEFECT" if result["probability"] >= 0.5 else "GOOD"))
        if index % 25 == 0 or index == len(rows):
            print(f"Scored {index}/{len(rows)}", flush=True)
    return results


def main(bundle):
    if torch.cuda.is_available():
        raise RuntimeError("CUDA must be disabled for the offline CPU study")
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    model_manifest, run, config = validate_candidate()
    if (model_manifest["modelVersion"], model_manifest["checkpointSHA256"]) != (
        EXPECTED_VERSION, EXPECTED_SHA256
    ) or sha(run / "best.pt") != EXPECTED_SHA256:
        raise ValueError("Unexpected e02 model identity")
    engine = load_engine(model_manifest, run, config)
    weight_before = weight_digest(engine.model)
    fixtures = []
    for index, expected in zip((0, 1, 3), (0.010911530815064907, 0.012285854667425156,
                                            0.9999741315841675)):
        image = Path(model_manifest["samples"][index]["image_path"])
        actual = scores(engine.model, engine.tensor(image).unsqueeze(0))["probability"]
        difference = abs(actual - expected)
        if difference > 1e-5 or (actual >= 0.5) != (expected >= 0.5):
            raise ValueError(f"CPU and previous GPU disagree on reference sample {index}")
        fixtures.append(dict(index=index, gpuReference=expected, cpuScore=actual, absoluteDifference=difference))
    split_path = bundle / "split_manifest.json"
    split_hash = sha(split_path)
    partitions = json.loads(split_path.read_text(encoding="utf-8"))["partitions"]
    print("Scoring development photos", flush=True)
    development = score_partition(engine, bundle, partitions["development"])
    development_path = bundle / "development_scores.json"
    save(development_path, development)
    policy_path = bundle / "frozen_policy.json"
    policy = choose_policy(development, split_hash, sha(development_path))
    save(policy_path, policy)
    policy_hash = sha(policy_path)
    print(f"Policy frozen: {policy_hash}", flush=True)

    print("Scoring held-out photos", flush=True)
    final = score_partition(engine, bundle, partitions["final"])
    if (weight_digest(engine.model) != weight_before or sha(run / "best.pt") != EXPECTED_SHA256
            or sha(split_path) != split_hash or sha(policy_path) != policy_hash):
        raise RuntimeError("Frozen input changed")
    save(bundle / "report.json", dict(
        device="DGX CPU", modelStateUnchanged=True, gpuFixtureComparison=fixtures,
        runtimeVersions={name: importlib.metadata.version(name) for name in config["versions"]},
        recordedTrainingVersions=config["versions"], policySHA256=policy_hash, policy=policy,
        development=evaluate(development, policy), final=evaluate(final, policy)))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
