"""Isolated FRAME calibration API and backend-rule contract fixtures."""

import argparse
import base64
import io
from PIL import Image, ImageOps
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import sys
import time


POLICY_SHA = "5d4299808c3ea2222fdb52b390a3730291339fdf479054737e1638c9ef21bc2b"
CALIBRATOR = "frame-e08-temperature-5d4299808c3e-demo"
SOURCE_SERVER = 'outputs/frame_layercam28_20261109.2V8EMY/8773/frame_unified_test_api_20261107.py'
POLICY_SOURCE = "outputs/frame_feature_validation_20261109.KBZGNt/policy"
FINAL_MANIFEST = ("outputs/frame_validation_review_closed_20261108.ROVWqL/"
                  "evaluation_confirmed_duplicates_excluded.jsonl")


def probability(margin, temperature):
    scaled = margin / temperature
    exp = math.exp(-abs(scaled))
    return 1 / (1 + exp) if scaled >= 0 else exp / (1 + exp)


def prepare_variant(project, runtime, candidate):
    original = (project / SOURCE_SERVER).read_text()
    replacements = {
        'CAM_LAYER = "layers.1.blocks.1.norm1"': (
            'CAM_LAYER = "layers.1.blocks.1.norm1"\n'
            f'TEMPERATURE = {candidate["temperature"]!r}\nCALIBRATOR_VERSION = {CALIBRATOR!r}'
        ),
        '    (overlay / "server.py").write_text(source)': '''    success_line = "            result=contract.success(ident,self.version,prediction,size,cam)"
    if source.count(success_line) != 1:
        raise RuntimeError("Existing response layout changed")
    source = source.replace(success_line, success_line + "\\n            self.add_calibration(result,prediction)")
    (overlay / "server.py").write_text(source)
    backend = (project / "ai_api/backend_contract.py").read_text()
    field = "'calibratorVersion':None,'loadable':row['available'] is True"
    if backend.count(field) != 1:
        raise RuntimeError("Existing inventory layout changed")
    (overlay / "backend_contract.py").write_text(backend.replace(
        field, "'calibratorVersion':row.get('calibratorVersion'),'loadable':row['available'] is True"))''',
        '        def tensor(self, path):': '''        def predict(self, path):
            from time import perf_counter
            torch.cuda.synchronize()
            start = perf_counter()
            pixels = self.tensor(path).unsqueeze(0).cuda()
            with torch.inference_mode():
                logits = self.model(pixels)
                if logits.shape != (1, 2) or not torch.isfinite(logits).all():
                    raise RuntimeError("Invalid logits")
                score = torch.softmax(logits, dim=1)[0, 1].item()
                margin = (logits[0, 1] - logits[0, 0]).item()
            torch.cuda.synchronize()
            return dict(predicted_class=int(score >= .5), raw_defect_score=score,
                        defect_logit_margin=margin, processing_ms=(perf_counter()-start)*1000,
                        model=self.metadata)

        def tensor(self, path):''',
        '        def model_inventory(self):': '''        def add_calibration(self, result, prediction):
            z = prediction["defect_logit_margin"] / TEMPERATURE
            exp = math.exp(-abs(z))
            result["calibratedDefectProbability"] = 1/(1+exp) if z >= 0 else exp/(1+exp)
            result["calibratorVersion"] = CALIBRATOR_VERSION

        def model_inventory(self):''',
        'available=ready, modelSha256=FRAME_SHA256 if ready else None)': (
            'available=ready, modelSha256=FRAME_SHA256 if ready else None,'
            ' calibratorVersion=CALIBRATOR_VERSION if ready else None)'
        ),
    }
    for old, new in replacements.items():
        if original.count(old) != 1:
            raise ValueError(f"Unexpected API source around {old[:60]!r}")
        original = original.replace(old, new)
    path = runtime / "frame_calibrated_trial_adapter.py"
    compile(original, str(path), "exec")
    path.write_text(original)
    sys.path.insert(0, str(runtime))
    import frame_calibrated_trial_adapter as api
    return api


def fixtures(project, candidate):
    frozen = project / POLICY_SOURCE
    validation_path = project / FINAL_MANIFEST
    raw = validation_path.read_bytes()
    if sha256(raw).hexdigest() != candidate["finalManifestSHA256"]:
        raise ValueError("Unexpected evaluation photos")
    source = {row["imageSHA256"]: row for row in map(json.loads, raw.splitlines())}
    score_rows = list(map(json.loads, (frozen / "final_scores.jsonl").read_text().splitlines()))
    assert len(score_rows) == 3241 and {row["imageSHA256"] for row in score_rows} == set(source)
    threshold, temperature = candidate["passThreshold"], candidate["temperature"]
    result = {}
    for name, desired, test, target in (
        ("pass", "GOOD", lambda r,p: not r["label"] and r["goodPrediction"] and p < threshold*.6, threshold*.35),
        ("above", "GOOD", lambda r,p: not r["label"] and r["goodPrediction"] and threshold*2 < p < .4, .12),
        ("defect", "DEFECT", lambda r,p: r["label"] and not r["goodPrediction"] and p > .9, .98),
    ):
        valid = [(abs(probability(row["margin"], temperature)-target), row["imageSHA256"], row)
                 for row in score_rows if test(row, probability(row["margin"], temperature))]
        _, digest, score = min(valid)
        row = source[digest]
        with open(row["imageArchive"], "rb") as archive:
            blob = os.pread(archive.fileno(), row["size"], row["offset"])
        if sha256(blob).hexdigest() != digest:
            raise ValueError("Fixture file differs from frozen evidence")
        result[name] = dict(data=blob, id=digest, expected=desired,
                            raw=score["rawScore"], calibrated=probability(score["margin"], temperature))
    return result


def gate(response, candidate, *, active, ready, calibrator=CALIBRATOR):
    # Mirrors the established backend guard for isolated contract verification.
    calibrated = response["calibratedDefectProbability"]
    return ("AUTO_PASS" if response["predictedQuality"] == "GOOD" and active and ready
            and response["modelVersion"] == candidate["modelVersion"]
            and response["calibratorVersion"] == calibrator and calibrated is not None
            and calibrated <= candidate["passThreshold"] else "REVIEW")


def smoke(api, project, engine, runtime, candidate):
    photos = fixtures(project, candidate)

    class FixtureOrigin(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            sample = photos.get(self.path.removeprefix("/"))
            if sample is None:
                self.send_error(404)
                return
            data = sample["data"]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    report = {}
    with api.running(ThreadingHTTPServer(("127.0.0.1", 0), FixtureOrigin)) as origin:
        with api.running(api.new_server(("127.0.0.1", 0), engine, [origin], runtime / "smoke_requests")) as base:
            status, inventory, _ = api.request(base + "/internal/v1/models")
            if status != 200 or inventory != {"data": [dict(partCode="FRAME", modelVersion=api.MODEL_VERSION,
                                                             calibratorVersion=CALIBRATOR, loadable=True)]}:
                raise ValueError("Calibrated inventory differs from contract")
            for case, photo in photos.items():
                status, response, _ = api.request(base + "/internal/v1/predict", dict(
                    inspectionId=f"frame-policy-{case}", partCode="FRAME", requestedModelVersion=api.MODEL_VERSION,
                    imageUrl=f"{origin}/{case}"))
                if (status != 200 or response["predictedQuality"] != photo["expected"]
                        or response["calibratorVersion"] != CALIBRATOR
                        or abs(response["rawDefectProbability"]-photo["raw"]) > .002
                        or abs(response["calibratedDefectProbability"]-photo["calibrated"]) > .002):
                    raise ValueError(f"Serving and offline scores differ for {case}")
                cam = response["gradcam"]
                if photo["expected"] == "GOOD":
                    if cam is not None:
                        raise ValueError("GOOD response must omit CAM")
                else:
                    if not cam or (cam["status"], cam["format"], cam["targetClass"]) != ("GENERATED", "jpeg", "DEFECT"):
                        raise ValueError("Expected a DEFECT LayerCAM JPEG")
                    decoded = base64.b64decode(cam["imageBase64"], validate=True)
                    with Image.open(io.BytesIO(photo["data"])) as img, Image.open(io.BytesIO(decoded)) as overlay:
                        if overlay.format != "JPEG" or overlay.size != ImageOps.exif_transpose(img).size:
                            raise ValueError("LayerCAM image dimensions or type differ")
                        overlay.verify()
                active = gate(response, candidate, active=True, ready=True)
                inactive = gate(response, candidate, active=False, ready=True)
                unready = gate(response, candidate, active=True, ready=False)
                mismatch = gate(response, candidate, active=True, ready=True, calibrator="other")
                if active != ("AUTO_PASS" if case == "pass" else "REVIEW") or any(
                    action != "REVIEW" for action in (inactive, unready, mismatch)
                ):
                    raise ValueError(f"Unexpected gate for {case}")
                report[case] = dict(imageSHA256=photo["id"], aiPrediction=response["predictedQuality"],
                                    raw=response["rawDefectProbability"], calibrated=response["calibratedDefectProbability"],
                                    testPolicyActive=active, testPolicyInactive=inactive, testPolicyUnready=unready,
                                    testWrongCalibrator=mismatch, camStatus=cam["status"] if cam else None)
    return dict(inventory=inventory, checks=report, candidateSHA256=POLICY_SHA,
                passThreshold=candidate["passThreshold"], camLayer=api.CAM_LAYER, camMethod="LayerCAM", camGrid=[28,28], policyScope="local contract harness only",
                deployedBackendChanged=False)


def main(project, runtime, host, port, origin, smoke_only=False):
    raw = (project / POLICY_SOURCE / "frozen_candidate.json").read_bytes()
    candidate = json.loads(raw)
    if sha256(raw).hexdigest() != POLICY_SHA or candidate["ready"] or candidate["active"]:
        raise ValueError("Unexpected or active policy candidate")
    api = prepare_variant(project, runtime, candidate)
    api.load_shared_api(project, runtime)
    if candidate["modelVersion"] != api.MODEL_VERSION or candidate["checkpointSHA256"] != api.FRAME_SHA256:
        raise ValueError("Candidate and API version differ")
    engine = api.create_engine(project)
    report = smoke(api, project, engine, runtime, candidate)
    (runtime / "smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if smoke_only:
        return
    server = api.new_server((host, port), engine, [origin], runtime / "requests")
    print("FRAME calibrated trial ready", server.server_port, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--smoke-only", action="store_true")
    args = parser.parse_args()
    main(args.project, args.runtime, args.host, args.port, args.origin, args.smoke_only)
