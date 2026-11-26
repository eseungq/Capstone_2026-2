"""Compare forced DEFECT maps for the human-confirmed, visible linkage misses."""

from collections import Counter
import csv
import hashlib
from html import escape
import io
import json
from pathlib import Path
import sys
import tarfile
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from PIL import Image, ImageOps
import timm
import torch
from torchvision.transforms import functional as TF

from check_cowl_pin_cam import LAYERS, compute, paint, position, sha
from evaluate_cowl_linkage_official import CONFIG_SHA, MANIFEST_SHA, MODEL_SHA
from frame_model.cam_review import verify_metadata
from frame_model.check import read_image


def digest(data):
    return hashlib.sha256(data).hexdigest()


def photo(z, name, image):
    buf = io.BytesIO()
    image.save(buf,"JPEG",quality=93)
    z.writestr(name,buf.getvalue())


def boxes_from_source(blob, label, display_size):
    info, = label["images"]
    with Image.open(io.BytesIO(blob)) as raw:
        w,h = raw.size
        assert (w,h)==(info["width"],info["height"])
        orientation = raw.getexif().get(274,1)
    transform = {
        1: lambda x,y:(x,y), 2: lambda x,y:(w-x,y), 3: lambda x,y:(w-x,h-y), 4: lambda x,y:(x,h-y),
        5: lambda x,y:(y,x), 6: lambda x,y:(h-y,x), 7: lambda x,y:(h-y,w-x), 8: lambda x,y:(y,w-x),
    }[orientation]
    boxes = []
    for mark in label["annotations"]:
        assert mark["category_id"]==205 and mark["attributes"]["quality"]=="불량품"
        x,y,bw,bh = mark["bbox"]
        assert 0<=x<x+bw<=w and 0<=y<y+bh<=h
        a,b = transform(x,y)
        c,d = transform(x+bw,y+bh)
        rect = min(a,c),min(b,d),max(a,c),max(b,d)
        assert 0<=rect[0]<rect[2]<=display_size[0] and 0<=rect[1]<rect[3]<=display_size[1]
        boxes.append(rect)
    assert boxes
    return boxes


def load_model(run):
    config_path,checkpoint = run/"run_config.json",run/"best.pt"
    assert (sha(config_path),sha(checkpoint))==(CONFIG_SHA,MODEL_SHA)
    meta = json.loads(config_path.read_bytes())
    config = meta["config"]
    assert config["inspection_types"]==["연계 불량"] and config["image_size"]==224
    with torch.serialization.safe_globals([np._core.multiarray._reconstruct,np.ndarray,np.dtype,np.dtypes.UInt32DType]):
        ck = torch.load(checkpoint,map_location="cpu",weights_only=True)
    assert ck["epoch"]==9
    verify_metadata(ck["metadata"],meta)
    model = timm.create_model(config["model_name"],pretrained=False,num_classes=2)
    model.load_state_dict(ck["model_state_dict"],strict=True)
    return model.eval(),config


def main(run, audit, evaluated, stage):
    torch.set_num_threads(3)
    torch.set_num_interop_threads(1)
    prior = stage/"review_selection.json"
    review = json.loads((stage/"manual_review.json").read_bytes())
    entries = {r["id"]:r for r in json.loads(prior.read_bytes())}
    observations = {r["id"]:r for r in review["observations"]}
    assert review["schema"]=="cowl-linkage-fn-review-v1" and review["selectionSha256"]==sha(prior)
    assert len(entries)==len(observations)==len(review["observations"])==28 and entries.keys()==observations.keys()
    chosen = [r for key,r in sorted(entries.items()) if not r["cross_near"] and
              (observations[key]["visibility"],observations[key]["label"])==("224에서도 보임","불량 확인")]
    assert len(chosen)==16
    report = json.loads((evaluated/"evaluation_report.json").read_bytes())
    manifest = audit/"frozen_evaluation_manifest.json"
    assert report["checkpoint_sha256"]==MODEL_SHA and sha(manifest)==report["evaluation_manifest_sha256"]==MANIFEST_SHA
    manifest_rows = {r["image_id"]:r for r in json.loads(manifest.read_bytes())}
    errors_path = evaluated/"official_errors.csv"
    assert sha(errors_path)==report["error_list_sha256"]
    with errors_path.open(encoding="utf-8-sig",newline="") as f:
        errors = {r["image_id"]:r for r in csv.DictReader(f)}
    wanted = {r["image_id"] for r in chosen}
    label_path, = Path("downloads").glob("aihub/*/01.*/2.Validation/*/VL_6.*.tar")
    with tarfile.open(label_path) as tar:
        labels = {Path(m.name).stem:tar.extractfile(m).read() for m in tar if m.isfile() and
                  m.name.endswith(".json") and Path(m.name).stem in wanted}
    assert labels.keys()==wanted
    model, config = load_model(run)
    results, cards = [], []
    with ZipFile(stage/"linkage_miss_cam.zip","x",compression=ZIP_DEFLATED,compresslevel=1) as z:
        for record in chosen:
            ident, case = record["image_id"],record["id"]
            row,error,label = manifest_rows[ident],errors[ident],labels[ident]
            assert (error["label"],error["prediction"],error["cross_near"])==("1","0","False")
            assert row["class_id"]=="1" and row["excluded"] is None and not row["cross_near"]
            assert digest(label)==row["label_sha256"]==record["label_sha256"]
            assert row["image_sha256"]==record["image_sha256"]
            with Path(row["image_archive"]).open("rb") as archive:
                archive.seek(row["offset"])
                raw = archive.read(row["size"])
            assert digest(raw)==row["image_sha256"]
            display,padded = read_image(row)
            rects = boxes_from_source(raw,json.loads(label),display.size)
            score,maps = compute(model,TF.normalize(TF.to_tensor(padded),config["mean"],config["std"]))
            assert score<.5 and abs(score-float(error["raw_score"]))<=.002
            result = dict(case=case,image_id=ident,source_raw_score=float(error["raw_score"]),
                          cam_raw_score=score,boxes=rects,methods={})
            pics = [(f"{case}-original.jpg","원본 · 노란색은 AI-Hub 라벨 박스")]
            photo(z,"images/"+pics[0][0],paint(display,rects))
            for i,(method,raw_map) in enumerate(maps.items(),1):
                location,visible = position(raw_map,display,rects)
                if visible is None:
                    location.update(status="ZERO_MAP" if not np.any(raw_map) else "CONSTANT_MAP")
                result["methods"][method] = location
                verdict = ("최대점 박스 안" if location["inside"] else "최대점 박스 밖") if visible is not None else location["status"]
                name = f"{case}-cam-{i}.jpg"
                photo(z,"images/"+name,paint(display,rects,visible,location.get("peakXY")))
                pics.append((name,f"{method} · {verdict}"))
            body = "".join(f'<figure><a href="images/{name}"><img loading="lazy" src="images/{name}" alt="{escape(text)}"></a><figcaption>{escape(text)}</figcaption></figure>'
                           for name,text in pics)
            cards.append(f'<section id="{case}"><h2>{case} · 보정 전 불량 점수 {score:.2%}</h2><div class="grid">{body}</div></section>')
            results.append(result)
        summary = {}
        for method in LAYERS:
            states = [r["methods"][method] for r in results]
            summary[method] = dict(statuses=Counter(r["status"] for r in states),
                                   peak_inside=sum(r.get("inside",False) for r in states))
        report = dict(checkpoint_sha256=MODEL_SHA,epoch=9,scope="16 human-confirmed Validation false negatives visible at 224",
                      device="DGX CPU FP32",cam_target="DEFECT (forced for diagnosis)",layers=LAYERS,
                      review_sha256=sha(stage/"manual_review.json"),summary=summary,results=results)
        z.writestr("cam_report.json",json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
        head = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>연결부 미검출 CAM 진단</title><style>body{font:16px/1.5 system-ui;background:#edf2f7;color:#192c3e;max-width:1250px;margin:22px auto;padding:0 16px}section{background:#fff;border:1px solid #d8e2eb;border-radius:10px;padding:12px;margin:16px 0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}figure{margin:0}img{width:100%;height:220px;object-fit:contain;background:#19232b}figcaption{color:#334d61}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style><h1>연결부 미검출 16장 CAM 진단</h1><p>모델은 모두 정상으로 예측했습니다. 불량 클래스에 대한 CAM을 진단용으로 따로 계산했습니다. 노란색은 AI-Hub 라벨 박스, 흰 원은 최대 반응점입니다. 색상은 JET 50%입니다.</p>"""
        counts = "".join(f'<li>{escape(method)} · 최대 반응점이 박스 안에 들어온 사진 {data["peak_inside"]}/16장</li>'
                         for method,data in summary.items())
        z.writestr("review.html",head+"<ul>"+counts+"</ul>"+"".join(cards)+"</html>")
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main(*(Path(x).resolve(strict=True) for x in sys.argv[1:]))
