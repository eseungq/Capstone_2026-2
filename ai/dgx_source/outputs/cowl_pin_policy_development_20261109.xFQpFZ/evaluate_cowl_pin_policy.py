"""Fit a temperature and compare fixed-pin AUTO_PASS candidates offline."""

import csv
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import expit
from scipy.stats import beta
import torch
from torchvision.transforms import functional as TF

from cowl_pin_trial_api import EXPECTED, ROOT, RUN, VERSION, PinEngine, read_csv, sha, write_json
from frame_model.check import read_image


PREP = ROOT / "outputs/cowl_pin_training_12e_20261109.Vj4ZcV"
GRID = (0, .001, .005, .01, .02, .05, .10, .15, .20, .25, .28, .30, .35, .3752, .40, .45, .4999)


def extract(engine, rows, output, batch_size=8):
    started = time.monotonic()
    result = []
    with torch.inference_mode():
        for offset in range(0, len(rows), batch_size):
            batch = rows[offset:offset + batch_size]
            pixels = torch.stack([TF.normalize(TF.to_tensor(read_image(r)[1]), engine.config["mean"],
                                               engine.config["std"]) for r in batch])
            logits = engine.model(pixels)
            assert logits.shape == (len(batch), 2) and torch.isfinite(logits).all()
            raw = logits.softmax(-1)[:, 1].tolist()
            for row, (normal, defect), score in zip(batch, logits.tolist(), raw, strict=True):
                result.append(dict(image_id=row["image_id"], image_sha256=row["image_sha256"],
                                   group_id=row["group_id"], label=int(row["class_id"]),
                                   good_logit=normal, defect_logit=defect, margin=defect-normal,
                                   raw_score=score, prediction=int(score >= .5)))
            if offset % 256 == 0:
                print(output.name, min(offset+batch_size,len(rows)), "/", len(rows), flush=True)
    with output.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
    print(output.name, "done", round(time.monotonic()-started,1), "seconds", flush=True)
    return result


def metrics(margins, labels, temperature):
    scaled = margins / temperature
    p = expit(scaled)
    bins = np.minimum((p*10).astype(int),9)
    ece = sum(mask.mean()*abs(float(labels[mask].mean()-p[mask].mean()))
              for i in range(10) if (mask := bins == i).any())
    return dict(nll=float(np.mean(np.logaddexp(0, scaled)-labels*scaled)),
                brier=float(np.mean((p-labels)**2)), ece_10_equal_width=float(ece))


def bounds(bad, n):
    return float(beta.ppf(.95, bad+1, n-bad)) if 0 <= bad < n else 1.0


def threshold_report(policy, probabilities):
    y = np.array([r["label"] for r in policy])
    group = np.array([r["group_id"] for r in policy])
    good_pred = np.array([r["prediction"] == 0 for r in policy])
    good = y == 0
    ng, nb = int(good.sum()), int((~good).sum())
    nbg = len(set(group[~good]))
    def at(value):
        passed = good_pred & (probabilities <= value)
        safe, bad = int((passed & good).sum()), int((passed & ~good).sum())
        bg = len(set(group[passed & ~good]))
        return dict(threshold=float(value), normal_autopass=safe, normal_autopass_rate=safe/ng,
                    defect_autopass=bad, defect_autopass_rate=bad/nb,
                    review=len(y)-safe-bad, defect_group_autopass=bg,
                    photo_upper95_descriptive=bounds(bad, nb), group_upper95_descriptive=bounds(bg,nbg))

    bad_scores = probabilities[good_pred & ~good]
    first_bad = float(bad_scores.min()) if bad_scores.size else None
    ceiling = min(.5, first_bad) if first_bad is not None else .5
    interior = float(np.nextafter(ceiling, 0)) if ceiling > 0 else 0
    best_grid = [at(x) for x in GRID if x < ceiling]
    demonstration = max((r for r in best_grid if r["normal_autopass"] > 0 and r["defect_autopass"] == 0),
                        key=lambda r: (r["normal_autopass"],-r["threshold"]), default=None)
    return dict(normal_count=ng, defect_count=nb, defect_groups=nbg, threshold_inequality="<= and raw prediction GOOD",
                candidates=[at(value) for value in GRID], first_bad_score_exclusive=first_bad,
                first_bad_examples=[dict(image_id=r["image_id"], group_id=r["group_id"], raw=r["raw_score"],
                                         calibrated=float(p))
                                    for r,p in zip(policy,probabilities,strict=True)
                                    if r["label"] == 1 and r["prediction"] == 0 and p == first_bad],
                best_observed_zero_miss_coverage=at(interior) if ceiling>0 else None,
                illustrative_grid_candidate=demonstration)


def main(out):
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    engine = PinEngine()
    manifest = json.loads((PREP / "config.json").read_bytes())["manifests"]
    roles, assigned_groups, assigned_images = {}, set(), set()
    for role, item in manifest.items():
        path = Path(item["path"])
        assert sha(path) == item["sha256"]
        rows = read_csv(path)
        groups, images = ({r[k] for r in rows} for k in ("group_id","image_sha256"))
        assert not assigned_groups & groups and not assigned_images & images and len(images) == len(rows)
        assigned_groups |= groups
        assigned_images |= images
        roles[role] = rows

    saved = {r["image_id"]: r for r in read_csv(RUN / "best_model_selection_predictions.csv")}
    pilot = sorted(roles["model_selection"], key=lambda r: r["image_sha256"])[:32]
    checks = extract(engine,pilot,out/"cpu_parity.csv")
    parity = dict(count=len(checks),
                  mismatches=[r["image_id"] for r in checks if r["prediction"] != int(saved[r["image_id"]]["predicted"])],
                  max_abs_raw_error=max(abs(r["raw_score"]-float(saved[r["image_id"]]["raw_defect_score"])) for r in checks))
    if parity["mismatches"] or parity["max_abs_raw_error"] > .002:
        raise ValueError(f"CPU scores diverged from saved GPU reference: {parity}")
    cal, policy = [extract(engine,roles[role],out/(role+"_scores.csv"))
                   for role in ("calibration_fit","policy_development")]

    def margins_labels(rows):
        return np.array([r["margin"] for r in rows]), np.array([r["label"] for r in rows])

    cal_x, cal_y = margins_labels(cal)
    pol_x, pol_y = margins_labels(policy)
    def objective(log_t):
        scaled = cal_x / np.exp(log_t)
        return float(np.mean(np.logaddexp(0,scaled)-cal_y*scaled))
    opt = minimize_scalar(objective,bounds=(-4,4),method="bounded",options={"xatol":1e-10})
    assert opt.success and -3.99 < opt.x < 3.99
    temperature = float(np.exp(opt.x))
    comparative = {}
    for label, x, y in (("fit",cal_x,cal_y),("policy_development",pol_x,pol_y)):
        comparative[label] = dict(raw=metrics(x,y,1),temperature=metrics(x,y,temperature))
    report = dict(model_version=VERSION,checkpoint_sha256=EXPECTED,temperature=temperature,
                  temperature_fit_method="binary logit-margin temperature scaling, NLL on calibration_fit only",
                  score_runtime="DGX CPU FP32, batch 8",cpu_parity=parity,
                  runtime_versions={k:importlib.metadata.version(k) for k in ("torch","torchvision","timm","Pillow","numpy","scipy")},
                  data={role:dict(count=len(roles[role]),manifest_sha256=manifest[role]["sha256"],
                                  scores_sha256=sha(out/(role+"_scores.csv")))
                        for role in ("calibration_fit","policy_development")},
                  metrics=comparative,
                  policies={"raw":threshold_report(policy,expit(pol_x)),
                            "temperature":threshold_report(policy,expit(pol_x/temperature))},
                  official_validation_used=False,policy_activated=False,
                  limitation="Thresholds evaluated and selected on policy-development data; confidence bounds are descriptive only. Photo groups are not verified physical units.")
    write_json(out/"policy_report.json",report)
    print("POLICY_DEVELOPMENT_COMPLETE",out/"policy_report.json",flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(strict=True))
