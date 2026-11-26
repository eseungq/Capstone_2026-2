"""Compare FRAME attribution methods on the frozen 32 photos."""

from collections import Counter
import json
from pathlib import Path
import sys
import tarfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import torch

from frame_cam_localization_20261109 import read_case


METHODS = ("Grad-CAM 14", "HiResCAM 14", "LayerCAM 14", "LayerCAM 28")


def maps(engine, photo, late, early):
    captured = {}
    hooks = [engine.model.get_submodule(layer).register_forward_hook(
        lambda _module, _inputs, output, layer=layer: captured.update({layer: output})
    ) for layer in (late, early)]
    try:
        with torch.enable_grad():
            tensor = engine.tensor(photo).unsqueeze(0).cuda().requires_grad_(True)
            score = engine.model(tensor)[0, 1]
            a14, a28 = captured[late], captured[early]
            g14, g28 = torch.autograd.grad(score, (a14, a28))
        a14, g14, a28, g28 = [value.permute(0, 3, 1, 2) for value in (a14, g14, a28, g28)]
        if tuple(a14.shape[2:]) != (14, 14) or tuple(a28.shape[2:]) != (28, 28):
            raise ValueError("Unexpected Swin feature dimensions")
        values = [
            (g14.mean((2, 3), keepdim=True)*a14).sum(1),
            (g14*a14).sum(1),
            (g14.relu()*a14).sum(1),
            (g28.relu()*a28).sum(1),
        ]
        return [value.relu()[0].detach().cpu().numpy() for value in values]
    finally:
        for hook in hooks:
            hook.remove()


def position(raw, image, boxes):
    if not np.isfinite(raw).all():
        raise ValueError("Nonfinite attribution")
    lo, hi = float(raw.min()), float(raw.max())
    if hi-lo <= max(1e-12, abs(hi)*1e-6):
        return dict(status="NO_ACTIVATION"), None
    full = np.asarray(Image.fromarray(((raw-lo)/(hi-lo)).astype("float32")).resize((224, 224), Image.Resampling.BILINEAR))
    contained = ImageOps.contain(image, (224, 224), Image.Resampling.BICUBIC)
    x0, y0 = round((224-contained.width)/2), round((224-contained.height)/2)
    visible = full[y0:y0+contained.height, x0:x0+contained.width]
    y, x = np.unravel_index(np.argmax(visible), visible.shape)
    px, py = (x+.5)*image.width/visible.shape[1], (y+.5)*image.height/visible.shape[0]
    return dict(status="GENERATED", peakXY=[px, py],
                inside=any(a<=px<=c and b<=py<=d for a,b,c,d in boxes)), visible


def decorate(image, visible, peak):
    small = ImageOps.contain(image, (273, 150), Image.Resampling.LANCZOS)
    if visible is None:
        return small
    values = np.asarray(Image.fromarray(visible).resize(small.size, Image.Resampling.BILINEAR))
    heat = cv2.cvtColor(cv2.applyColorMap(np.uint8(np.clip(values,0,1)*255), cv2.COLORMAP_JET), cv2.COLOR_BGR2RGB)
    result = Image.fromarray(cv2.addWeighted(np.asarray(small), .5, heat, .5, 0))
    x, y = peak[0]*small.width/image.width, peak[1]*small.height/image.height
    draw = ImageDraw.Draw(result)
    draw.ellipse((x-5,y-5,x+5,y+5), outline="#161616", width=4)
    draw.ellipse((x-5,y-5,x+5,y+5), outline="white", width=2)
    return result


def main(project, source, output):
    torch.set_num_threads(2)
    sys.path.insert(0, str(project / "outputs/frame_test_api_jet_20261108.0mqEHz"))
    from frame_unified_test_api_20261107 import CAM_LAYER, FRAME_SHA256, MODEL_VERSION, create_engine
    engine = create_engine(project)
    baseline = json.loads((source / "report.json").read_text())
    selection = json.loads((source / "selection.json").read_text())
    assert len(selection) == 32 and baseline["checkpointSHA256"] == FRAME_SHA256 and baseline["camLayer"] == CAM_LAYER
    original = {row["imageSHA256"]: row for row in baseline["results"]}
    manifest_path = project / "outputs/frame_validation_review_closed_20261108.ROVWqL/evaluation_confirmed_duplicates_excluded.jsonl"
    manifest = {row["imageSHA256"]: row for row in map(json.loads, manifest_path.read_text().splitlines())}
    wanted = {manifest[row["imageSHA256"]]["labelMember"] for row in selection}
    label_path, = project.glob("downloads/aihub/*/01.*/2.Validation/*/VL_9.*.tar")
    with tarfile.open(label_path, "r:") as archive:
        labels = {member.name: archive.extractfile(member).read() for member in archive if member.name in wanted}
    output.mkdir()
    results, figures = [], {}
    input_path = output / "current_input.bin"
    for selected in selection:
        ident = selected["imageSHA256"]
        row = manifest[ident]
        case = read_case(row, labels[row["labelMember"]])
        if case is None:
            raise ValueError("Previously accepted CAM coordinates differ")
        raw, image, boxes = case
        input_path.write_bytes(raw)
        attribution = maps(engine, input_path, CAM_LAYER, "layers.1.blocks.1.norm1")
        evaluated = [position(raw_map, image, boxes) for raw_map in attribution]
        base = evaluated[0][0]
        ref = original[ident]
        if base["status"] != ref["status"] or base.get("inside") != ref.get("peakInsideBox"):
            raise RuntimeError(f'Previous baseline did not reproduce for {selected["number"]}')
        results.append(dict(**selected, methods={method: value[0] for method, value in zip(METHODS, evaluated)}))
        if not base.get("inside"):
            labeled = decorate(image, None, None)
            draw = ImageDraw.Draw(labeled)
            sx, sy = labeled.width/image.width, labeled.height/image.height
            for x0,y0,x1,y1 in boxes:
                draw.rectangle((x0*sx,y0*sy,x1*sx,y1*sy), outline="#ffcf42", width=2)
            figures.setdefault(selected["type"], []).append((selected["number"], labeled,
                [(value["inside"] if "inside" in value else None, decorate(image, visible, value.get("peakXY")))
                 for value, visible in evaluated]))
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    font = ImageFont.truetype(font_path, 17, index=1)
    title = ImageFont.truetype(font_path, 30, index=1)
    kinds = list(dict.fromkeys(row["type"] for row in selection))
    for index, kind in enumerate(kinds, 1):
        cases = figures[kind]
        sheet = Image.new("RGB", (1470, 105+185*len(cases)), "#eef3f8")
        draw = ImageDraw.Draw(sheet)
        draw.text((22, 12), f"프레임 Grad-CAM · 기존 반응점이 박스 밖인 {kind} 사례", font=title, fill="#15314d")
        for col, method in enumerate(("원본 라벨 박스", *METHODS)):
            draw.text((20+291*col, 67), method, font=font, fill="#15314d")
        for i, (number, left, variants) in enumerate(cases):
            y = 100+185*i
            for col, (flag, img) in enumerate([(None,left), *variants]):
                x = 20+291*col
                state = f"{number:02d}번" if col == 0 else "박스 안" if flag else "박스 밖" if flag is False else "반응 없음"
                draw.text((x,y), state, font=font, fill="#15314d")
                sheet.paste(img, (x+(273-img.width)//2, y+25))
        sheet.save(output / f"misses_{index}.jpg", quality=92, optimize=True)

    def counts(samples, method):
        states = Counter(row["methods"][method]["status"] for row in samples)
        inside = sum(row["methods"][method].get("inside", False) for row in samples)
        recovered = sum(not row["methods"][METHODS[0]].get("inside") and row["methods"][method].get("inside", False)
                        for row in samples)
        regressed = sum(row["methods"][METHODS[0]].get("inside", False) and not row["methods"][method].get("inside")
                        for row in samples)
        return dict(total=len(samples), inside=inside, recovered=recovered, regressed=regressed, statuses=dict(states))
    report = dict(modelVersion=MODEL_VERSION, checkpointSHA256=FRAME_SHA256, peakCheckReproduced=32,
                  overall={m:counts(results,m) for m in METHODS},
                  byType={kind:{m:counts([row for row in results if row["type"]==kind],m)
                                for m in METHODS} for kind in kinds}, photos=results)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(report["overall"]), flush=True)


if __name__ == "__main__":
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
