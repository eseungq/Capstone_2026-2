"""Launch the separate DOOR e02 calibrated demonstration API after HTTP checks."""

import argparse
from hashlib import file_digest, sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import logging
import math
from pathlib import Path
import sys

ROOT = Path("/path/to/private/validated-project")
PRIOR_TRIAL = ROOT / "outputs/door_policy_trial_20261109.bTH85T/door_calibrated_trial_20261109.py"
TRAINING_HELPERS = ROOT / "outputs/cars_ad_e02_offline.0KilRE"
GPU_RECORD = ROOT / (
    "outputs/door_e02_live/autopass_reserved_candidates_20261104/20261104T132651_701625Z/"
    "photo_group_evaluation/door_gpu_rescreen_20261112.8EL6t5/scores.json"
)
GPU_RECORD_SHA = "8e3c1a6331c3a67f1365a37ec659313c658c0f1919c3b4d8e34af1e88b9994f1"
MODEL = "door-swin-tiny-e02-28a2dd1cb40b-dev"
WEIGHT_SHA = "28a2dd1cb40b4bbecf3fc4e34dfc5354179dcb31c0c37297f1d3ee3bfe3d985e"
TEMPERATURE = 1.1173850605473976
BETWEEN_SHA = "516bc9173264f4b413ab1bd9281675180765776fe5ca6212d81db470fba9ba95"
CALIBRATOR = "door-e02-temperature-30962f5cac45-demo"
ORIGIN = "http://127.0.0.1:8080"
MIN_THRESHOLD, DEFAULT_THRESHOLD = 0.0084, 0.0092


def previous_integration():
    spec = importlib.util.spec_from_file_location("previous_door_trial", PRIOR_TRIAL)
    trial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trial)
    trial.CALIBRATOR = CALIBRATOR
    return trial


def load_test_samples():
    raw_scores = GPU_RECORD.read_bytes()
    if sha256(raw_scores).hexdigest() != GPU_RECORD_SHA:
        raise ValueError("Frozen GPU reference differs")
    data = json.loads(raw_scores)
    if data["model_version"] != MODEL or data["model_sha256"] != WEIGHT_SHA:
        raise ValueError("Frozen GPU reference belongs to another model")
    samples = data["results"]
    return {
        "between": next(row for row in samples if row["image_sha256"] == BETWEEN_SHA),
        "above": min(
            (row for row in samples if int(row["class_id"]) == int(row["predicted_class"]) == 0
             and float(row["logit_margin"]) > -4),
            key=lambda row: abs(float(row["logit_margin"]) + 3.5),
        ),
        "defect": min(
            (row for row in samples if int(row["class_id"]) == int(row["predicted_class"]) == 1),
            key=lambda row: abs(float(row["raw_defect_probability"]) - 0.99),
        ),
    }


def write_result(path, result):
    temp = path.with_suffix(".pending")
    temp.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def verify_http(trial, engine, policy, work):
    samples = load_test_samples()
    images = {}
    for key, row in samples.items():
        path = Path(row["image_path"])
        with path.open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != row["image_sha256"]:
                raise ValueError(f"Image differs from GPU reference: {key}")
        images[key] = path.read_bytes()

    class TestImages(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            image = images.get(self.path.removeprefix("/"))
            if image is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(image)))
            self.end_headers()
            self.wfile.write(image)

    checks = {}
    with trial.running(ThreadingHTTPServer(("127.0.0.1", 0), TestImages)) as origin:
        http = trial.server(("127.0.0.1", 0), engine, [origin], work / "http_checks", policy)
        with trial.running(http) as address:
            status, listing = trial.request(address + "/internal/v1/models")
            expected = {"data": [{"partCode": "DOOR", "modelVersion": MODEL,
                                  "calibratorVersion": CALIBRATOR, "loadable": True}]}
            if status != 200 or listing != expected:
                raise ValueError("Model list does not advertise the agreed calibrator")
            for key, row in samples.items():
                status, result = trial.request(address + "/internal/v1/predict", {
                    "inspectionId": f"door-calibration-check-{key}", "partCode": "DOOR",
                    "requestedModelVersion": MODEL, "imageUrl": f"{origin}/{key}",
                })
                probability = result["calibratedDefectProbability"]
                expected_probability = trial.calibrated_probability(float(row["logit_margin"]), TEMPERATURE)
                predicted = "DEFECT" if key == "defect" else "GOOD"
                cam = result.get("gradcam")
                if (status != 200 or result["predictedQuality"] != predicted
                        or result["calibratorVersion"] != CALIBRATOR or result["modelVersion"] != MODEL
                        or not math.isclose(probability, expected_probability, abs_tol=0.00002)
                        or (predicted == "GOOD" and cam is not None)):
                    raise ValueError(f"HTTP response differs from frozen GPU evidence: {key}: {probability!r}")
                at_min = predicted == "GOOD" and probability <= MIN_THRESHOLD
                at_default = predicted == "GOOD" and probability <= DEFAULT_THRESHOLD
                if at_min or at_default != (key == "between"):
                    raise ValueError(f"Wrong policy branch: {key}: {probability!r}")
                checks[key] = {"predictedQuality": predicted, "calibratedDefectProbability": probability,
                               "referenceProbability": expected_probability, "imageSHA256": row["image_sha256"],
                               "at0.84percent": "AUTO_PASS" if at_min else "REVIEW",
                               "at0.92percent": "AUTO_PASS" if at_default else "REVIEW",
                               "camStatus": cam.get("status") if cam else None}
    return {"models": listing, "checks": checks, "policyDecisions": "local contract check"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    work = Path(__file__).resolve().parent
    sys.path.insert(0, str(ROOT))
    metadata = {"method": "binary-temperature-scaling", "modelVersion": MODEL,
                "checkpointSHA256": WEIGHT_SHA, "temperature": TEMPERATURE}
    digest = sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if CALIBRATOR != f"door-e02-temperature-{digest[:12]}-demo":
        raise ValueError("Calibration metadata does not match agreed version")
    policy = {**metadata, "calibratorVersion": CALIBRATOR}
    trial = previous_integration()
    engine = trial.load_engine(ROOT, TRAINING_HELPERS, policy)
    engine.torch.backends.cuda.matmul.allow_tf32 = False
    engine.torch.backends.cudnn.allow_tf32 = False
    evidence = verify_http(trial, engine, policy, work)
    write_result(work / "http_verified.json", evidence)
    http = trial.server((args.host, args.port), engine, [ORIGIN], work / "requests", policy)
    logging.info("Verified DOOR trial is available at %s:%s", args.host, args.port)
    try:
        http.serve_forever()
    finally:
        http.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
