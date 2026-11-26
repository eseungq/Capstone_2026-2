"""Serve the frozen linkage checkpoint with the fixed-pin trial's LayerCAM path."""

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageOps
import torch

from check_cowl_linkage_miss_cam import digest
from cowl_pin_trial_api import LAYER, PART, PinEngine, load_shared_api, request, running
from evaluate_cowl_linkage_official import read_csv, sha, write_json

MODEL_SHA = "458a07d4645324eefce8ba7d0e921a26b610c5b543c2dd5d6e2ff32e36bb28af"


VERSION = "cowl-cover-unified-swin-tiny-e08-458a07d46453-dev"


class LinkageEngine(PinEngine):
    def __init__(self, run):
        self.checkpoint_path = run / "best.pt"
        self.expected_checkpoint_sha256 = MODEL_SHA
        self.model, self.config = load_model(run)
        assert self.config["prediction_cutoff"] == .5
        self.metadata = dict(model_version=VERSION, model_sha256=MODEL_SHA, model_name=self.config["model_name"],
                             checkpoint_epoch=8, scope="UNIFIED_FIXED_PIN_LINKAGE", device="cpu", cam_method="LayerCAM",
                             gradcam_layer=LAYER, gradcam_palette="JET", gradcam_alpha=.5)


def make_server(engine, runtime, origins, port):
    from ai_api.e02_integration.handler import Handler
    from ai_api.e02_integration.serve import IntegrationService
    from ai_api.server import Downloader, Server

    class LinkageService(IntegrationService):
        part_code = PART

        def model_inventory(self):
            data = super().model_inventory()
            data["models"][0]["partCode"] = self.part_code
            return data

    httpd = Server(("127.0.0.1",port),Handler)
    httpd.service = LinkageService(engine,VERSION,Downloader(origins),runtime,cam_format="jpeg",jpeg_quality=90)
    return httpd



def load_model(run):
    import numpy as np
    import timm
    from frame_model.cam_review import verify_metadata
    checkpoint = run/"best.pt"
    meta = json.loads((run/"run_config.json").read_bytes())
    assert sha(checkpoint)==MODEL_SHA
    config = meta["config"]
    assert config["image_size"]==224 and config["inspection_types"]==["고정핀 불량","연계 불량"]
    with torch.serialization.safe_globals([np._core.multiarray._reconstruct,np.ndarray,np.dtype,np.dtypes.UInt32DType]):
        ck=torch.load(checkpoint,map_location="cpu",weights_only=True)
    assert ck["epoch"]==8
    verify_metadata(ck["metadata"],meta)
    model=timm.create_model(config["model_name"],pretrained=False,num_classes=2)
    model.load_state_dict(ck["model_state_dict"],strict=True)
    return model.eval(),config


def fixtures(audit, evaluation, cam_zip):
    from evaluate_cowl_unified import PIN, LINK, reference
    report=json.loads((evaluation/"comparison_report.json").read_bytes())
    assert report["epoch"]==8 and report["checkpoint_sha256"]==MODEL_SHA
    with ZipFile(cam_zip) as archive:
        cam=json.loads(archive.read("cam_report.json"))
    assert cam["checkpoint_sha256"]==MODEL_SHA and len(cam["results"])==48
    cases={}
    for role,kind,paths in (("fixed_pin","고정핀",PIN),("linkage","연결부",LINK)):
        rows=reference(role,paths)[0]
        score_path=evaluation/f"{role}_scores.csv"
        assert sha(score_path)==report["per_type"][role]["unified_scores_sha256"]
        scores={r["image_id"]:r for r in read_csv(score_path)}
        selected=max((r for r in cam["results"] if r["kind"]==kind and
                      r["methods"]["LayerCAM 28×28"].get("inside")),key=lambda r:r["raw_score"])
        for case,ident in [(role.upper(),selected["image_id"])] + ([
                ("GOOD",next(i for i,r in sorted(scores.items()) if r["label"]==r["prediction"]=="0"
                             and not rows[i]["cross_near"] and float(r["raw_score"])<.01))] if role=="fixed_pin" else []):
            row,pred=rows[ident],scores[ident]
            expected="0" if case=="GOOD" else "1"
            assert row["class_id"]==pred["label"]==pred["prediction"]==expected and not row["cross_near"]
            with Path(row["image_archive"]).open("rb") as stream:
                blob=os.pread(stream.fileno(),row["size"],row["offset"])
            assert digest(blob)==row["image_sha256"]==pred["image_sha256"]
            cases[case]=blob,ident,float(pred["raw_score"])
    return cases


def smoke(engine, runtime, samples):
    class Fixture(BaseHTTPRequestHandler):
        def log_message(self,*_args):
            pass

        def do_GET(self):
            case = samples.get(self.path.removeprefix("/"))
            if case is None:
                self.send_error(404)
                return
            data = case[0]
            self.send_response(200)
            self.send_header("Content-Type","image/jpeg")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    with running(ThreadingHTTPServer(("127.0.0.1",0),Fixture)) as origin:
        with running(make_server(engine,runtime/"requests",[origin],0)) as api:
            status,inventory,headers = request(api+"/internal/v1/models")
            expected = dict(partCode=PART,modelVersion=VERSION,loadable=True,calibratorVersion=None)
            assert status==200 and inventory=={"data":[expected]} and headers.get("X-AI-Model-SHA256")==MODEL_SHA
            outputs,errors = {},{}
            endpoint = api+"/internal/v1/predict"
            for case,(blob,ident,reference) in samples.items():
                label = "GOOD" if case == "GOOD" else "DEFECT"
                payload = dict(partCode=PART,requestedModelVersion=VERSION,
                               inspectionId=f"cowl-unified-{case.lower()}",imageUrl=f"{origin}/{case}")
                status,body,_ = request(endpoint,payload)
                assert status==200 and body["predictedQuality"]==label, (status,body)
                assert body["modelVersion"]==VERSION and body["inspectionId"]==payload["inspectionId"]
                assert body["calibratedDefectProbability"] is None and body["calibratorVersion"] is None
                assert abs(body["rawDefectProbability"]-reference)<=.002
                cam = body["gradcam"]
                result = {k:body[k] for k in ("predictedQuality","rawDefectProbability","inferenceTimeMs")}
                if label=="GOOD":
                    assert cam is None
                    result["gradcam"] = None
                else:
                    assert (cam["status"],cam["targetClass"],cam["format"])==("GENERATED","DEFECT","jpeg")
                    jpeg = base64.b64decode(cam["imageBase64"],validate=True)
                    with Image.open(io.BytesIO(blob)) as source, Image.open(io.BytesIO(jpeg)) as overlay:
                        assert overlay.format=="JPEG" and overlay.size==ImageOps.exif_transpose(source).size
                        result["gradcam"] = dict(status=cam["status"],format=cam["format"],
                                                 width=overlay.width,height=overlay.height,bytes=len(jpeg))
                        overlay.verify()
                    (runtime/f"smoke_{case.lower()}_layercam.jpg").write_bytes(jpeg)
                outputs[case] = dict(result,image_id=ident)
            for edit,expected_error in (({"partCode":"DOOR"},(422,"UNSUPPORTED_PART")),
                                        ({"requestedModelVersion":"cowl-cover-fixed-pin-swin-tiny-e08-5a581b8b727d-dev"},(409,"MODEL_VERSION_MISMATCH")),
                                        ({"imageUrl":"http://127.0.0.1:1/DEFECT"},(422,"IMAGE_ORIGIN_NOT_ALLOWED"))):
                status,body,_ = request(endpoint,payload|edit)
                assert (status,body["error"]["code"])==expected_error, (status,body)
                errors[expected_error[1]] = status
    write_json(runtime/"smoke.json",dict(status="passed",scope="UNIFIED_FIXED_PIN_LINKAGE",device="cpu",cam_method="LayerCAM 28×28",
                                        cam_display="JET 50%",inventory=inventory,samples=outputs,errors=errors,
                                        checkpoint_sha256=MODEL_SHA,calibrated=False,backend_registered=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("smoke","serve"))
    parser.add_argument("run",type=Path)
    parser.add_argument("runtime",type=Path)
    parser.add_argument("--audit",type=Path)
    parser.add_argument("--evaluation",type=Path)
    parser.add_argument("--cam-zip",type=Path)
    parser.add_argument("--port",type=int,default=8778)
    parser.add_argument("--image-origin",action="append",default=[])
    args = parser.parse_args()
    args.runtime.mkdir(parents=True,exist_ok=True)
    load_shared_api(Path.cwd(),args.runtime)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    engine = LinkageEngine(args.run)
    if args.mode=="smoke":
        smoke(engine,args.runtime,fixtures(args.audit,args.evaluation,args.cam_zip))
    else:
        httpd = make_server(engine,args.runtime/"requests",args.image_origin,args.port)
        print(f"COWL_UNIFIED_API_READY 127.0.0.1:{args.port} {VERSION}",flush=True)
        httpd.serve_forever()


if __name__=="__main__":
    main()
