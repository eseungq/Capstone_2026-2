"""Evaluate the frozen fixed-pin policy on AI-Hub Validation after overlap checks."""

from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

import numpy as np
from PIL import Image, ImageOps
from scipy.special import expit
import torch

from cowl_model.audit_similarity import dhash
from cowl_pin_trial_api import EXPECTED, ROOT, VERSION, PinEngine, sha, write_json
from evaluate_cowl_pin_policy import bounds, extract, metrics


DEV = ROOT / "outputs/cowl_pin_policy_development_20261109.xFQpFZ/policy_report.json"
DEV_SHA = "31ea0aee83002107b25aca650f9e189793308a6421fb4799617036ddf1f3d6b0"


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def source_stat(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns]


def inventory(image_path, label_path):
    images = {}
    with tarfile.open(image_path, "r:") as archive:
        for m in archive:
            if not m.isfile() or Path(m.name).suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            ident = Path(m.name).stem
            assert ident not in images
            images[ident] = (m.offset_data, m.size)
    rows = {}
    with tarfile.open(label_path, "r:") as archive:
        for m in archive:
            if not m.isfile() or Path(m.name).suffix != ".json":
                continue
            label = archive.extractfile(m).read()
            data = json.loads(label)
            annotations = data["annotations"]
            if 202 not in {a["category_id"] for a in annotations}:
                continue
            image, = data["images"]
            ident = Path(m.name).stem
            assert ident not in rows and ident == Path(image["file_name"]).stem
            assert {a["category_id"] for a in annotations} == {202}
            assert {a["attributes"]["part"] for a in annotations} == {"카울커버"}
            quality, = {a["attributes"]["quality"] for a in annotations}
            offset, size = images[ident]
            rows[ident] = dict(image_id=ident,image_archive=str(image_path),offset=offset,size=size,
                               class_id={"양품":"0","불량품":"1"}[quality],label_sha256=digest(label),
                               captured_at=image.get("date_captured"))
    assert len(rows) == 1295, len(rows)
    return rows


def audit(rows, train_fingerprints, out):
    train = list(map(json.loads, train_fingerprints.read_bytes().splitlines()))
    assert len(train) == 20386 and len({r["image_id"] for r in train}) == len(train)
    exact_source, exact_pixels = defaultdict(list), defaultdict(list)
    train_near = []
    for r in train:
        exact_source[r["source_sha256"]].append(r["image_id"])
        exact_pixels[r["display_sha256"]].append(r["image_id"])
        train_near.append((int(r["dhash64"]),r["image_id"]))
    cross = {}
    parent = {i:i for i in rows}
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def join(a,b):
        a,b = sorted((root(a),root(b)))
        parent[b] = a
    prior = []
    exact_groups = defaultdict(list)
    archive_path, = {r["image_archive"] for r in rows.values()}
    with Path(archive_path).open("rb") as archive:
        for n,row in enumerate(sorted(rows.values(),key=lambda r:r["offset"]),1):
            ident = row["image_id"]
            archive.seek(row["offset"])
            blob = archive.read(row["size"])
            assert len(blob) == row["size"]
            with Image.open(io.BytesIO(blob)) as raw:
                display = ImageOps.exif_transpose(raw).convert("RGB")
            s = digest(blob)
            d = digest(str(display.size).encode()+display.tobytes())
            h = dhash(display)
            same = set(exact_source[s]) | set(exact_pixels[d])
            near = [i for f,i in train_near if (h^f).bit_count() <= 8 and i not in same]
            cross[ident] = dict(exact=sorted(same),near=sorted(near))
            exact_groups[d].append(ident)
            row.update(image_sha256=s, display_sha256=d)
            for f,i in prior:
                if (h^f).bit_count() <= 8:
                    join(ident,i)
            prior.append((h,ident))
            if n % 250 == 0:
                print("OVERLAP", n, "/", len(rows), flush=True)
    held = {}
    for members in exact_groups.values():
        if len(members) > 1:
            for i in members[1:]:
                join(members[0],i)
            if len({rows[i]["class_id"] for i in members}) > 1:
                held.update({i:"validation_exact_label_conflict" for i in members})
            else:
                held.update({i:"validation_exact_duplicate_copy" for i in sorted(members)[1:]})
    for ident, row in rows.items():
        row["group_id"] = root(ident)
        if cross[ident]["exact"]:
            held[ident] = "exact_overlap_with_training_pool"
    manifest = [dict(**r, excluded=held.get(i), cross_near=bool(cross[i]["near"]))
                for i,r in sorted(rows.items())]
    write_json(out/"overlap_matches.json", cross)
    write_json(out/"frozen_evaluation_manifest.json",manifest)
    return manifest, Counter(held.values())


def summarize(rows, frozen):
    temperature = frozen["temperature"]
    p = expit(np.array([r["margin"] for r in rows])/temperature)
    y = np.array([r["label"] for r in rows])
    passed = np.array([r["prediction"] == 0 for r in rows]) & (p <= frozen["pass_threshold"])
    good, bad = y==0, y==1
    ng, nb = int(good.sum()), int(bad.sum())
    dg = {r["group_id"] for r in rows if r["label"]==1}
    missed = [{**r, "calibrated_defect_probability":float(p[i])}
              for i,r in enumerate(rows) if passed[i] and bad[i]]
    mg = len({r["group_id"] for r in missed})
    gp = int((passed & good).sum())
    return dict(total=len(rows),normal=ng,defect=nb,defect_similarity_groups=len(dg),
                normal_autopass=gp,normal_autopass_rate=gp/ng,defect_autopass=len(missed),
                defect_autopass_rate=len(missed)/nb,defect_groups_autopass=mg,
                total_autopass=int(passed.sum()),review=int((~passed).sum()),
                photo_upper95_descriptive=bounds(len(missed),nb),
                group_upper95_descriptive=bounds(mg,len(dg)),
                reference_zero_and_upper_1_percent_met_on_similarity_groups=(len(dg)>=300 and mg==0 and bounds(mg,len(dg))<=.01),
                metrics_before=metrics(np.array([r["margin"] for r in rows]),y,1.0),
                metrics_after=metrics(np.array([r["margin"] for r in rows]),y,temperature),
                missed=missed)


def main(out):
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    assert sha(DEV) == DEV_SHA
    dev = json.loads(DEV.read_bytes())
    assert dev["checkpoint_sha256"] == EXPECTED and dev["policies"]["temperature"]["illustrative_grid_candidate"]["threshold"]==.02
    frozen = dict(model_version=VERSION,checkpoint_sha256=EXPECTED,temperature=dev["temperature"],pass_threshold=.02,
                  rule="raw_prediction_GOOD and calibrated_defect_probability <= 0.02",
                  policy_development_report_sha256=DEV_SHA,
                  primary="AI-Hub Validation category 202, exact cross-split excluded, exact internal copies collapsed",
                  sensitivity="primary excluding all cross-Training dHash64 distance <= 8 candidates",
                  grouping="dHash64 distance <= 8 transitive groups within Validation; physical identities unavailable",
                  scoring="DGX CPU FP32 batch 8, same model/preprocessing/runtime as policy development")
    write_json(out/"frozen_policy.json",frozen)
    print("FROZEN", sha(out/"frozen_policy.json"), flush=True)
    engine = PinEngine()
    image_path, = ROOT.glob("downloads/aihub/*/01.*/2.Validation/*/VS_6.*.tar")
    label_path, = ROOT.glob("downloads/aihub/*/01.*/2.Validation/*/VL_6.*.tar")
    source_before = {str(p):source_stat(p) for p in (image_path,label_path)}
    training = Path(json.loads((ROOT/"cowl_model/latest_full_similarity.json").read_bytes())["directory"])
    train_fingerprints = training/"fingerprints.jsonl"
    assert json.loads((training/"summary.json").read_bytes())["decode_errors"]==0
    rows = inventory(image_path,label_path)
    manifest, holds = audit(rows,train_fingerprints,out)
    manifest_hash = sha(out/"frozen_evaluation_manifest.json")
    primary = [r for r in manifest if r["excluded"] is None]
    strict = {r["image_id"] for r in primary if not r["cross_near"]}
    print("AUDIT_COMPLETE",len(manifest),len(primary),len(strict),dict(holds),flush=True)
    scores = extract(engine,sorted(primary,key=lambda r:r["offset"]),out/"official_scores.csv")
    assert manifest_hash == sha(out/"frozen_evaluation_manifest.json")
    assert source_before == {str(p):source_stat(p) for p in (image_path,label_path)}
    report = dict(frozen_policy=frozen,frozen_policy_sha256=sha(out/"frozen_policy.json"),
                  raw_counts=dict(Counter(r["class_id"] for r in manifest)),
                  exclusions=holds,primary_cross_near_candidates=len(primary)-len(strict),
                  primary=summarize(scores,frozen),
                  sensitivity=summarize([r for r in scores if r["image_id"] in strict],frozen),
                  official_manifest_sha256=manifest_hash,score_sha256=sha(out/"official_scores.csv"),
                  training_fingerprints_sha256=sha(train_fingerprints),source_archive_stat=source_before,
                  policy_activated=False,
                  limit="Photo and similarity-group evaluation only; unverified physical identities and line conditions.")
    write_json(out/"official_policy_report.json",report)
    print("OFFICIAL_VALIDATION_COMPLETE",out/"official_policy_report.json",flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(strict=True))
