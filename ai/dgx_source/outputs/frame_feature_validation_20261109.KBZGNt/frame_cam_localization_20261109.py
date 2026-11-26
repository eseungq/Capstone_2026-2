"""Check the current FRAME Grad-CAM peak against source boxes on frozen TP fixtures."""

from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import torch


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_case(row, raw_label):
    if sha(raw_label) != row["labelSHA256"]:
        raise ValueError("Label hash differs from frozen evaluation")
    label = json.loads(raw_label.decode("utf-8-sig"))
    info = label["images"][0]
    categories = {item["id"]: item["name"] for item in label["categories"]}
    boxes = [mark["bbox"] for mark in label["annotations"] if len(mark.get("bbox", [])) == 4
             and categories[mark["category_id"]] == row["defectType"]
             and mark["attributes"]["quality"] == "불량품"]
    if not boxes:
        return None
    with Path(row["imageArchive"]).open("rb") as archive:
        raw = os.pread(archive.fileno(), row["size"], row["offset"])
    if sha(raw) != row["imageSHA256"]:
        raise ValueError("Image hash differs from frozen evaluation")
    with Image.open(io.BytesIO(raw)) as source:
        if source.getexif().get(274, 1) != 1 or source.size != (info["width"], info["height"]):
            return None
        image = ImageOps.exif_transpose(source).convert("RGB")
    rects = [(x, y, x+w, y+h) for x, y, w, h in boxes]
    if any(not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height)
           for x0, y0, x1, y1 in rects):
        return None
    return raw, image, rects


def main(root, out):
    Image.MAX_IMAGE_PIXELS = 120_000_000
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    sys.path.insert(0, str(root / "outputs/frame_test_api_jet_20261108.0mqEHz"))
    from frame_unified_test_api_20261107 import CAM_LAYER, MODEL_VERSION, FRAME_SHA256, load_shared_api, create_engine
    load_shared_api(root, out)
    from ai_api.diagnostics import cam
    engine = create_engine(root)
    run = root / "outputs/frame_e08_final_20261108.b9jWcj"
    prediction_raw = (run / "predictions.jsonl").read_bytes()
    validation = root / "outputs/frame_validation_review_closed_20261108.ROVWqL/evaluation_confirmed_duplicates_excluded.jsonl"
    validation_raw = validation.read_bytes()
    baseline = json.loads((run / "report.json").read_text())
    if (sha(prediction_raw), sha(validation_raw), MODEL_VERSION) != (
        baseline["predictionsSHA256"], baseline["mainManifestSHA256"], baseline["modelVersion"]
    ):
        raise ValueError("Frozen classification evidence changed")
    predictions = [json.loads(line) for line in prediction_raw.splitlines()]
    eligible = {row["id"] for row in predictions if row["conservative"] and row["actual"] == row["prediction"] == 1}
    manifest = [json.loads(line) for line in validation_raw.splitlines()]
    wanted = {row["labelMember"] for row in manifest if row["imageSHA256"] in eligible}
    label_path, = root.glob("downloads/aihub/*/01.*/2.Validation/*/VL_9.*.tar")
    with tarfile.open(label_path, "r:") as archive:
        labels = {member.name: archive.extractfile(member).read() for member in archive if member.name in wanted}
    assert set(labels) == wanted
    kinds = ("실링 불량", "외관 손상", "헤밍 불량", "홀 변형")
    cases = []
    skipped = Counter()
    for kind in kinds:
        candidates = sorted((row for row in manifest if row["defectType"] == kind and row["imageSHA256"] in eligible),
                            key=lambda row: sha(("frame-cam-20261109:" + row["imageSHA256"]).encode()))
        chosen = 0
        used_times = set()
        for row in candidates:
            if row["capturedAt"] in used_times:
                continue
            info = read_case(row, labels[row["labelMember"]])
            if info is None:
                skipped[kind] += 1
                continue
            cases.append((kind, row, info))
            used_times.add(row["capturedAt"])
            chosen += 1
            if chosen == 8:
                break
        if chosen != 8:
            raise ValueError(f"Too few usable boxes for {kind}")
    selection = [dict(number=i, type=kind, imageSHA256=row["imageSHA256"], sourceMember=row["imageMember"],
                      labelSHA256=row["labelSHA256"], boxes=info[2])
                 for i, (kind, row, info) in enumerate(cases, 1)]
    (out / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n")
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 19, index=1)
    large = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 32, index=1)
    results = []
    for kind_index, kind in enumerate(kinds, 1):
        sheet = Image.new("RGB", (1400, 120 + 220 * 4), "#eef3f8")
        draw = ImageDraw.Draw(sheet)
        draw.text((20, 12), f"프레임 JET Grad-CAM 위치 점검 · {kind}", font=large, fill="#193452")
        draw.text((23, 64), "각 쌍의 왼쪽은 AI-Hub 라벨 박스. 오른쪽은 JET 50%와 최대 반응점(흰색).",
                  font=font, fill="#435b73")
        for i in range(8):
            number = (kind_index - 1) * 8 + i + 1
            _, row, (raw, image, rects) = cases[number-1]
            output = dict(**selection[number-1])
            small = ImageOps.contain(image, (327, 164), Image.Resampling.LANCZOS)
            marked = small.copy()
            marked_draw = ImageDraw.Draw(marked)
            for x0, y0, x1, y1 in rects:
                sx, sy = small.width/image.width, small.height/image.height
                marked_draw.rectangle((x0*sx, y0*sy, x1*sx, y1*sy), outline="#ffcf42", width=2)
            overlay = small.copy()
            with tempfile.TemporaryDirectory(dir=out) as workspace:
                folder = Path(workspace)
                photo = folder / "original.bin"
                photo.write_bytes(raw)
                prediction = engine.predict(photo)
                output["score"] = prediction["raw_defect_score"]
                if prediction["predicted_class"] == 1:
                    info, full, _ = cam(engine, photo, CAM_LAYER, folder, render_overlay=False)
                    output["status"] = info["status"]
                    if full is not None:
                        x0, y0, x1, y1 = info["paddingCrop"]
                        visible = full[y0:y1, x0:x1]
                        y, x = np.unravel_index(np.argmax(visible), visible.shape)
                        px, py = (x+.5)*image.width/visible.shape[1], (y+.5)*image.height/visible.shape[0]
                        output["peakXY"] = [px, py]
                        output["peakInsideBox"] = bool(any(l <= px <= r and t <= py <= b for l,t,r,b in rects))
                        scaled = Image.fromarray(visible).resize(small.size, Image.Resampling.BILINEAR)
                        heat = cv2.applyColorMap(np.uint8(np.clip(np.asarray(scaled), 0, 1)*255), cv2.COLORMAP_JET)
                        overlay = Image.fromarray(cv2.addWeighted(
                            np.asarray(small), .5, cv2.cvtColor(heat, cv2.COLOR_BGR2RGB), .5, 0))
                        x, y = px*small.width/image.width, py*small.height/image.height
                        peak_draw = ImageDraw.Draw(overlay)
                        peak_draw.ellipse((x-5, y-5, x+5, y+5), outline="#141414", width=4)
                        peak_draw.ellipse((x-5, y-5, x+5, y+5), outline="white", width=2)
                else:
                    output["status"] = "NOT_REQUIRED_SINGLE_PREDICTION_GOOD"
            results.append(output)
            label = ("박스 안" if output.get("peakInsideBox") else "박스 밖"
                     if "peakInsideBox" in output else output["status"])
            ox, oy = (i % 2)*700, 110+(i//2)*220
            draw.text((ox+20, oy), f'{number:02d} · 최대 반응점 {label}', font=font, fill="#193452")
            sheet.paste(marked, (ox+18+(327-marked.width)//2, oy+34))
            sheet.paste(overlay, (ox+350+(327-overlay.width)//2, oy+34))
        sheet.save(out / f"cam_{kind_index}.jpg", quality=92, optimize=True)
        print(kind, "CAM checks complete", flush=True)
    def counts(rows):
        return dict(samples=len(rows), generated=sum(row["status"] == "GENERATED" for row in rows),
                    peakInside=sum(row.get("peakInsideBox", False) for row in rows),
                    statusCounts=dict(Counter(row["status"] for row in rows)))
    report = dict(modelVersion=MODEL_VERSION, checkpointSHA256=FRAME_SHA256, camLayer=CAM_LAYER,
                  selection="8 seeded, conservative-set true-positive photos per type, with supported source boxes.",
                  scope="Bounding-box peak check, not pixel-level accuracy or location for missed defects.",
                  skippedInvalidBoxOrOrientation=dict(skipped), overall=counts(results),
                  byType={kind: counts([row for row in results if row["type"] == kind]) for kind in kinds}, results=results)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["overall"]), flush=True)


if __name__ == "__main__":
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
