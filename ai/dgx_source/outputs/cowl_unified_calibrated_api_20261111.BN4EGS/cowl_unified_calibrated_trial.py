"""Run the frozen unified COWL_COVER calibration on the CPU trial API."""

import argparse
from contextvars import ContextVar
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import io
import json
import math
import os
from pathlib import Path
from threading import Event
from time import perf_counter

from PIL import Image, ImageOps
import torch

from cowl_unified_trial_api import LinkageEngine, MODEL_SHA, PART, VERSION, load_shared_api, request, running
from evaluate_cowl_unified import LINK, PIN, read_csv, reference, sha


CANDIDATE_SHA = "2d80fc926685d9a1eb647233fd50a0cdc159b4a07788dc2e7d7482a2e87becf2"
REPORT_SHA = "88749946c668d1e986ba4e06562e42ade34485f49f47c51535c1e3b7996cb403"
CALIBRATOR = "cowl-unified-e08-temperature-2d80fc926685-demo"
MARGIN = ContextVar("cowl_trial_margin", default=None)


def probability(margin, temperature):
    scaled = margin / temperature
    exponential = math.exp(-abs(scaled))
    return 1 / (1 + exponential) if scaled >= 0 else exponential / (1 + exponential)


def load_policy(study):
    paths = [study / name for name in ("frozen_candidate.json", "heldout_policy_report.json")]
    assert tuple(map(sha, paths)) == (CANDIDATE_SHA, REPORT_SHA)
    candidate, report = [json.loads(path.read_bytes()) for path in paths]
    assert report["candidate"] == candidate and report["candidate_sha256"] == CANDIDATE_SHA
    assert report["zero_bad_observed"] and candidate["calibration_gate_passed"]
    assert not report["production_policy_activated"]
    assert candidate["checkpoint_sha256"] == MODEL_SHA and candidate["model_version"] == VERSION
    assert candidate["threshold"] == .0163 and candidate["runtime"] == "DGX CPU FP32 batch 1"
    assert math.isfinite(candidate["temperature"]) and candidate["temperature"] > 0
    return candidate, report


class CalibratedEngine(LinkageEngine):
    def predict(self, path):
        started = perf_counter()
        with torch.inference_mode():
            logits = self.model(self.tensor(self.read(path)))
            if logits.shape != (1, 2) or not torch.isfinite(logits).all():
                raise ValueError("Invalid unified model logits")
            normal, defect = logits[0].tolist()
            MARGIN.set(defect - normal)
            score = logits.softmax(-1)[0, 1].item()
        return dict(predicted_class=int(score >= .5), raw_defect_score=score,
                    processing_ms=(perf_counter() - started) * 1000)


def build_server(engine, runtime, origins, port, temperature):
    from ai_api import contract
    from ai_api.e02_integration.handler import Handler
    from ai_api.e02_integration.serve import IntegrationService
    from ai_api.server import Downloader, Server

    class CalibratedService(IntegrationService):
        part_code = PART

        def model_inventory(self):
            data = super().model_inventory()
            data["models"][0]["partCode"] = self.part_code
            return data

        def predict(self, body, *, request_id=None):
            token = MARGIN.set(None)
            try:
                result = super().predict(body, request_id=request_id)
                margin = MARGIN.get()
                if margin is None or not math.isfinite(margin):
                    raise contract.Failure("INFERENCE_FAILED", 503)
                result["calibratedDefectProbability"] = probability(margin, temperature)
                result["calibratorVersion"] = CALIBRATOR
                return result
            finally:
                MARGIN.reset(token)

    class CalibratedHandler(Handler):
        def send(self, status, body, **kwargs):
            if status == 200 and self.path == "/internal/v1/models":
                body = {"data": [dict(row, calibratorVersion=CALIBRATOR if row["loadable"] else None)
                                 for row in body["data"]]}
            return super().send(status, body, **kwargs)

    downloader = Downloader(origins)
    http = Server(("127.0.0.1", port), CalibratedHandler)
    http.service = CalibratedService(engine, VERSION, downloader, runtime, cam_format="jpeg", jpeg_quality=90)
    return http, downloader


def select_photos(study, report, candidate):
    expected_defects = {
        "fixed_pin": "203_202_20_cd4624a8-91cc-4a95-bcb9-a6d6fb58e4c2",
        "linkage": "203_205_20_65fdcb82-d737-4e86-bebc-bdc7a1f18a47",
    }
    photos, threshold = {}, candidate["threshold"]
    for kind, locations in (("fixed_pin", PIN), ("linkage", LINK)):
        manifest = reference(kind, locations)[0]
        score_file = study / f"{kind}_heldout_scores.csv"
        assert sha(score_file) == report["heldout_sources"][kind]["scores_sha256"]
        scores = {r["image_id"]: r for r in read_csv(score_file)}
        assert scores.keys() == manifest.keys()
        cases = {kind: expected_defects[kind]}
        if kind == "fixed_pin":
            for name, target, test in (
                ("normal_pass", threshold - .002, lambda p: p < threshold - .0005),
                ("normal_review", threshold + .002, lambda p: p > threshold + .0005),
            ):
                cases[name] = min(
                    (ident for ident, row in scores.items()
                     if not manifest[ident]["cross_near"] and row["prediction"] == row["label"] == "0"
                     and test(probability(float(row["margin"]), candidate["temperature"]))),
                    key=lambda ident: (abs(probability(float(scores[ident]["margin"]), candidate["temperature"]) - target), ident))
        for case, ident in cases.items():
            row, score = manifest[ident], scores[ident]
            assert str(row["class_id"]) == score["label"] == score["prediction"] and not row["cross_near"]
            with Path(row["image_archive"]).open("rb") as archive:
                blob = os.pread(archive.fileno(), row["size"], row["offset"])
            assert sha256(blob).hexdigest() == score["image_sha256"] == row["image_sha256"]
            photos[case] = dict(blob=blob, image_id=ident, predicted="GOOD" if score["prediction"] == "0" else "DEFECT",
                                raw=float(score["raw_score"]), calibrated=probability(float(score["margin"]), candidate["temperature"]))
    return photos


def gate(response, threshold, *, ready=True, active=True, calibrator=CALIBRATOR):
    if response["predictedQuality"] == "DEFECT":
        return "REVIEW", "DEFECT_PREDICTED"
    if not ready or not active or response["modelVersion"] != VERSION:
        return "REVIEW", "NO_ACTIVE_POLICY"
    value = response["calibratedDefectProbability"]
    if value is None:
        return "REVIEW", "CALIBRATION_UNAVAILABLE"
    if response["calibratorVersion"] != calibrator:
        return "REVIEW", "NO_ACTIVE_POLICY"
    if value <= threshold:
        return "AUTO_PASS", None
    return "REVIEW", "ABOVE_THRESHOLD"


def check_http(api, origin, photos, candidate):
    threshold = candidate["threshold"]
    status, inventory, headers = request(api + "/internal/v1/models")
    assert status == 200 and headers.get("X-AI-Model-SHA256") == MODEL_SHA
    assert inventory == {"data": [dict(partCode=PART, modelVersion=VERSION, loadable=True, calibratorVersion=CALIBRATOR)]}
    checks = {}
    for case, photo in photos.items():
        payload = dict(inspectionId=f"cowl-unified-policy-{case}", partCode=PART,
                       requestedModelVersion=VERSION, imageUrl=f"{origin}/{case}")
        status, result, _ = request(api + "/internal/v1/predict", payload)
        assert status == 200 and result["inspectionId"] == payload["inspectionId"]
        assert result["modelVersion"] == VERSION and result["predictedQuality"] == photo["predicted"]
        assert result["calibratorVersion"] == CALIBRATOR
        assert abs(result["rawDefectProbability"] - photo["raw"]) <= .00001
        assert abs(result["calibratedDefectProbability"] - photo["calibrated"]) <= .00001
        cam = result["gradcam"]
        if photo["predicted"] == "GOOD":
            assert cam is None
        else:
            assert (cam["targetClass"], cam["status"], cam["format"]) == ("DEFECT", "GENERATED", "jpeg")
            with Image.open(io.BytesIO(photo["blob"])) as source, Image.open(
                    io.BytesIO(base64.b64decode(cam["imageBase64"], validate=True))) as overlay:
                assert overlay.format == "JPEG" and overlay.size == ImageOps.exif_transpose(source).size
                overlay.verify()
        actual = gate(result, threshold)
        expected = {
            "normal_pass": ("AUTO_PASS", None), "normal_review": ("REVIEW", "ABOVE_THRESHOLD")
        }.get(case, ("REVIEW", "DEFECT_PREDICTED"))
        assert actual == expected, (case, actual, expected)
        checks[case] = {key: result[key] for key in (
            "predictedQuality", "rawDefectProbability", "calibratedDefectProbability", "inferenceTimeMs")}
        checks[case].update(action=actual[0], reason=actual[1], image_id=photo["image_id"],
                            camStatus=cam["status"] if cam else None)
    base = dict(predictedQuality="GOOD", modelVersion=VERSION, calibratorVersion=CALIBRATOR,
                calibratedDefectProbability=threshold)
    guards = {
        "equal_threshold": gate(base, threshold),
        "just_above": gate(dict(base, calibratedDefectProbability=math.nextafter(threshold, 1)), threshold),
        "inactive": gate(base, threshold, active=False),
        "unready": gate(base, threshold, ready=False),
        "wrong_calibrator": gate(base, threshold, calibrator="another"),
        "wrong_model": gate(dict(base, modelVersion="another"), threshold),
        "missing_probability": gate(dict(base, calibratedDefectProbability=None), threshold),
        "defect_below_threshold": gate(dict(base, predictedQuality="DEFECT", calibratedDefectProbability=0), threshold),
    }
    assert list(guards.values()) == [
        ("AUTO_PASS", None), ("REVIEW", "ABOVE_THRESHOLD"), ("REVIEW", "NO_ACTIVE_POLICY"),
        ("REVIEW", "NO_ACTIVE_POLICY"), ("REVIEW", "NO_ACTIVE_POLICY"), ("REVIEW", "NO_ACTIVE_POLICY"),
        ("REVIEW", "CALIBRATION_UNAVAILABLE"), ("REVIEW", "DEFECT_PREDICTED"),
    ]
    return dict(api=api, inventory=inventory, checkpointSHA256=MODEL_SHA, candidateSHA256=CANDIDATE_SHA,
                passThreshold=threshold, temperature=candidate["temperature"], checks=checks, policyGuards=guards,
                policyScope="Local rule test against actual HTTP responses", backendChanged=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("study", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--image-origin", required=True)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    args.runtime.mkdir(parents=True)
    candidate, report = load_policy(args.study)
    load_shared_api(Path.cwd(), args.runtime)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    engine = CalibratedEngine(args.run)
    photos = select_photos(args.study, report, candidate)

    class FixtureOrigin(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            photo = photos.get(self.path.removeprefix("/"))
            if photo is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(photo["blob"])))
            self.end_headers()
            self.wfile.write(photo["blob"])

    http, downloader = build_server(engine, args.runtime / "requests", [args.image_origin],
                                    args.port, candidate["temperature"])
    with running(http) as api:
        with running(ThreadingHTTPServer(("127.0.0.1", 0), FixtureOrigin)) as origin:
            downloader.origins.add(origin)
            try:
                evidence = check_http(api, origin, photos, candidate)
            finally:
                downloader.origins.remove(origin)
        with (args.runtime / "smoke.json").open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, ensure_ascii=False, allow_nan=False, indent=2)
        print(f"COWL_UNIFIED_CALIBRATED_READY {api} {CALIBRATOR}", flush=True)
        if args.serve:
            Event().wait()


if __name__ == "__main__":
    main()
