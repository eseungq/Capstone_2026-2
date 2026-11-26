"""Isolated e02 DOOR temperature-calibration trial over the existing HTTP contract."""

import argparse
from contextvars import ContextVar
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
from pathlib import Path
import sys
import time
from threading import Thread
from contextlib import contextmanager
from urllib.request import Request, urlopen
import base64


POLICY_SHA = "fea7d1256bce7d5ee6ffc400f19f17bb591cadb831477883e7b202d4fc4150e0"
REPORT_SHA = "3bbec4ae98396a530cf12c3117aed2d1f527d55613b0f7eecda8448ba6dd682a"
CALIBRATOR = "door-e02-temperature-fea7d1256bce-demo"
THRESHOLD = 0.30
MARGIN = ContextVar("door_trial_logit_margin", default=None)


def calibrated_probability(margin, temperature):
    scaled = margin / temperature
    exponential = math.exp(-abs(scaled))
    return 1/(1+exponential) if scaled >= 0 else exponential/(1+exponential)


def load_frozen(study):
    policy_bytes, report_bytes = ((study / name).read_bytes() for name in ("frozen_policy.json", "report.json"))
    if (sha256(policy_bytes).hexdigest(), sha256(report_bytes).hexdigest()) != (POLICY_SHA, REPORT_SHA):
        raise ValueError("The offline calibration or its evaluation evidence differs")
    policy, report = map(json.loads, (policy_bytes, report_bytes))
    if report["policy"] != policy or policy["ready"] or policy["active"]:
        raise ValueError("Expected an inactive offline calibration artifact")
    return policy, report


def load_engine(project, study, policy):
    sys.path[:0] = [str(project), str(study)]
    from cars_ad_e02_pilot import EXPECTED_SHA256, EXPECTED_VERSION, load_engine, validate_candidate
    from prototype.engine import Engine, sha
    import numpy as np
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("DGX CUDA is required")
    torch.set_num_threads(2)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    manifest, run, cfg = validate_candidate()
    if (policy["modelVersion"], policy["checkpointSHA256"]) != (EXPECTED_VERSION, EXPECTED_SHA256):
        raise ValueError("Offline artifact is for another model")
    checkpoint = run / "best.pt"
    if sha(checkpoint) != EXPECTED_SHA256:
        raise ValueError("e02 checkpoint differs")
    base = load_engine(manifest, run, cfg)

    class DoorEngine(Engine):
        def __init__(self):
            self.torch, self.np = torch, np
            self.model = base.model.float().cuda().eval()
            self.dataset = base.dataset
            self.checkpoint_path = checkpoint
            self.expected_checkpoint_sha256 = EXPECTED_SHA256
            self.metadata = dict(model_version=EXPECTED_VERSION, model_sha256=EXPECTED_SHA256,
                                 model_name=cfg["config"]["model_name"], checkpoint_epoch=2,
                                 device=torch.cuda.get_device_name(0), torch=torch.__version__)

        def predict(self, path):
            torch.cuda.synchronize()
            start = time.perf_counter()
            tensor = self.tensor(path).unsqueeze(0).cuda()
            with torch.inference_mode():
                logits = self.model(tensor)
                if logits.shape != (1, 2) or not torch.isfinite(logits).all():
                    raise ValueError("Invalid e02 logits")
                score = logits.softmax(dim=1)[0, 1].item()
                MARGIN.set((logits[0, 1] - logits[0, 0]).item())
            torch.cuda.synchronize()
            return dict(predicted_class=int(score >= .5), raw_defect_score=score,
                        processing_ms=(time.perf_counter()-start)*1000, model=self.metadata)

    return DoorEngine()


def server(address, engine, allowed, runtime, policy):
    from ai_api import contract
    from ai_api.e02_integration.handler import Handler
    from ai_api.e02_integration.serve import IntegrationService
    from ai_api.server import Downloader, Server

    class DoorService(IntegrationService):
        def predict(self, body, *, request_id=None):
            token = MARGIN.set(None)
            try:
                result = super().predict(body, request_id=request_id)
                margin = MARGIN.get()
                if margin is None or not math.isfinite(margin):
                    raise contract.Failure("INFERENCE_FAILED", 503)
                result["calibratedDefectProbability"] = calibrated_probability(margin, policy["temperature"])
                result["calibratorVersion"] = CALIBRATOR
                return result
            finally:
                MARGIN.reset(token)

    class DoorHandler(Handler):
        server_version = "DoorAI/calibrated-trial"

        def send(self, status, body, **kwargs):
            if self.path == "/internal/v1/models" and status == 200:
                body = {"data": [dict(row, calibratorVersion=CALIBRATOR if row["loadable"] else None)
                                 for row in body["data"]]}
            return super().send(status, body, **kwargs)

    http = Server(address, DoorHandler)
    http.service = DoorService(engine, policy["modelVersion"], Downloader(allowed), runtime,
                               cam_format="jpeg", jpeg_quality=90)
    return http


@contextmanager
def running(http):
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}"
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def request(url, payload=None):
    req = (Request(url, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
           if payload is not None else Request(url))
    with urlopen(req, timeout=40) as response:
        return response.status, json.load(response)


def gate(response, *, ready, active, model, calibrator):
    probability = response["calibratedDefectProbability"]
    return ("AUTO_PASS" if response["predictedQuality"] == "GOOD" and ready and active
            and response["modelVersion"] == model and response["calibratorVersion"] == calibrator
            and probability is not None and probability <= THRESHOLD else "REVIEW")


def smoke(study, report, policy, engine, runtime):
    from PIL import Image, ImageOps
    rows = {row["id"]: row for row in report["final"]["rows"]}
    defect = min((row for row in rows.values() if row["decision"] == "DEFECT_DOOR"
                  and row["prediction"] == "DEFECT"), key=lambda row: abs(row["probability"]-.98))
    fixtures = {"pass": rows["J69"], "above": rows["H188"], "defect": defect}
    blobs = {}
    for role, row in fixtures.items():
        raw = (study / row["image"]).read_bytes()
        if sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError(f"Fixture changed: {role}")
        blobs[role] = raw

    class Origin(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            data = blobs.get(self.path.removeprefix("/"))
            if data is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    cases = {}
    version = policy["modelVersion"]
    with running(ThreadingHTTPServer(("127.0.0.1", 0), Origin)) as origin:
        with running(server(("127.0.0.1", 0), engine, [origin], runtime/"smoke_requests", policy)) as base:
            status, models = request(base+"/internal/v1/models")
            if status != 200 or models != {"data":[dict(partCode="DOOR", modelVersion=version,
                                                        calibratorVersion=CALIBRATOR, loadable=True)]}:
                raise ValueError("Trial model listing differs")
            for role, row in fixtures.items():
                status, result = request(base+"/internal/v1/predict", dict(
                    inspectionId=f"door-policy-{role}", partCode="DOOR", requestedModelVersion=version,
                    imageUrl=f"{origin}/{role}"
                ))
                if (status != 200 or result["predictedQuality"] != row["prediction"]
                        or result["calibratorVersion"] != CALIBRATOR
                        or abs(result["rawDefectProbability"]-row["probability"]) > .002
                        or abs(result["calibratedDefectProbability"]-row["experimentalDefectProbability"]) > .002):
                    raise ValueError(f"Offline and API scores differ for {role}")
                cam = result["gradcam"]
                if role != "defect" and cam is not None:
                    raise ValueError("GOOD unexpectedly generated CAM")
                if cam and cam["status"] == "GENERATED":
                    binary = base64.b64decode(cam["imageBase64"], validate=True)
                    with Image.open(io.BytesIO(blobs[role])) as original, Image.open(io.BytesIO(binary)) as overlay:
                        if overlay.format != "JPEG" or overlay.size != ImageOps.exif_transpose(original).size:
                            raise ValueError("Unexpected CAM dimensions")
                        overlay.verify()
                elif role == "defect" and (not cam or cam["status"] != "NO_ACTIVATION"):
                    raise ValueError("DEFECT CAM contract did not produce an image or NO_ACTIVATION")
                active = gate(result, ready=True, active=True, model=version, calibrator=CALIBRATOR)
                inactive = gate(result, ready=True, active=False, model=version, calibrator=CALIBRATOR)
                unready = gate(result, ready=False, active=True, model=version, calibrator=CALIBRATOR)
                mismatch = gate(result, ready=True, active=True, model=version, calibrator="another-calibrator")
                missing = gate(dict(result, calibratedDefectProbability=None), ready=True, active=True,
                               model=version, calibrator=CALIBRATOR)
                if active != ("AUTO_PASS" if role == "pass" else "REVIEW") or {
                    inactive, unready, mismatch, missing
                } != {"REVIEW"}:
                    raise ValueError(f"Unexpected demo policy result: {role}")
                cases[role] = dict(sampleId=row["id"], actual=row["decision"],
                                   imageSHA256=row["sha256"], prediction=result["predictedQuality"],
                                   raw=result["rawDefectProbability"], calibrated=result["calibratedDefectProbability"],
                                   camStatus=cam["status"] if cam else None, activeTestPolicy=active,
                                   inactiveTestPolicy=inactive, unreadyTestPolicy=unready,
                                   incompatibleCalibrator=mismatch, missingProbability=missing)
    return dict(models=models, threshold=THRESHOLD, temperature=policy["temperature"], policySHA256=POLICY_SHA,
                backendScope="Isolated local test of the existing backend rule", runtime=engine.metadata, cases=cases)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("study", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--origin", required=True)
    args = parser.parse_args()
    policy, offline = load_frozen(args.study)
    engine = load_engine(args.project, args.study, policy)
    evidence = smoke(args.study, offline, policy, engine, args.runtime)
    (args.runtime/"smoke.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n")
    http = server((args.host, args.port), engine, [args.origin], args.runtime/"requests", policy)
    print(f"DOOR calibrated trial ready {http.server_port}", flush=True)
    try:
        http.serve_forever()
    finally:
        http.server_close()
