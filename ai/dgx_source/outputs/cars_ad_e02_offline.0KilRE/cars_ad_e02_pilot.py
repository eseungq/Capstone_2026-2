"""Run a fixed-checkpoint, CPU-only CARS-AD door pilot on the DGX."""
import ast
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageOps
import timm
from timm.data import resolve_model_data_config
import torch
from torch.utils.data import Dataset
from torchvision.transforms import functional as TF

from ai_api.e02_engine import ROOT, validate_candidate
from ai_api.e02_integration.diagnose_cam_cpu import cam, scores
from prototype.engine import Engine, sha


EXPECTED_VERSION = "door-swin-tiny-e02-28a2dd1cb40b-dev"
EXPECTED_SHA256 = "28a2dd1cb40b4bbecf3fc4e34dfc5354179dcb31c0c37297f1d3ee3bfe3d985e"


def load_engine(manifest, run, cfg):
    engine = Engine.__new__(Engine)
    engine.torch = torch
    engine.model = timm.create_model(cfg["config"]["model_name"], pretrained=False, num_classes=2)
    checkpoint = torch.load(run / "best.pt", map_location="cpu", weights_only=False)
    if json.loads(json.dumps(checkpoint["metadata"])) != cfg or checkpoint["epoch"] != 2:
        raise ValueError("Checkpoint metadata does not match the frozen candidate")
    engine.model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    engine.model.float().eval()
    dc = resolve_model_data_config(engine.model)
    mean, std = dc["mean"], dc["std"]
    if cfg["normalization"] != {"mean": list(mean), "std": list(std)} or dc["input_size"] != (3, 224, 224):
        raise ValueError("Input configuration mismatch")
    fill = tuple(round(value * 255) for value in mean)
    training = ROOT / manifest["trainingSource"]
    tree = ast.parse(training.read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    dataset = next(node for node in main.body if isinstance(node, ast.ClassDef) and node.name == "DoorDataset")
    context = dict(Dataset=Dataset, Image=Image, ImageOps=ImageOps, TF=TF,
                   CONFIG=cfg["config"], mean=mean, std=std, fill=fill)
    exec(compile(ast.Module(body=[dataset], type_ignores=[]), str(training), "exec"), context)
    engine.dataset = context["DoorDataset"]
    return engine


def weight_digest(model):
    digest = hashlib.sha256()
    for key, tensor in model.state_dict().items():
        digest.update(key.encode("utf-8"))
        digest.update(tensor.detach().contiguous().numpy().tobytes())
    return digest.hexdigest()


def explain(engine, tensor, image_path, dest, layer):
    info, _, heat = cam(engine.model, tensor, layer, "defect")
    if heat is None:
        return dict(status="NO_ACTIVATION", mapType=info["status"], image=None)
    with Image.open(image_path) as image:
        photo = ImageOps.exif_transpose(image).convert("RGB")
    contained = ImageOps.contain(photo, (224, 224), Image.Resampling.BICUBIC)
    width, height = contained.size
    left, top = round((224 - width) / 2), round((224 - height) / 2)
    values = np.asarray(Image.fromarray(heat[top:top + height, left:left + width]).resize(
        photo.size, Image.Resampling.BILINEAR)).clip(0, 1)
    colors = np.stack((values, np.zeros_like(values), 1 - values), axis=-1) * 255
    overlay = np.asarray(photo) * 0.6 + colors * 0.4
    Image.fromarray(overlay.clip(0, 255).astype(np.uint8)).save(dest, quality=92)
    return dict(status="GENERATED", image=f"cam/{dest.name}")


def main(bundle):
    if torch.cuda.is_available():
        raise RuntimeError("CUDA must be disabled for the CPU pilot")
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    manifest, run, cfg = validate_candidate()
    if (manifest["modelVersion"], manifest["checkpointSHA256"]) != (EXPECTED_VERSION, EXPECTED_SHA256):
        raise ValueError("Unexpected e02 model identity")
    engine = load_engine(manifest, run, cfg)
    before = weight_digest(engine.model)
    versions = {name: importlib.metadata.version(name) for name in cfg["versions"]}
    expected_gpu_scores = [0.010911530815064907, 0.012285854667425156, 0.9999741315841675]
    fixtures = []
    for index, expected in zip((0, 1, 3), expected_gpu_scores):
        image = Path(manifest["samples"][index]["image_path"])
        actual = scores(engine.model, engine.tensor(image).unsqueeze(0))["probability"]
        fixtures.append(dict(index=index, gpuReference=expected, cpuScore=actual,
                             absoluteDifference=abs(actual - expected),
                             classAgrees=(actual >= 0.5) == (expected >= 0.5)))
    if not all(row["classAgrees"] for row in fixtures):
        raise RuntimeError("CPU fixture classifications disagree with the previous GPU results")
    records = json.loads((bundle / "verified_manifest.json").read_text(encoding="utf-8"))
    if Counter(row["decision"] for row in records) != {"GOOD_DOOR": 3, "DEFECT_DOOR": 7}:
        raise ValueError("Expected the ten reviewed CARS-AD photos")
    dest = bundle / "results"
    (dest / "cam").mkdir(parents=True, exist_ok=False)
    results = []
    for row in records:
        image = bundle / row["image"]
        if sha(image) != row["sha256"]:
            raise ValueError(f"Hash mismatch for {row['id']}")
        tensor = engine.tensor(image).unsqueeze(0)
        score = scores(engine.model, tensor)["probability"]
        if not np.isfinite(score):
            raise ValueError(f"Nonfinite score for {row['id']}")
        prediction = "DEFECT" if score >= 0.5 else "GOOD"
        ground_truth = "DEFECT" if row["decision"] == "DEFECT_DOOR" else "GOOD"
        cam_info = dict(status="NOT_REQUIRED", image=None)
        if prediction == "DEFECT":
            try:
                cam_info = explain(engine, tensor, image, dest / "cam" / f"{row['id']}.jpg",
                                   manifest["gradcamLayer"])
            except Exception as error:
                cam_info = dict(status="FAILED", image=None, error=str(error))
        results.append(dict(**row, groundTruth=ground_truth, prediction=prediction, rawDefectScore=score,
                            correct=prediction == ground_truth, gradcam=cam_info))
        print(row["id"], ground_truth, prediction, f"{score:.8f}", cam_info["status"], flush=True)
    if weight_digest(engine.model) != before or sha(run / "best.pt") != EXPECTED_SHA256:
        raise RuntimeError("The checkpoint or model state changed")
    report = dict(scope="selected external photos; qualitative pilot", modelVersion=EXPECTED_VERSION,
                  checkpointSHA256=EXPECTED_SHA256, device="DGX CPU", cutoff=0.5,
                  runtimeVersions=versions, recordedTrainingVersions=cfg["versions"],
                  runtimeVersionsMatch=versions == cfg["versions"], gpuFixtureComparison=fixtures,
                  gradcamLayer=manifest["gradcamLayer"], modelStateUnchanged=True, results=results)
    (dest / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                      encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
