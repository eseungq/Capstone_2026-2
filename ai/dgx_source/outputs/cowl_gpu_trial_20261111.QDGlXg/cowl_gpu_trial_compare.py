"""Compare CUDA with the frozen CPU cowl deployment using the same checkpoint."""

from collections import Counter
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
from statistics import mean
import sys
from time import perf_counter

import torch
from torchvision.transforms import functional as TF

from cowl_unified_calibrated_trial import (
    CalibratedEngine, PART, VERSION, build_server, load_policy, load_shared_api,
    probability, request, running, select_photos,
)
from evaluate_cowl_unified import LINK, PIN, reference, sha
from frame_model.check import read_image


PROJECT = Path.cwd()
RUN = PROJECT / "outputs/cowl_unified_training_20261110.zQKXgx/runs/train"
STUDY = PROJECT / "outputs/cowl_unified_policy_20261110.8sMbOO"


class CudaEngine(CalibratedEngine):
    def __init__(self, run):
        super().__init__(run)
        self.model = self.model.to("cuda")
        self.metadata.update(device=torch.cuda.get_device_name())

    def tensor(self, image):
        return super().tensor(image).to("cuda")


def save(path, value):
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, indent=2, allow_nan=False)
        file.write("\n")


def http_comparison(cpu, gpu, stage, candidate, report):
    photos = select_photos(STUDY, report, candidate)
    order = list(photos)

    class Origin(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            photo = photos[self.path.removeprefix("/")]
            blob = photo["blob"]
            self.send_response(200)
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

    records = {}
    with running(ThreadingHTTPServer(("127.0.0.1", 0), Origin)) as origin:
        for name, engine in (("CPU", cpu), ("GPU", gpu)):
            http, _ = build_server(engine, stage / name, [origin], 0, candidate["temperature"])
            with running(http) as api:
                measurements = []
                for cycle in range(3):
                    for key in order:
                        started = perf_counter()
                        status, response, _ = request(api+"/internal/v1/predict", dict(
                            inspectionId=f"cowl-device-{name.lower()}-{cycle}-{key}",
                            partCode=PART, requestedModelVersion=VERSION, imageUrl=f"{origin}/{key}"))
                        elapsed = (perf_counter()-started)*1000
                        assert status == 200 and response["predictedQuality"] == photos[key]["predicted"]
                        cam = response["gradcam"]
                        assert (cam is None if photos[key]["predicted"]=="GOOD" else
                                (cam["status"], cam["format"])==("GENERATED", "jpeg"))
                        measurements.append(dict(cycle=cycle, case=key, prediction=response["predictedQuality"],
                                                 probability=response["calibratedDefectProbability"],
                                                 cam=cam["status"] if cam else None,
                                                 api_ms=response["inferenceTimeMs"], roundtrip_ms=elapsed))
                steady = [row for row in measurements if row["cycle"]]
                records[name] = dict(requests=measurements, mean_steady_ms=mean(r["api_ms"] for r in steady),
                                     mean_good_ms=mean(r["api_ms"] for r in steady if r["prediction"]=="GOOD"),
                                     mean_defect_ms=mean(r["api_ms"] for r in steady if r["prediction"]=="DEFECT"),
                                     steady_total_ms=sum(r["roundtrip_ms"] for r in steady))
            print(name, {k: v for k, v in records[name].items() if k!="requests"}, flush=True)
    return records


def gpu_policy(engine, candidate, report):
    temperature, threshold = candidate["temperature"], candidate["threshold"]
    results = {}
    for kind, locations in (("fixed_pin", PIN), ("linkage", LINK)):
        manifest = reference(kind, locations)[0]
        path = STUDY / f"{kind}_heldout_scores.csv"
        assert sha(path) == report["heldout_sources"][kind]["scores_sha256"]
        with path.open(newline="", encoding="utf-8") as file:
            old = {row["image_id"]: row for row in csv.DictReader(file)}
        assert old.keys() == manifest.keys()
        counters = Counter()
        flips = []
        max_raw_delta = max_probability_delta = 0
        with torch.inference_mode():
            for i, row in enumerate(sorted(manifest.values(), key=lambda r: r["offset"]), 1):
                prior = old[row["image_id"]]
                assert prior["image_sha256"] == row["image_sha256"] and prior["label"] == row["class_id"]
                tensor = TF.normalize(TF.to_tensor(read_image(row)[1]), engine.config["mean"], engine.config["std"])
                logits = engine.model(tensor.unsqueeze(0).to("cuda"))
                normal, defect = logits[0].tolist()
                gpu_raw = logits.softmax(-1)[0, 1].item()
                gpu_prob = probability(defect-normal, temperature)
                cpu_raw = float(prior["raw_score"])
                cpu_prob = probability(float(prior["margin"]), temperature)
                assert all(map(math.isfinite, (gpu_raw, gpu_prob)))
                cpu_pred, gpu_pred = int(prior["prediction"]), int(gpu_raw >= .5)
                cpu_pass, gpu_pass = cpu_pred==0 and cpu_prob<=threshold, gpu_pred==0 and gpu_prob<=threshold
                label = "defect" if row["class_id"]=="1" else "normal"
                counters.update({label: 1, "class_flips": int(cpu_pred!=gpu_pred),
                                 f"cpu_pass_{label}": int(cpu_pass), f"gpu_pass_{label}": int(gpu_pass)})
                max_raw_delta = max(max_raw_delta, abs(gpu_raw-cpu_raw))
                max_probability_delta = max(max_probability_delta, abs(gpu_prob-cpu_prob))
                if cpu_pass!=gpu_pass:
                    flips.append(dict(id=row["image_id"], label=label, cpu_pass=cpu_pass, gpu_pass=gpu_pass,
                                      cpu_probability=cpu_prob, gpu_probability=gpu_prob))
                if i % 256 == 0 or i == len(manifest):
                    print(f"{kind} {i}/{len(manifest)}", flush=True)
        results[kind] = dict(counts=dict(counters), threshold_flips=flips,
                             max_raw_delta=max_raw_delta, max_calibrated_delta=max_probability_delta)
    return results


if __name__=="__main__":
    stage = Path(sys.argv[1])
    load_shared_api(PROJECT, stage)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    assert torch.cuda.is_available()
    frozen, evidence = load_policy(STUDY)
    cpu, gpu = CalibratedEngine(RUN), CudaEngine(RUN)
    performance = http_comparison(cpu, gpu, stage, frozen, evidence)
    save(stage/"http_comparison.json", performance)
    del cpu
    parity = gpu_policy(gpu, frozen, evidence)
    save(stage/"gpu_policy_comparison.json", dict(model=VERSION, gpu=torch.cuda.get_device_name(),
         torch=torch.__version__, precision="FP32 without TF32", threshold=frozen["threshold"],
         inference="single image", score_set="existing held-out photos", compared=parity))
    print("COWL_CUDA_COMPARISON_COMPLETE", flush=True)
