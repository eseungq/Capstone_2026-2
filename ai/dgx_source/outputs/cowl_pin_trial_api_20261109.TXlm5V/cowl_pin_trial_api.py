"""Isolated fixed-pin CPU trial using the shared backend-v4 wire contract."""

import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageOps
import timm
import torch
from torchvision.transforms import functional as TF

from check_cowl_pin_cam import EXPECTED, LAYERS, position, read_csv, sha, write_json


ROOT = Path.cwd()
RUN = ROOT / "outputs/cowl_pin_training/train_20261109T080932_751236Z"
PART = "COWL_COVER"
VERSION = "cowl-cover-fixed-pin-swin-tiny-e08-5a581b8b727d-dev"
LAYER = LAYERS["LayerCAM 28×28"]

sys.path.insert(0, str(ROOT / "outputs/frame_test_api_jet_20261108.0mqEHz"))
from frame_unified_test_api_20261107 import load_shared_api, request, running


class PinEngine:
    def __init__(self):
        self.checkpoint_path = RUN / "best.pt"
        self.expected_checkpoint_sha256 = EXPECTED
        artifacts = json.loads((RUN / "artifacts.json").read_bytes())
        config_path = RUN / "run_config.json"
        assert sha(self.checkpoint_path) == EXPECTED and sha(config_path) == artifacts["run_config.json"]
        run_metadata = json.loads(config_path.read_bytes())
        self.config = run_metadata["config"]
        assert (self.config["image_size"], self.config["prediction_cutoff"], self.config["class_mapping"]) == (
            224, 0.5, {"GOOD": 0, "DEFECT": 1}
        )
        with torch.serialization.safe_globals([np._core.multiarray._reconstruct, np.ndarray, np.dtype, np.dtypes.UInt32DType]):
            checkpoint = torch.load(self.checkpoint_path, map_location="cpu", weights_only=True)
        assert checkpoint["epoch"] == 8
        from frame_model.cam_review import verify_metadata
        verify_metadata(checkpoint["metadata"], run_metadata)
        self.model = timm.create_model(self.config["model_name"], pretrained=False, num_classes=2)
        self.model.load_state_dict(checkpoint["model_state_dict"], strict=True)
        self.model.eval()
        self.metadata = dict(model_version=VERSION, model_sha256=EXPECTED, model_name=self.config["model_name"],
                             checkpoint_epoch=8, scope="FIXED_PIN", device="cpu", cam_method="LayerCAM",
                             gradcam_layer=LAYER, gradcam_palette="JET", gradcam_alpha=0.5)

    def tensor(self, image):
        padded = ImageOps.pad(image, (224, 224), method=Image.Resampling.BICUBIC, color=(124, 116, 104))
        return TF.normalize(TF.to_tensor(padded), self.config["mean"], self.config["std"]).unsqueeze(0)

    @staticmethod
    def read(path):
        with Image.open(path) as image:
            return ImageOps.exif_transpose(image).convert("RGB")

    def predict(self, path):
        started = time.perf_counter()
        with torch.inference_mode():
            logits = self.model(self.tensor(self.read(path)))
            if logits.shape != (1, 2) or not torch.isfinite(logits).all():
                raise ValueError("Invalid logits")
            score = logits.softmax(-1)[0, 1].item()
        return dict(predicted_class=int(score >= 0.5), raw_defect_score=score,
                    processing_ms=(time.perf_counter()-started)*1000)

    def explain(self, path, dest, cls):
        if cls != 1:
            raise ValueError("CAM targets DEFECT")
        image = self.read(path)
        parameters = tuple((id(p), p._version) for p in self.model.state_dict(keep_vars=True).values())
        captured = {}
        hook = self.model.get_submodule(LAYER).register_forward_hook(
            lambda _m, _i, output: captured.update(activation=output))
        try:
            with torch.enable_grad():
                logits = self.model(self.tensor(image))
                a = captured["activation"]
                assert tuple(a.shape[1:3]) == (28, 28) and torch.isfinite(logits).all()
                g, = torch.autograd.grad(logits[0, 1], a)
                raw = (g.relu()*a).sum(-1).relu().detach()[0].numpy()
        finally:
            hook.remove()
        _, visible = position(raw, image, [])
        if visible is not None:
            intensity = np.uint8(np.clip(np.asarray(Image.fromarray(visible).resize(
                image.size, Image.Resampling.BILINEAR)), 0, 1)*255)
            heat = cv2.cvtColor(cv2.applyColorMap(intensity, cv2.COLORMAP_JET), cv2.COLOR_BGR2RGB)
            Image.fromarray(cv2.addWeighted(np.asarray(image), .5, heat, .5, 0)).save(dest / "cam1.png")
        unchanged = parameters == tuple((id(p), p._version) for p in self.model.state_dict(keep_vars=True).values())
        return dict(state_unchanged=unchanged, eval_mode=not self.model.training, constant=visible is None,
                    raw_min=float(raw.min()), raw_max=float(raw.max()))


def server(host, port, engine, runtime, origins):
    from ai_api.e02_integration.handler import Handler
    from ai_api.e02_integration.serve import IntegrationService
    from ai_api.server import Downloader, Server

    class PinService(IntegrationService):
        part_code = PART

        def model_inventory(self):
            data = super().model_inventory()
            data["models"][0]["partCode"] = self.part_code
            return data

    httpd = Server((host, port), Handler)
    httpd.service = PinService(engine, VERSION, Downloader(origins), runtime, cam_format="jpeg", jpeg_quality=90)
    return httpd


def smoke(engine, runtime, replication):
    report = json.loads(replication.read_bytes())
    assert report["checkpointSHA256"] == EXPECTED
    tps = report["byCohort"]["TP"]
    assert tps["LayerCAM 28×28"]["peakInside"] > tps["Grad-CAM 14×14"]["peakInside"]
    defect = next(r["image_id"] for r in report["results"] if r["cohort"] == "TP" and r["LayerCAM 28×28"]["inside"])
    predictions = {r["image_id"]: r for r in read_csv(RUN / "best_model_selection_predictions.csv")}
    good = next(i for i, r in predictions.items()
                if r["actual"] == r["predicted"] == "0" and float(r["raw_defect_score"]) < .05)
    used = {r["image_id"]: r for r in read_csv(RUN / "model_selection_used.csv")}
    fixtures = {}
    for kind, ident in (("GOOD", good), ("DEFECT", defect)):
        row = used[ident]
        with Path(row["image_archive"]).open("rb") as archive:
            blob = os.pread(archive.fileno(), int(row["size"]), int(row["offset"]))
        assert hashlib.sha256(blob).hexdigest() == row["image_sha256"]
        fixtures[kind] = blob, ident

    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            item = fixtures.get(self.path[1:])
            if item is None:
                self.send_error(404)
                return
            data = item[0]
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    samples, errors = {}, {}
    with running(ThreadingHTTPServer(("127.0.0.1", 0), Fixture)) as origin:
        with running(server("127.0.0.1", 0, engine, runtime / "requests", [origin])) as url:
            status, inventory, headers = request(url+"/internal/v1/models")
            assert status == 200 and headers.get("X-AI-Model-SHA256") == EXPECTED, (status, inventory)
            assert inventory == {"data": [dict(partCode=PART, modelVersion=VERSION, loadable=True, calibratorVersion=None)]}
            endpoint = url+"/internal/v1/predict"
            for kind, (blob, ident) in fixtures.items():
                payload = dict(partCode=PART, requestedModelVersion=VERSION, inspectionId=f"cowl-pin-{kind.lower()}",
                               imageUrl=f"{origin}/{kind}")
                status, body, _ = request(endpoint, payload)
                assert status == 200 and body["predictedQuality"] == kind and body["modelVersion"] == VERSION
                assert body["inspectionId"] == payload["inspectionId"]
                assert body["calibratedDefectProbability"] is None and body["calibratorVersion"] is None
                assert abs(body["rawDefectProbability"] - float(predictions[ident]["raw_defect_score"])) <= .002
                cam = body["gradcam"]
                sample = {k: body[k] for k in ("predictedQuality","rawDefectProbability","inferenceTimeMs")}
                if kind == "GOOD":
                    assert cam is None
                    sample["gradcam"] = None
                else:
                    assert (cam["status"], cam["targetClass"], cam["format"]) == ("GENERATED", "DEFECT", "jpeg")
                    jpeg = base64.b64decode(cam["imageBase64"], validate=True)
                    with Image.open(io.BytesIO(blob)) as source, Image.open(io.BytesIO(jpeg)) as overlay:
                        assert overlay.format == "JPEG" and overlay.size == ImageOps.exif_transpose(source).size
                        sample["gradcam"] = dict(status=cam["status"], format=cam["format"], width=overlay.width,
                                                 height=overlay.height, bytes=len(jpeg))
                        overlay.verify()
                samples[kind] = sample
            for change, expected in (({"partCode": "DOOR"}, (422, "UNSUPPORTED_PART")),
                                     ({"requestedModelVersion": "wrong"}, (409, "MODEL_VERSION_MISMATCH")),
                                     ({"imageUrl": "http://127.0.0.1:1/DEFECT"}, (422, "IMAGE_ORIGIN_NOT_ALLOWED"))):
                status, body, _ = request(endpoint, payload | change)
                assert (status, body["error"]["code"]) == expected, (status, body)
                errors[expected[1]] = status
    write_json(runtime / "smoke.json", dict(status="passed", device="cpu", scope="FIXED_PIN", inventory=inventory,
                                           samples=samples, errors=errors, camMethod="LayerCAM 28×28",
                                           calibrated=False, backendRegistered=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "serve"))
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--replication", type=Path)
    parser.add_argument("--port", type=int, default=8776)
    parser.add_argument("--image-origin", action="append", default=[])
    args = parser.parse_args()
    args.runtime.mkdir(parents=True, exist_ok=True)
    load_shared_api(ROOT, args.runtime)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    engine = PinEngine()
    if args.mode == "smoke":
        smoke(engine, args.runtime, args.replication)
    else:
        httpd = server("127.0.0.1", args.port, engine, args.runtime / "requests", args.image_origin)
        print(f"COWL_PIN_API_READY 127.0.0.1:{args.port} {VERSION}", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
