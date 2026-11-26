"""Fit and freeze the unified cowl policy before checking held-out scores."""

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import expit
import torch

from cowl_unified_training import TYPES, check, load, save, sha
from cowl_unified_trial_api import MODEL_SHA, VERSION, load_model
from evaluate_cowl_pin_policy import bounds, extract, metrics
from evaluate_cowl_unified import LINK, PIN, read_csv, reference
from torchvision.transforms import functional as TF
from types import SimpleNamespace


TYPE_KEYS = dict(zip(TYPES, ("fixed_pin", "linkage"), strict=True))
DEV_ROLES = ("calibration_fit", "policy_development")
GRID_SCALE = 10_000


def enrich(scores, manifest, kind=None):
    scores_by_id = {r["image_id"]: r for r in scores}
    assert len(scores_by_id) == len(scores) == len(manifest)
    result = []
    for source in manifest:
        row = scores_by_id[source["image_id"]]
        assert row["image_sha256"] == source["image_sha256"]
        assert str(row["label"]) == source["class_id"] and row["group_id"] == source["group_id"]
        result.append(dict(row, kind=kind or TYPE_KEYS[source["defect_type"]],
                           label=int(row["label"]), prediction=int(row["prediction"]),
                           margin=float(row["margin"]), raw_score=float(row["raw_score"]),
                           display_sha256=source.get("display_sha256", source["image_sha256"]),
                           cross_near=source.get("cross_near", False)))
    return result


def arrays(rows):
    x = np.array([r["margin"] for r in rows])
    y = np.array([r["label"] for r in rows])
    good = np.array([r["prediction"] == 0 for r in rows])
    assert np.isfinite(x).all()
    return x, y, good


def scopes(rows):
    return {"pooled": rows, **{k: [r for r in rows if r["kind"] == k] for k in TYPE_KEYS.values()}}


def counts(rows, temperature, threshold):
    x, y, good = arrays(rows)
    p = expit(x / temperature)
    passed = good & (p <= threshold)
    bad = [r for r, flag in zip(rows, passed & (y == 1), strict=True) if flag]
    normal_count, defect_count = int((y == 0).sum()), int((y == 1).sum())
    normal_pass = int((passed & (y == 0)).sum())
    first_bad = p[good & (y == 1)]
    return dict(normal_count=normal_count, defect_count=defect_count,
                unique_defect_pixels=len({r["display_sha256"] for r in rows if r["label"] == 1}),
                normal_autopass=normal_pass, defect_autopass=len(bad), review=len(rows) - int(passed.sum()),
                normal_autopass_rate=normal_pass / normal_count,
                defect_autopass_rate=len(bad) / defect_count,
                photo_upper95_if_independent=bounds(len(bad), defect_count),
                first_bad_score_exclusive=float(first_bad.min()) if first_bad.size else None,
                bad_ids=[dict(image_id=r["image_id"], kind=r["kind"],
                              probability=float(expit(r["margin"] / temperature))) for r in bad])


def develop(stage, out):
    config, tables, _ = check(stage)
    run = stage / "runs/train"
    model, verified = load_model(run)
    assert verified == config and sha(run / "best.pt") == MODEL_SHA
    engine = SimpleNamespace(model=model, config=config)
    recorded = run / "best_model_selection_predictions.csv"
    assert sha(recorded) == load(run / "artifacts.json")[recorded.name]
    reference_rows = {r["image_id"]: r for r in read_csv(recorded)}
    assert reference_rows.keys() == {r["image_id"] for r in tables["model_selection"]}
    near = sorted(tables["model_selection"],
                  key=lambda r: abs(float(reference_rows[r["image_id"]]["raw_defect_score"]) - .5))[:16]
    near_ids = {r["image_id"] for r in near}
    other = sorted((r for r in tables["model_selection"] if r["image_id"] not in near_ids),
                   key=lambda r: r["image_sha256"])[:48]
    sample = extract(engine, near + other, out / "cpu_batch1_parity.csv", batch_size=1)
    batched = extract(engine, near + other, out / "cpu_batch8_parity.csv")
    mismatches = sum(r["prediction"] != int(reference_rows[r["image_id"]]["predicted"]) for r in sample)
    delta = max(abs(r["raw_score"] - float(reference_rows[r["image_id"]]["raw_defect_score"])) for r in sample)
    cpu_delta = max(abs(a["raw_score"] - b["raw_score"]) for a, b in zip(sample, batched, strict=True))
    assert all(a["prediction"] == b["prediction"] for a, b in zip(sample, batched, strict=True))
    assert cpu_delta <= .002, cpu_delta
    from cowl_unified_trial_api import LinkageEngine
    from frame_model.check import read_image
    from io import BytesIO
    from PIL import Image, ImageOps
    import os
    for row in (near[0], other[0]):
        with Path(row["image_archive"]).open("rb") as archive:
            blob = os.pread(archive.fileno(), int(row["size"]), int(row["offset"]))
        with Image.open(BytesIO(blob)) as image:
            api_pixels = LinkageEngine.tensor(engine, ImageOps.exif_transpose(image).convert("RGB"))
        evaluation_pixels = TF.normalize(TF.to_tensor(read_image(row)[1]), config["mean"], config["std"])
        assert torch.equal(api_pixels[0], evaluation_pixels), row["image_id"]
    print("PARITY", dict(cpu_batch1_vs_batch8=cpu_delta, cpu_vs_gpu=delta, gpu_mismatches=mismatches), flush=True)

    roles = {}
    used_ids = {r["image_id"] for role in ("train", "model_selection") for r in tables[role]}
    used_groups = {r["group_id"] for role in ("train", "model_selection") for r in tables[role]}
    for role in DEV_ROLES:
        source = config["manifests"][role]
        assert sha(source["path"]) == source["sha256"]
        reserved = read_csv(Path(source["path"]))
        ids = {r["image_id"] for r in reserved}
        groups = {r["group_id"] for r in reserved}
        assert len(reserved) == len(ids) == config["roles"][role]
        assert not (used_ids & ids or used_groups & groups)
        used_ids.update(ids)
        used_groups.update(groups)
        roles[role] = enrich(extract(engine, reserved, out / f"{role}_scores.csv", batch_size=1), reserved)
    fit_x, fit_y, _ = arrays(roles["calibration_fit"])

    def objective(log_temperature):
        z = fit_x / np.exp(log_temperature)
        return float(np.mean(np.logaddexp(0, z) - fit_y * z))

    fit = minimize_scalar(objective, bounds=(-4, 4), method="bounded", options={"xatol": 1e-10})
    assert fit.success and -3.99 < fit.x < 3.99
    temperature = float(np.exp(fit.x))
    comparison = {}
    for role, rows in roles.items():
        comparison[role] = {}
        for name, scoped in scopes(rows).items():
            x, y, _ = arrays(scoped)
            comparison[role][name] = dict(raw=metrics(x, y, 1), calibrated=metrics(x, y, temperature),
                                          normal_count=int((y == 0).sum()), defect_count=int((y == 1).sum()))
    pooled = comparison["policy_development"]["pooled"]
    improves = all(pooled["calibrated"][k] < pooled["raw"][k] for k in ("nll", "brier"))
    rows = roles["policy_development"]
    x, y, good = arrays(rows)
    p = expit(x / temperature)
    defects = p[(y == 1) & good]
    safe_normals = np.sort(p[(y == 0) & good])
    grid = np.arange(1, GRID_SCALE // 2) / GRID_SCALE
    safe_grid = grid[grid < defects.min()] if defects.size else grid
    # Maximize observed GOOD coverage with zero bad passes, then take the smallest tied grid value.
    coverage = np.searchsorted(safe_normals, safe_grid, side="right")
    threshold = float(safe_grid[np.argmax(coverage)]) if improves and coverage.size and coverage.max() else None
    frozen = dict(model_version=VERSION, checkpoint_sha256=MODEL_SHA,
                  temperature=temperature, calibration_gate_passed=improves, threshold=threshold,
                  selection_rule="pooled development NLL and Brier improve; maximum normal coverage at zero defect passes; lowest tied threshold on grid 0.0001 to 0.4999; prediction must be GOOD",
                  heldout_scores_read=False, policy_activated=False, runtime="DGX CPU FP32 batch 1")
    development = dict(calibration=comparison, cpu_parity=dict(photos=len(sample), mismatches=mismatches,
                       max_abs_raw_error=delta, cpu_batch1_vs_batch8_max_abs_error=cpu_delta,
                       gpu_reference_tolerance=.002, gpu_reference_passed=mismatches == 0 and delta <= .002,
                       exact_api_preprocessing_samples=2),
                       scores_sha256={role: sha(out / f"{role}_scores.csv") for role in DEV_ROLES},
                       manifest_sha256={role: config["manifests"][role]["sha256"] for role in DEV_ROLES},
                       first_bad_score_exclusive=float(defects.min()) if defects.size else None,
                       candidate={k: counts(v, temperature, threshold) for k, v in scopes(rows).items()}
                       if threshold is not None else None)
    save(out / "development.json", development)
    save(out / "frozen_candidate.json", frozen)


def verify(stage, out):
    frozen_path = out / "frozen_candidate.json"
    frozen = load(frozen_path)
    assert frozen["checkpoint_sha256"] == MODEL_SHA and frozen["model_version"] == VERSION
    assert frozen["heldout_scores_read"] is False
    threshold, temperature = frozen["threshold"], frozen["temperature"]
    report = dict(model_version=VERSION, candidate=frozen, candidate_sha256=sha(frozen_path),
                  production_policy_activated=False, validated_min=None, validated_max=None,
                  limits=["Photo-level evaluation; repeated views and physical independence not verified.",
                          "Dataset has no joint two-defect or fully inspected two-area normal labels.",
                          "Official scores previously used for classification comparison; this frozen policy did not use them for fitting or selection."])
    if threshold is not None:
        evaluation = stage / "official_evaluation"
        comparison = load(evaluation / "comparison_report.json")
        assert comparison["checkpoint_sha256"] == MODEL_SHA
        preflight = load(stage / "preflight.json")
        for audit in (Path(PIN[1]) / "official_policy_report.json",
                      Path(LINK[1]) / "linkage_validation_overlap_summary.json"):
            assert load(audit)["training_fingerprints_sha256"] == preflight["similarity_fingerprints_sha256"]
        model, config = load_model(stage / "runs/train")
        engine = SimpleNamespace(model=model, config=config)
        all_rows, sources = [], {}
        for kind, locations in (("fixed_pin", PIN), ("linkage", LINK)):
            manifest, _, _ = reference(kind, locations)
            path = evaluation / f"{kind}_scores.csv"
            assert sha(path) == comparison["per_type"][kind]["unified_scores_sha256"]
            rows = sorted(manifest.values(), key=lambda r: r["offset"])
            scored = out / f"{kind}_heldout_scores.csv"
            all_rows.extend(enrich(extract(engine, rows, scored, batch_size=1), rows, kind))
            sources[kind] = dict(scores_sha256=sha(scored), comparison_scores_sha256=sha(path))
        report["heldout_sources"] = sources
        for field, rows in (("exact_clean", all_rows), ("near_excluded", [r for r in all_rows if not r["cross_near"]])):
            report[field] = {name: counts(scoped, temperature, threshold) for name, scoped in scopes(rows).items()}
        report["zero_bad_observed"] = report["exact_clean"]["pooled"]["defect_autopass"] == 0
    save(out / "heldout_policy_report.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("develop", "verify"))
    parser.add_argument("stage", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    (develop if args.phase == "develop" else verify)(args.stage.resolve(strict=True), args.out.resolve(strict=True))
