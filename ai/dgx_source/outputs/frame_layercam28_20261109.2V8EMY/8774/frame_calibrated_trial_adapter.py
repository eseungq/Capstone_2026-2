"""Serve the frozen unified FRAME checkpoint using the existing v4 HTTP contract."""

import argparse
import base64
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import signal
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen


FRAME_SHA256 = "2425d7e46572e771421644ef3e255448a161da2b0d2258c09f9b9bb2ba643575"
CONFIG_SHA256 = "6a4f3de66a4342b8e5ed564e2839f6aa1a7da62df8c59e9cfe430ef8a5de02af"
MODEL_VERSION = "frame-swin-tiny-unified-e08-2425d7e46572-dev"
CAM_LAYER = "layers.1.blocks.1.norm1"
TEMPERATURE = 2.187761623949553
CALIBRATOR_VERSION = 'frame-e08-temperature-5d4299808c3e-demo'


def load_shared_api(project, runtime):
    # Only this process sees the adapted validator. The DOOR installation stays intact.
    overlay = runtime / "overlay" / "ai_api"
    overlay.mkdir(parents=True, exist_ok=True)
    source = (project / "ai_api/server.py").read_text()
    edits = {
        "def validate_request(body, version):": 'def validate_request(body, version, part_code="DOOR"):',
        "if body['partCode']!='DOOR':": "if body['partCode']!=part_code:",
        "validate_request(body,self.version)": 'validate_request(body,self.version,getattr(self,"part_code","DOOR"))',
    }
    for previous, replacement in edits.items():
        if source.count(previous) != 1:
            raise RuntimeError("Existing validation code changed; inspect it before adapting it")
        source = source.replace(previous, replacement)
    (overlay / "__init__.py").write_text("from pkgutil import extend_path\n__path__ = extend_path(__path__, __name__)\n")
    success_line = "            result=contract.success(ident,self.version,prediction,size,cam)"
    if source.count(success_line) != 1:
        raise RuntimeError("Existing response layout changed")
    source = source.replace(success_line, success_line + "\n            self.add_calibration(result,prediction)")
    (overlay / "server.py").write_text(source)
    backend = (project / "ai_api/backend_contract.py").read_text()
    field = "'calibratorVersion':None,'loadable':row['available'] is True"
    if backend.count(field) != 1:
        raise RuntimeError("Existing inventory layout changed")
    (overlay / "backend_contract.py").write_text(backend.replace(
        field, "'calibratorVersion':row.get('calibratorVersion'),'loadable':row['available'] is True"))
    diagnostics = (project / "ai_api/diagnostics.py").read_text()
    changes = {
        "def cam(engine,path,layer,dest,target='defect'):": "def cam(engine,path,layer,dest,target='defect',*,render_overlay=True):",
        "    values=np.clip(np.asarray(Image.fromarray(full[top:top+h,left:left+w]).resize(original.size,Image.Resampling.BILINEAR)),0,1)": (
            "    if not render_overlay:\n"
            "        info.update(paddingCrop=[left,top,left+w,top+h],displaySize=list(original.size))\n"
            "        return info,full,None\n"
            "    values=np.clip(np.asarray(Image.fromarray(full[top:top+h,left:left+w]).resize(original.size,Image.Resampling.BILINEAR)),0,1)"
        ),
    }
    for previous, replacement in changes.items():
        if diagnostics.count(previous) != 1:
            raise RuntimeError("Existing CAM renderer changed; inspect it before adapting it")
        diagnostics = diagnostics.replace(previous, replacement)
    (overlay / "diagnostics.py").write_text(diagnostics)
    sys.path.insert(0, str(overlay.parent))
    sys.path.insert(1, str(project))


def create_engine(project):
    import cv2
    import numpy as np
    import timm
    import torch
    from PIL import Image, ImageOps
    from torchvision.transforms import functional as TF
    from frame_layercam28 import cam
    from frame_model.cam_review import file_sha, verify_metadata
    from prototype.engine import Engine

    if not torch.cuda.is_available():
        raise RuntimeError("FRAME GPU unavailable")
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    run = project / "outputs/frame_training/comparison_train_20261022T160533_169658Z/unified"
    checkpoint_path, config_path = run / "best.pt", run / "run_config.json"
    if file_sha(checkpoint_path) != FRAME_SHA256 or file_sha(config_path) != CONFIG_SHA256:
        raise ValueError("Frozen FRAME checkpoint or configuration changed")
    cfg = json.loads(config_path.read_text())
    config = cfg["config"]
    if (config["image_size"], config["prediction_cutoff"], config["class_mapping"]) != (
        224, 0.5, {"GOOD": 0, "DEFECT": 1}
    ):
        raise ValueError("Unexpected FRAME input or class configuration")

    class FrameEngine(Engine):
        def __init__(self):
            self.torch, self.np = torch, np
            self.checkpoint_path = checkpoint_path
            self.expected_checkpoint_sha256 = FRAME_SHA256
            checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
            verify_metadata(checkpoint["metadata"], cfg)
            if checkpoint["epoch"] != 8:
                raise ValueError("Unexpected FRAME checkpoint epoch")
            self.model = timm.create_model(config["model_name"], pretrained=False, num_classes=2)
            self.model.load_state_dict(checkpoint["model_state_dict"], strict=True)
            del checkpoint
            self.model.float().cuda().eval()
            self.metadata = dict(model_version=MODEL_VERSION, model_sha256=FRAME_SHA256,
                                 model_name=config["model_name"], checkpoint_epoch=8,
                                 gradcam_layer=CAM_LAYER, gradcam_method="LayerCAM", gradcam_grid=[28,28], gradcam_palette="JET", gradcam_alpha=0.5,
                                 gpu=torch.cuda.get_device_name(0),
                                 versions={name: importlib.metadata.version(name) for name in cfg["versions"]},
                                 recorded_versions=cfg["versions"])

        def predict(self, path):
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

        def tensor(self, path):
            with Image.open(path) as original:
                display = ImageOps.exif_transpose(original).convert("RGB")
            padded = ImageOps.pad(display, (224, 224), method=Image.Resampling.BICUBIC,
                                  color=tuple(config["fill"]))
            return TF.normalize(TF.to_tensor(padded), config["mean"], config["std"])

        def explain(self, path, dest, cls):
            if cls != 1:
                raise ValueError("FRAME CAM must target DEFECT")
            before = {key: value.detach().cpu().clone() for key, value in self.model.state_dict().items()}
            info, full, _ = cam(self, path, CAM_LAYER, dest, target="defect", render_overlay=False)
            unchanged = all(torch.equal(before[key], value.detach().cpu())
                            for key, value in self.model.state_dict().items())
            if info["status"] == "GENERATED":
                with Image.open(path) as image:
                    original = ImageOps.exif_transpose(image).convert("RGB")
                left, top, right, bottom = info["paddingCrop"]
                scaled = Image.fromarray(full[top:bottom, left:right]).resize(
                    original.size, Image.Resampling.BILINEAR
                )
                intensity = np.uint8(np.clip(np.asarray(scaled), 0, 1) * 255)
                heat_bgr = cv2.applyColorMap(intensity, cv2.COLORMAP_JET)
                heat_rgb = cv2.cvtColor(heat_bgr, cv2.COLOR_BGR2RGB)
                blended = cv2.addWeighted(np.asarray(original), 0.5, heat_rgb, 0.5, 0)
                Image.fromarray(blended).save(dest / "cam1.png")
            return dict(state_unchanged=unchanged, eval_mode=not self.model.training,
                        raw_min=info["rawMin"], raw_max=info["rawMax"],
                        constant=info["status"] != "GENERATED")

    return FrameEngine()


def new_server(address, engine, origins, runtime):
    from ai_api.e02_integration.handler import Handler
    from ai_api.e02_integration.serve import IntegrationService
    from ai_api.server import Downloader, Server
    from frame_model.cam_review import file_sha

    class FrameService(IntegrationService):
        part_code = "FRAME"

        def add_calibration(self, result, prediction):
            z = prediction["defect_logit_margin"] / TEMPERATURE
            exp = math.exp(-abs(z))
            result["calibratedDefectProbability"] = 1/(1+exp) if z >= 0 else exp/(1+exp)
            result["calibratorVersion"] = CALIBRATOR_VERSION

        def model_inventory(self):
            try:
                ready = not self.engine.model.training and file_sha(self.engine.checkpoint_path) == FRAME_SHA256
            except OSError:
                ready = False
            return {"models": [dict(partCode=self.part_code, modelVersion=self.version,
                                    available=ready, modelSha256=FRAME_SHA256 if ready else None, calibratorVersion=CALIBRATOR_VERSION if ready else None)]}

    class FrameHandler(Handler):
        server_version = "FrameAI/development"

        def send(self, status, body, **kwargs):
            kwargs["headers"] = {**(kwargs.get("headers") or {}), "X-Frame-CAM-Method": "LayerCAM",
                                 "X-Frame-CAM-Grid": "28x28"}
            return super().send(status, body, **kwargs)

    server = Server(address, FrameHandler)
    server.service = FrameService(engine, MODEL_VERSION, Downloader(origins), runtime,
                                  cam_format="jpeg", jpeg_quality=90)
    return server


@contextmanager
def running(server):
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def request(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    try:
        response = urlopen(Request(url, data=data, headers=headers), timeout=40)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response), dict(response.headers)


def smoke(project, engine, runtime):
    from PIL import Image, ImageOps

    review = project / "outputs/frame_cam_review/20261026T144548_871522Z"
    selection = json.loads((review / "selection.json").read_text())
    prior = json.loads((review / "cam_report.json").read_text())
    samples = {}
    for item in selection["items"]:
        if item["id"] not in {"11", "08"}:
            continue
        row = item["source"]
        with Path(row["image_archive"]).open("rb") as archive:
            blob = os.pread(archive.fileno(), int(row["size"]), int(row["offset"]))
        if hashlib.sha256(blob).hexdigest() != row["image_sha256"]:
            raise ValueError("Fixture bytes changed")
        samples[item["id"]] = (blob, row)
    if set(samples) != {"11", "08"}:
        raise ValueError("Missing FRAME fixtures")

    class FixtureHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            sample = samples.get(self.path.removeprefix("/"))
            if sample is None:
                self.send_error(404)
                return
            blob = sample[0]
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

    results = {}
    with running(ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)) as origin:
        with running(new_server(("127.0.0.1", 0), engine, [origin], runtime / "smoke_requests")) as base:
            status, models, headers = request(base + "/internal/v1/models")
            expected = dict(partCode="FRAME", modelVersion=MODEL_VERSION, loadable=True, calibratorVersion=None)
            if status != 200 or models != {"data": [expected]} or headers.get("X-AI-Model-SHA256") != FRAME_SHA256:
                raise ValueError("FRAME inventory contract failed")
            endpoint = base + "/internal/v1/predict"
            for ident, (blob, row) in sorted(samples.items()):
                payload = dict(inspectionId=f"frame-smoke-{ident}", partCode="FRAME",
                               requestedModelVersion=MODEL_VERSION, imageUrl=f"{origin}/{ident}")
                status, body, headers = request(endpoint, payload)
                if status != 200:
                    raise RuntimeError(f"Fixture {ident} failed: {status} {body}")
                quality = "DEFECT" if int(row["class_id"]) else "GOOD"
                reference = prior["samples"][ident]["unified"]["single_score"]
                score = body["rawDefectProbability"]
                if (body["predictedQuality"], body["modelVersion"], body["inspectionId"]) != (
                    quality, MODEL_VERSION, payload["inspectionId"]
                ) or body["calibratedDefectProbability"] is not None or body["calibratorVersion"] is not None:
                    raise ValueError("FRAME prediction contract failed")
                if not math.isclose(score, reference, abs_tol=0.001):
                    raise ValueError(f"Fixture {ident} exceeds 0.1 percentage point GPU comparison tolerance")
                gradcam = body["gradcam"]
                cam_bytes = 0
                if quality == "GOOD":
                    if gradcam is not None:
                        raise ValueError("GOOD should omit Grad-CAM")
                else:
                    if (gradcam or {}).get("status") != "GENERATED" or gradcam.get("format") != "jpeg" or gradcam.get("targetClass") != "DEFECT":
                        raise ValueError(f"Expected GENERATED JPEG for fixture {ident}")
                    encoded = base64.b64decode(gradcam["imageBase64"], validate=True)
                    with Image.open(io.BytesIO(blob)) as source, Image.open(io.BytesIO(encoded)) as overlay:
                        if overlay.format != "JPEG" or overlay.size != ImageOps.exif_transpose(source).size:
                            raise ValueError("CAM JPEG dimensions or encoding differ")
                        overlay.verify()
                    cam_bytes = len(encoded)
                results[quality] = dict(sample=ident, rawDefectProbability=score, priorGpuSingle=reference,
                                        inferenceTimeMs=body["inferenceTimeMs"], traceId=headers["X-Trace-Id"],
                                        gradcamStatus=gradcam["status"] if gradcam else None, camBytes=cam_bytes)
            negative = [
                (dict(partCode="DOOR"), 422, "UNSUPPORTED_PART"),
                (dict(requestedModelVersion="wrong-version"), 409, "MODEL_VERSION_MISMATCH"),
                (dict(imageUrl="http://127.0.0.1:1/forbidden"), 422, "IMAGE_ORIGIN_NOT_ALLOWED"),
            ]
            for fields, expected_status, expected_code in negative:
                status, body, _ = request(endpoint, dict(payload, **fields))
                if status != expected_status or body["error"]["code"] != expected_code:
                    raise ValueError(f"Negative HTTP smoke failed: {status} {body}")
    return dict(models=models, samples=results, negativeCases=[code for _, _, code in negative],
                metadata=engine.metadata, camLayer=CAM_LAYER)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--image-origin", required=True)
    parser.add_argument("--smoke-only", action="store_true")
    args = parser.parse_args()
    load_shared_api(args.project, args.runtime)
    engine = create_engine(args.project)
    report = smoke(args.project, engine, args.runtime)
    (args.runtime / "smoke.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    if args.smoke_only:
        return
    server = new_server((args.host, args.port), engine, [args.image_origin], args.runtime / "requests")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    print(f"READY {args.host}:{args.port} {MODEL_VERSION}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
