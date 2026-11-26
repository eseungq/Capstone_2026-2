"""Prepare and run the fixed-pin baseline using the existing FRAME trainer."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path
import sys


ROOT = Path("/path/to/private/validated-project")
FRAME_RUN = ROOT / "outputs/frame_training/comparison_train_20261022T160533_169658Z/unified"
ROLES = ("train", "model_selection", "calibration_fit", "policy_development")
MODEL = "swin_tiny_patch4_window7_224.ms_in1k"
SEED = 42
GPU_VERSIONS = {
    "torch": "2.10.0a0+b558c986e8.nv25.11", "torchvision": "0.25.0a0+7a13ad0f",
    "timm": "1.0.30", "Pillow": "12.0.0", "numpy": "2.1.0",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def dump(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def prepare(source, prep):
    report = read(source / "summary.json")
    assert report["target"] == "COWL_COVER fixed pin only" and not report["official_validation_opened"]
    frame = read(FRAME_RUN / "run_config.json")
    original = frame["config"]
    initial = FRAME_RUN / "initial_state.pt"
    assert original["model_name"] == MODEL and original["image_size"] == 224 and original["seed"] == SEED
    assert frame["initial_state_source"] == "ImageNet initialization with seed-controlled head"
    assert digest(initial) == frame["initial_state_sha256"]
    archive_stats = {}
    manifests = {}
    roles = {}
    for role in ROLES:
        source_csv = source / f"{role}.csv"
        entry = report["roles"][role]
        assert digest(source_csv) == entry["manifest_sha256"]
        with source_csv.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == entry["total"]
        assert {r["annotation_types"] for r in rows} == {"고정핀 불량"}
        assert {r["class_id"] for r in rows} == {"0", "1"}
        output = prep / f"{role}.csv"
        with output.open("x", encoding="utf-8", newline="") as stream:
            fields = ("image_id", "image_archive", "offset", "size", "image_sha256", "group_id",
                      "defect_type", "class_id", "label_sha256")
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                for archive in (row["image_archive"], row["label_archive"]):
                    if archive not in archive_stats:
                        stat = Path(archive).stat()
                        archive_stats[archive] = dict(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)
                writer.writerow(dict(image_id=row["image_id"], image_archive=row["image_archive"],
                                     offset=row["image_offset"], size=row["image_bytes"],
                                     image_sha256=row["source_sha256"], group_id=row["group_id"],
                                     defect_type=row["annotation_types"], class_id=row["class_id"],
                                     label_sha256=row["label_sha256"]))
        roles[role] = len(rows)
        manifests[role] = dict(path=str(output), sha256=digest(output), source_sha256=digest(source_csv))
    assert roles == dict(train=7235, model_selection=1033, calibration_fit=1033, policy_development=1035)
    fields = ("model_name", "image_size", "epochs", "batch_size", "learning_rate", "weight_decay",
              "mean", "std", "seed", "prediction_cutoff")
    config = {k: original[k] for k in fields}
    config.update(part_code="COWL_COVER", scope="Fixed pin only", inspection_types=["고정핀 불량"],
                  class_mapping={"GOOD": 0, "DEFECT": 1}, archive_stats=archive_stats, manifests=manifests,
                  roles=roles, initialization=dict(path=str(initial), sha256=digest(initial)),
                  split_report_sha256=digest(source / "summary.json"),
                  trainer_sha256={f: digest(ROOT / f) for f in ("frame_model/train.py", "frame_model/check.py")},
                  launcher_sha256={f: digest(prep / f) for f in ("cowl_pin_training.py", "run_cowl_pin.sh")},
                  limitations=["Fixed-pin photo-level binary classification only.",
                               "Official AI-Hub Validation is reserved for final evaluation.",
                               "Calibration and policy roles are reserved; their pixels are not read in training.",
                               "224 baseline excludes the reviewed unreadable sample. Field coverage remains unverified."])
    dump(prep / "config.json", config)


def verified(prep):
    sys.path.insert(0, str(ROOT))
    from frame_model.train import manifests

    config, tables = manifests(prep)
    if config["part_code"] != "COWL_COVER" or config["inspection_types"] != ["고정핀 불량"]:
        raise ValueError("Unexpected fixed-pin training scope")
    for file, expected in config["trainer_sha256"].items():
        if digest(ROOT / file) != expected:
            raise ValueError(f"Trainer changed: {file}")
    for file, expected in config["launcher_sha256"].items():
        if digest(prep / file) != expected:
            raise ValueError(f"Launcher changed: {file}")
    initial = Path(config["initialization"]["path"])
    if digest(initial) != config["initialization"]["sha256"]:
        raise ValueError("ImageNet initial state changed")
    return config, tables, initial


def revise_epochs(previous, prep, epochs):
    config, _, _ = verified(previous)
    if not 1 <= epochs <= config["epochs"]:
        raise ValueError("Revision must keep or reduce the epoch limit")
    config["epochs"] = epochs
    config["launcher_sha256"] = {f: digest(prep / f) for f in ("cowl_pin_training.py", "run_cowl_pin.sh")}
    dump(prep / "config.json", config)


def compatible_smoke(config, output_root):
    # A one-epoch execution check is independent of the full epoch count.
    # Launcher changes are verified separately; all trainer/data/runtime inputs must match.
    expected = {k: v for k, v in config.items() if k not in {"epochs", "launcher_sha256"}}
    for path in sorted(output_root.glob("smoke_*"), reverse=True):
        if not all((path / name).is_file() for name in ("status.json", "launch.json", "run_config.json", "smoke_last.pt")):
            continue
        status = read(path / "status.json")
        run = read(path / "run_config.json")
        launch = read(path / "launch.json")
        source = Path(launch["preparation"]) / "config.json"
        if (status.get("status") != "passed" or run.get("mode") != "smoke" or run.get("epochs") != 1
                or run.get("versions") != GPU_VERSIONS or not source.is_file()
                or digest(source) != launch.get("config_sha256") or run["config"] != read(source)):
            continue
        if {k: v for k, v in run["config"].items() if k not in {"epochs", "launcher_sha256"}} == expected:
            return path
    return None


def check(prep):
    import timm
    import torch
    from torchvision.transforms import functional as TF

    config, tables, initial = verified(prep)
    from frame_model.check import read_image
    from frame_model.train import subset

    torch.set_num_threads(2)
    model = timm.create_model(config["model_name"], pretrained=False, num_classes=2)
    model.load_state_dict(torch.load(initial, map_location="cpu", weights_only=True), strict=True)
    batch = torch.stack([TF.normalize(TF.to_tensor(read_image(row)[1]), config["mean"], config["std"])
                         for rows in tables.values() for row in subset(rows, 1)])
    model.eval()
    with torch.inference_mode():
        logits = model(batch)
    assert tuple(batch.shape) == (4, 3, 224, 224)
    assert tuple(logits.shape) == (4, 2) and torch.isfinite(logits).all()
    smoke = compatible_smoke(config, ROOT / "outputs/cowl_pin_training")
    dump(prep / "preflight.json", dict(status="passed", runtime="DGX host venv CPU",
                                      model=config["model_name"], input_shape=list(batch.shape),
                                      output_shape=list(logits.shape), manifests=config["roles"],
                                      config_sha256=digest(prep / "config.json"),
                                      weights_sha256=digest(initial),
                                      configured_epochs=config["epochs"],
                                      compatible_prior_gpu_smoke=str(smoke) if smoke else None,
                                      packages={k: importlib.metadata.version(k) for k in GPU_VERSIONS},
                                      official_validation_used=False, training_started=False, gpu_smoke_run=False))
    print("[COWL PIN PREFLIGHT PASSED]", prep / "preflight.json", flush=True)


def gpu_run(prep, mode, start_training):
    if mode == "train" and not start_training:
        raise ValueError("Full training needs --start-training")
    actual = {k: importlib.metadata.version(k) for k in GPU_VERSIONS}
    if actual != GPU_VERSIONS:
        raise RuntimeError(f"GPU runtime differs from the frozen FRAME training stack: {actual}")
    config, tables, initial = verified(prep)
    if read(prep / "preflight.json")["config_sha256"] != digest(prep / "config.json"):
        raise ValueError("CPU preflight does not match the configuration")
    from frame_model.train import execute, subset

    smoke = mode == "smoke"
    output_root = ROOT / "outputs/cowl_pin_training"
    config_sha = digest(prep / "config.json")
    smoke_evidence = None
    if not smoke:
        smoke_evidence = compatible_smoke(config, output_root)
        if smoke_evidence is None:
            raise RuntimeError("A successful GPU smoke run for this configuration is required")
    if smoke:
        tables = {role: subset(rows, 16 if role == "train" else 8) for role, rows in tables.items()}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    out = output_root / f"{mode}_{stamp}"
    out.mkdir(parents=True)
    print("[COWL PIN RUN]", out, flush=True)
    dump(out / "launch.json", dict(mode=mode, preparation=str(prep), config_sha256=config_sha,
                                  gpu_smoke_evidence=str(smoke_evidence) if smoke_evidence else None))
    try:
        execute(config, tables, prep, out, smoke, initial_state=initial,
                context={"partCode": "COWL_COVER", "inspectionScope": "FIXED_PIN",
                         "qualityEvaluation": not smoke, "launcherSHA256": config["launcher_sha256"]})
    except BaseException as error:
        if not (out / "status.json").exists():
            dump(out / "status.json", dict(status="failed_or_interrupted", error_type=type(error).__name__))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "revise-epochs", "check", "smoke", "train"))
    parser.add_argument("preparation", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--start-training", action="store_true")
    args = parser.parse_args()
    prep = args.preparation.resolve(strict=True)
    if args.mode == "prepare":
        prepare(args.source, prep)
    elif args.mode == "revise-epochs":
        if args.source is None or args.epochs is None:
            parser.error("revise-epochs requires --source and --epochs")
        revise_epochs(args.source, prep, args.epochs)
    elif args.mode == "check":
        check(prep)
    else:
        gpu_run(prep, args.mode, args.start_training)
