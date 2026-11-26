"""Compare fixed-pin explanation maps on frozen development photos."""

from collections import Counter
import csv
import hashlib
from html import escape
import io
import json
from pathlib import Path
import sys
import tarfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import timm
import torch
from torchvision.transforms import functional as TF

sys.path.insert(0, str(Path("outputs/frame_cam_methods_20261109.0Gw4Bt").resolve()))
from frame_cam_localization_20261109 import read_case
from frame_cam_compare_20261109 import position


LAYERS = {"Grad-CAM 14×14": "layers.2.blocks.5.norm1", "LayerCAM 28×28": "layers.1.blocks.1.norm1"}
EXPECTED = "5a581b8b727df3590a4a09a66c15a62b1f1a3ce297da6456d4460069502ea9d7"
COHORTS = {"TP": 24, "FN": 6, "FP": 6}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def compute(model, tensor):
    features = {}
    hooks = [model.get_submodule(layer).register_forward_hook(
        lambda _m, _i, output, key=key: features.update({key: output}))
        for key, layer in LAYERS.items()]
    try:
        with torch.enable_grad():
            logits = model(tensor.unsqueeze(0))
            a14, a28 = (features[key] for key in LAYERS)
            assert tuple(a14.shape[1:3]) == (14, 14) and tuple(a28.shape[1:3]) == (28, 28)
            g14, g28 = torch.autograd.grad(logits[0, 1], (a14, a28))
        gradcam = (g14.mean((1, 2), keepdim=True) * a14).sum(-1).relu()
        layercam = (g28.relu() * a28).sum(-1).relu()
        return logits.detach().softmax(-1)[0, 1].item(), {
            key: item.detach()[0].cpu().numpy() for key, item in zip(LAYERS, (gradcam, layercam), strict=True)}
    finally:
        for hook in hooks:
            hook.remove()


def paint(image, boxes, visible=None, peak=None):
    small = ImageOps.contain(image, (650, 360), Image.Resampling.LANCZOS)
    if visible is not None:
        values = np.asarray(Image.fromarray(visible).resize(small.size, Image.Resampling.BILINEAR))
        heat = cv2.cvtColor(cv2.applyColorMap(np.uint8(np.clip(values, 0, 1)*255), cv2.COLORMAP_JET),
                            cv2.COLOR_BGR2RGB)
        small = Image.fromarray(cv2.addWeighted(np.asarray(small), .5, heat, .5, 0))
    draw = ImageDraw.Draw(small)
    sx, sy = small.width / image.width, small.height / image.height
    for l, t, r, b in boxes:
        draw.rectangle((l*sx, t*sy, r*sx, b*sy), outline="#ffe55b", width=2)
    if peak is not None:
        x, y = peak[0]*sx, peak[1]*sy
        draw.ellipse((x-5,y-5,x+5,y+5), outline="#161616", width=4)
        draw.ellipse((x-5,y-5,x+5,y+5), outline="white", width=2)
    return small


def get_cases(run, previous_report=None):
    output_hashes = json.loads((run / "artifacts.json").read_bytes())
    for name in ("best_model_selection_predictions.csv", "model_selection_used.csv", "run_config.json"):
        assert sha(run / name) == output_hashes[name]
    predictions = read_csv(run / "best_model_selection_predictions.csv")
    used = {row["image_id"]: row for row in read_csv(run / "model_selection_used.csv")}
    assert len(predictions) == len(used) == 1033 and {r["image_id"] for r in predictions} == used.keys()
    source = Path(json.loads(Path("cowl_model/latest_inventory.json").read_bytes())["directory"])
    inventory = {row["image_id"]: row for row in read_csv(source / "image_label_inventory.csv")}
    prior_groups = set()
    prior_times = set()
    if previous_report:
        prior = json.loads(previous_report.read_bytes())
        assert prior["checkpointSHA256"] == EXPECTED and len(prior["results"]) == 36
        for row in prior["results"]:
            image_id = row["image_id"]
            assert row["image_sha256"] == used[image_id]["image_sha256"]
            prior_groups.add(used[image_id]["group_id"])
            if inventory[image_id]["captured_at"]:
                prior_times.add(inventory[image_id]["captured_at"])
    labels_archive, = {inventory[i]["label_archive"] for i in used}
    wanted = {inventory[i]["label_member"] for i in used}
    with tarfile.open(labels_archive) as archive:
        labels = {m.name: archive.extractfile(m).read() for m in archive if m.name in wanted}
    assert labels.keys() == wanted
    skip = Counter()
    cases = []
    for cohort, n in COHORTS.items():
        actual_pred = {"TP": ("1", "1"), "FN": ("1", "0"), "FP": ("0", "1")}[cohort]
        options = sorted((row for row in predictions if (row["actual"], row["predicted"]) == actual_pred),
                         key=lambda r: hashlib.sha256(("cowl-pin-cam-v1:"+r["image_id"]).encode()).digest())
        seen_groups = set()
        seen_times = set()
        for prediction in options:
            data = used[prediction["image_id"]]
            info = inventory[prediction["image_id"]]
            assert data["class_id"] == prediction["actual"] and data["label_sha256"] == info["label_sha256"]
            if data["group_id"] in seen_groups or data["group_id"] in prior_groups:
                continue
            if info["captured_at"] and (info["captured_at"] in seen_times or info["captured_at"] in prior_times):
                continue
            label = labels[info["label_member"]]
            if cohort == "FP":
                assert hashlib.sha256(label).hexdigest() == data["label_sha256"]
                anns = json.loads(label)["annotations"]
                assert any(a["category_id"] == 202 and a["attributes"]["quality"] == "양품" for a in anns)
                with Path(data["image_archive"]).open("rb") as archive:
                    archive.seek(int(data["offset"]))
                    raw = archive.read(int(data["size"]))
                assert hashlib.sha256(raw).hexdigest() == data["image_sha256"]
                with Image.open(io.BytesIO(raw)) as original:
                    image = ImageOps.exif_transpose(original).convert("RGB")
                ref = image, []
            else:
                result = read_case(dict(labelSHA256=data["label_sha256"], defectType="고정핀 불량",
                                        imageArchive=data["image_archive"], offset=int(data["offset"]),
                                        size=int(data["size"]), imageSHA256=data["image_sha256"]), label)
                if result is None:
                    skip[cohort] += 1
                    continue
                _, image, boxes = result
                ref = image, boxes
            seen_groups.add(data["group_id"])
            seen_times.add(info["captured_at"])
            cases.append((cohort, len(seen_groups), prediction, data, *ref))
            if len(seen_groups) == n:
                break
        assert len(seen_groups) == n, cohort
    return cases, skip


def summarize(results, method):
    generated = [row[method] for row in results if row[method]["status"] == "GENERATED"]
    measurable = [item["inside"] for item in generated if item["inside"] is not None]
    return dict(samples=len(results), generated=len(generated), peakInside=sum(measurable),
                peakComparable=len(measurable), statuses=Counter(row[method]["status"] for row in results))


def main(run, out, previous_report=None):
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    assert sha(run / "best.pt") == EXPECTED
    config = json.loads((run / "run_config.json").read_bytes())["config"]
    with torch.serialization.safe_globals([np._core.multiarray._reconstruct, np.ndarray, np.dtype, np.dtypes.UInt32DType]):
        checkpoint = torch.load(run / "best.pt", map_location="cpu", weights_only=True)
    assert checkpoint["epoch"] == 8 and config["image_size"] == 224
    model = timm.create_model(config["model_name"], pretrained=False, num_classes=2)
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()
    del checkpoint
    cases, skip = get_cases(run, previous_report)
    images = out / "images"
    images.mkdir()
    results, cards = [], []
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 20)
    page_head = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>카울커버 고정핀 CAM 비교</title><style>body{max-width:1360px;margin:24px auto;padding:0 16px;font:16px/1.5 system-ui;background:#eff4f8;color:#192f43}section{background:white;padding:12px 16px;margin:14px 0;border-radius:8px}.views{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}figure{margin:0}img{width:100%;height:235px;object-fit:contain;background:#171e26}small{color:#42576a}@media(max-width:650px){.views{grid-template-columns:1fr}}</style><h1>카울커버 고정핀 CAM 비교</h1><p>고정핀 8에폭 · 모델 선택 세트 · JET 50%. 노란 사각형은 AI-Hub 주석, 흰 원은 최대 반응점입니다. 사진을 누르면 해당 미리보기가 크게 열립니다.</p><p>TP는 불량을 맞힌 사진, FN은 놓친 사진, FP는 정상인데 불량으로 본 사진입니다. FN의 CAM은 진단용으로 강제 생성했으며 FP는 불량 위치 판정에서 제외했습니다.</p>"""
    if previous_report:
        page_head += "<p>재현 확인용 표본이며 첫 비교의 유사 그룹과 기록된 촬영 시각을 제외했습니다.</p>"
    for cohort, number, pred, data, image, boxes in cases:
        ident = f"{cohort}-{number:02d}"
        padded = ImageOps.pad(image, (224,224), Image.Resampling.BICUBIC, color=(124,116,104))
        tensor = TF.normalize(TF.to_tensor(padded), config["mean"], config["std"])
        score, raw_maps = compute(model, tensor)
        gpu_score = float(pred["raw_defect_score"])
        cutoff = config["prediction_cutoff"]
        row = dict(id=ident, cohort=cohort, image_id=pred["image_id"], boxes=boxes, image_sha256=data["image_sha256"],
                   box_area_fraction=sum((r-l)*(b-t) for l,t,r,b in boxes)/(image.width*image.height),
                   rawScoreCPU=score, frozenScoreGPU=gpu_score, predictionMatches=int(score >= cutoff)==int(pred["predicted"]))
        source = paint(image, boxes)
        source.save(images / f"{ident}-source.jpg", quality=92)
        sections = [(f"{ident}-source.jpg", "원본 · AI-Hub 주석")]
        for n, (method, raw) in enumerate(raw_maps.items(), 1):
            # Project the map back after removing the same letterbox padding as the FRAME check.
            info, visible = position(raw, image, boxes)
            if visible is None:
                status = "ZERO_MAP" if not np.any(raw) else "CONSTANT_MAP"
                info = dict(status=status, inside=None)
            elif not boxes:
                info["inside"] = None
            row[method] = info
            rendered = paint(image, boxes, visible, info.get("peakXY"))
            filename = f"{ident}-{n}.jpg"
            rendered.save(images / filename, quality=92)
            outcome = ("박스 안" if info["inside"] else "박스 밖") if info["inside"] is not None else (
                "위치 채점 제외" if visible is not None else info["status"])
            sections.append((filename, f"{method} · {outcome}"))
        results.append(row)
        figures = "".join(f'<figure><a href="images/{file}"><img loading="lazy" src="images/{file}" alt="{escape(text)}"></a><figcaption>{escape(text)}</figcaption></figure>'
                          for file, text in sections)
        cards.append(f'<section id="{ident}"><h2>{ident} · 불량 점수 {score:.2%}</h2><div class="views">{figures}</div></section>')
        if cohort == "TP" and number <= 6:
            sheet = Image.new("RGB",(1220,240),"#eff4f8")
            draw = ImageDraw.Draw(sheet)
            for j, (file, text) in enumerate(sections):
                draw.text((j*407+8, 5), f"{ident} · {text}", font=font, fill="#192f43")
                with Image.open(images / file) as photo:
                    photo.thumbnail((398, 202))
                    sheet.paste(photo, (j*407+(407-photo.width)//2, 30))
            sheet.save(out / f"{ident}.jpg",quality=93)
    groups = {cohort: [r for r in results if r["cohort"] == cohort] for cohort in COHORTS}
    report = dict(checkpointSHA256=EXPECTED, epoch=8, source="model_selection", device="cpu", layers=LAYERS,
                  selection=dict(COHORTS), skippedInvalidBoxOrOrientation=skip,
                  predictionMismatches=[row["id"] for row in results if not row["predictionMatches"]],
                  maxRawScoreDifference=max(abs(r["rawScoreCPU"]-r["frozenScoreGPU"]) for r in results),
                  byCohort={name: {method:summarize(rows, method) for method in LAYERS} for name,rows in groups.items()},
                  medianTPBoxAreaFraction=float(np.median([r["box_area_fraction"] for r in groups["TP"]])),
                  official_validation_used=False,
                  excludedPreviousCAMGroupAndCaptureTime=previous_report is not None,
                  priorReportSHA256=sha(previous_report) if previous_report else None, results=results)
    write_json(out / "report.json", report)
    summary = "<ul>"+"".join(f'<li>{escape(method)} · TP 24장 중 최대점 박스 안 {summary["peakInside"]}장, 유효한 맵 {summary["generated"]}장</li>'
                               for method, summary in report["byCohort"]["TP"].items())+"</ul>"
    (out / "review.html").write_text(page_head + summary + "".join(cards) + "</html>", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="results"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
