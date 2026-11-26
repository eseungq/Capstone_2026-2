"""Read-only AI-Hub FRAME Validation audit, without predictions or GPU use."""

import csv
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile

from PIL import Image, ImageOps
from ai_api.audit_data import difference_hash
from ai_api.audit_frame import label_info
from ai_api.rank_similarity import features, metrics
from frame_model.audit_similarity import HashIndex
from frame_model.cam_review import file_sha


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def label_index(archive_path):
    labels = defaultdict(list)
    errors = []
    with tarfile.open(archive_path, "r:") as archive:
        for member in archive:
            if not member.isfile() or not member.name.lower().endswith(".json"):
                continue
            try:
                raw = archive.extractfile(member).read()
                info = label_info(json.loads(raw.decode("utf-8-sig")), member.name)
                info["labelSHA256"] = hashlib.sha256(raw).hexdigest()
                labels[Path(member.name).stem].append(info)
            except Exception as error:
                errors.append(dict(member=member.name, error=repr(error)))
    return labels, errors


def inspect(fd, path, member, labels, thumb_dir, expected_types):
    stem = Path(member.name).stem
    info = labels.get(stem, [])
    row = dict(imageArchive=str(path), imageMember=member.name, offset=member.offset_data,
               size=member.size, stem=stem, issues=[])
    if len(info) != 1:
        row["issues"].append("missing_label" if not info else "ambiguous_label_stem")
    else:
        info = info[0]
        meta = info["metadata"]
        row.update(labelMember=info["labelMember"], labelSHA256=info["labelSHA256"],
                   quality=info["quality"], defectType=info["types"], capturedAt=meta.get("date_captured"))
        row["issues"].extend(info["issues"])
        if row["defectType"] not in expected_types:
            row["issues"].append("unknown_or_mixed_type")
        if meta.get("file_name") != Path(member.name).name:
            row["issues"].append("label_filename_mismatch")
    try:
        raw = os.pread(fd, member.size, member.offset_data)
        if len(raw) != member.size:
            raise OSError("Short read")
        row["imageSHA256"] = hashlib.sha256(raw).hexdigest()
        with Image.open(io.BytesIO(raw)) as image:
            raw_size = image.size
            display = ImageOps.exif_transpose(image).convert("RGB")
        row.update(width=display.width, height=display.height)
        if len(labels.get(stem, [])) == 1:
            declared = (meta.get("width"), meta.get("height"))
            if declared not in (raw_size, display.size):
                row["issues"].append("unexplained_label_dimensions")
        h = difference_hash(display)
        v = difference_hash(display.transpose(Image.Transpose.TRANSPOSE))
        row.update(dhash64=h, dual128=(h << 64) | v,
                   pixelSHA256=hashlib.sha256(str(display.size).encode() + display.tobytes()).hexdigest())
        display.resize((64, 64), Image.Resampling.LANCZOS).save(thumb_dir / f"{member.offset_data}.png")
    except Exception as error:
        row["issues"].append("image_read_or_decode_failure")
        row["error"] = repr(error)[:250]
    return row


def scan(images, labels, out, expected_types):
    thumbs = out / "thumbs"
    thumbs.mkdir()
    results = []
    with tarfile.open(images, "r:") as archive, ThreadPoolExecutor(max_workers=5) as workers:
        fd = archive.fileobj.fileno()
        pending = []
        for member in archive:
            if member.isfile() and member.name.lower().endswith((".jpg", ".jpeg", ".png")):
                pending.append(workers.submit(inspect, fd, images, member, labels, thumbs, expected_types))
            if len(pending) == 20:
                results.extend(future.result() for future in pending)
                pending.clear()
                if len(results) % 200 == 0:
                    print("Validation photos fingerprinted:", len(results), flush=True)
        results.extend(future.result() for future in pending)
    with (out / "validation_fingerprints.jsonl").open("w", encoding="utf-8") as stream:
        for row in results:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return results


def visual_matches(validation, existing, old_thumbs, out):
    horizontal = [int(row["dhash64"]) for row in existing]
    dual = [int(row["dual_hash128"]) for row in existing]
    hi, di = HashIndex(horizontal, 64, 8), HashIndex(dual, 128, 12)
    pixels = defaultdict(list)
    for row in existing:
        pixels[row["display_pixel_sha256"]].append(row)

    @lru_cache(maxsize=4096)
    def old_features(ident):
        with Image.open(old_thumbs / f"{ident}.png") as image:
            return features(image)

    for index, row in enumerate(validation, 1):
        if "dhash64" not in row:
            continue
        row["crossPixelMatches"] = [old["image_id"] for old in pixels.get(row["pixelSHA256"], ())]
        a, b = row["dhash64"], row["dual128"]
        candidates = hi.query(a) | di.query(b)
        close = []
        row["crossHashCandidateCount"] = 0
        for candidate in candidates:
            hd, dd = (a ^ horizontal[candidate]).bit_count(), (b ^ dual[candidate]).bit_count()
            if hd <= 8 or dd <= 12:
                row["crossHashCandidateCount"] += 1
            if hd <= 4 and dd <= 8:
                close.append((candidate, hd, dd))
        strong = []
        if close:
            with Image.open(out / "thumbs" / f'{row["offset"]}.png') as image:
                va, ve, _ = features(image)
            for candidate, hd, dd in close:
                old = existing[candidate]
                oa, oe, _ = old_features(old["image_id"])
                measures = metrics((va, ve, row["width"] / row["height"]),
                                   (oa, oe, old["width"] / old["height"]))
                if (measures["rgbMAE64"] <= 12 and measures["relativeEdgeDifference"] <= 0.35
                        and measures["aspectDifference"] <= 0.015):
                    strong.append(dict(imageId=old["image_id"], role=old["role"],
                                       dHashDistance=hd, dualHashDistance=dd, **measures))
        row["strongVisualCandidates"] = sorted(strong, key=lambda item: item["rankScore"])
        if index % 500 == 0:
            print("Cross-split comparison:", index, "/", len(validation), flush=True)


def counts(rows):
    values = Counter((row.get("defectType", "unknown"), row.get("quality", "unknown")) for row in rows)
    return [dict(type=kind, quality=quality, count=count) for (kind, quality), count in sorted(values.items())]


def main(project, output):
    Image.MAX_IMAGE_PIXELS = 120_000_000
    source = next(project.glob("downloads/aihub/*/01.*/2.Validation"))
    images, labels_path = next(source.glob("*/VS_9.*.tar")), next(source.glob("*/VL_9.*.tar"))
    run = project / "outputs/frame_training/comparison_train_20261022T160533_169658Z/unified"
    run_config = json.loads((run / "run_config.json").read_text())
    artifacts = json.loads((run / "artifacts.json").read_text())
    inventory_path = project / "ai_api/verification/frame_audit_20261020T171709_051078Z/image_inventory.csv"
    prior = project / "outputs/frame_similarity/20261027T082755_762226Z"
    prior_fp = prior / "fingerprints.jsonl"
    prior_summary = json.loads((prior / "verified_summary.json").read_text())
    if file_sha(prior_fp) != prior_summary["file_sha256"][prior_fp.name]:
        raise ValueError("Existing comparison fingerprints changed")
    original_stats = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in (images, labels_path)}
    roles = {}
    exact_names = defaultdict(set)
    exact_times = defaultdict(set)
    for role in ("train", "model_selection", "calibration_fit", "policy_development"):
        if role in ("train", "model_selection"):
            path = run / f"{role}_used.csv"
            expected = artifacts[path.name]
        else:
            item = run_config["config"]["manifests"][role]
            path, expected = Path(item["path"]), item["sha256"]
        if file_sha(path) != expected:
            raise ValueError(f"{role} manifest differs")
        roles[role] = {}
        for row in read_csv(path):
            roles[role][row["image_sha256"]] = row
            exact_names[Path(row["image_member"]).stem].add(role)
            if row["captured_at"]:
                exact_times[(row["defect_type"], row["captured_at"])].add(role)
    train_inventory = read_csv(inventory_path)
    train_digests = {row["imageSHA256"] for row in train_inventory if row["imageSHA256"]}
    all_training_names = {Path(row["imageMember"]).stem for row in train_inventory}
    with prior_fp.open(encoding="utf-8") as stream:
        reference = [json.loads(line) for line in stream]
    if ({row["image_id"] for row in reference} != (set(roles["train"]) | set(roles["model_selection"]))
            or len(reference) != len(roles["train"]) + len(roles["model_selection"])):
        raise ValueError("Prior fingerprints do not match the used splits")
    labels, label_errors = label_index(labels_path)
    print("Validation label stems:", len(labels), "label parsing errors:", len(label_errors), flush=True)
    rows = scan(images, labels, output, set(run_config["config"]["inspection_types"]))
    visual_matches(rows, reference, prior / "thumbs", output)

    internal = defaultdict(list)
    for row in rows:
        if row.get("pixelSHA256"):
            internal[row["pixelSHA256"]].append(row)
    for group in internal.values():
        if len(group) < 2:
            continue
        label_set = {(row.get("quality"), row.get("defectType")) for row in group}
        keep = min(group, key=lambda row: (bool(row["issues"]), row["imageMember"], row["offset"]))
        for row in group:
            if len(label_set) != 1:
                row["issues"].append("internal_exact_pixel_label_conflict")
            elif row is not keep:
                row["issues"].append("internal_exact_pixel_repeated_copy")

    missing_labels = sorted(set(labels) - {row["stem"] for row in rows})
    for row in rows:
        digest = row.get("imageSHA256")
        row["crossExactByteRoles"] = sorted(role for role in roles if digest in roles[role])
        row["crossExactByteTrainingArchive"] = digest in train_digests
        row["crossSameNameRoles"] = sorted(exact_names[row["stem"]])
        row["crossSameNameTrainingArchive"] = row["stem"] in all_training_names
        row["sameTypeAndTimestampRoles"] = sorted(exact_times[(row.get("defectType"), row.get("capturedAt"))])
        row["eligibleAfterExactChecks"] = not (row["issues"] or row["crossExactByteTrainingArchive"]
                                                or row["crossSameNameTrainingArchive"]
                                                or row.get("crossPixelMatches"))
        row["eligibleConservative"] = (row["eligibleAfterExactChecks"]
                                       and not row.get("crossHashCandidateCount")
                                       and not row["sameTypeAndTimestampRoles"])
    exact = [row for row in rows if row["eligibleAfterExactChecks"]]
    conservative = [row for row in rows if row["eligibleConservative"]]
    if any(original_stats[path.name] != (path.stat().st_size, path.stat().st_mtime_ns) for path in (images, labels_path)):
        raise ValueError("A Validation archive changed during the audit")
    for name, subset in (("all_records", rows), ("eligible_exact", exact), ("eligible_conservative", conservative)):
        with (output / f"{name}.jsonl").open("w", encoding="utf-8") as stream:
            for row in subset:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = dict(
        status="complete", validationImages=len(rows), labelStems=len(labels),
        labelParseErrors=label_errors, orphanLabelStems=missing_labels,
        trainingArchiveInventoryRows=len(train_inventory),
        comparedRoleCounts={role: len(records) for role, records in roles.items()},
        priorVisualFingerprints=len(reference), modelInference=False,
        crossExactByte=sum(row["crossExactByteTrainingArchive"] for row in rows),
        crossExactByteByRole=dict(Counter(role for row in rows for role in row["crossExactByteRoles"])),
        crossSameName=sum(row["crossSameNameTrainingArchive"] for row in rows),
        crossExactDecodedPixel=sum(bool(row.get("crossPixelMatches")) for row in rows),
        visualCandidates=sum(bool(row.get("crossHashCandidateCount")) for row in rows),
        visualCandidatePairs=sum(row.get("crossHashCandidateCount", 0) for row in rows),
        strongVisualCandidates=sum(bool(row.get("strongVisualCandidates")) for row in rows),
        sameTypeAndTimestamp=sum(bool(row["sameTypeAndTimestampRoles"]) for row in rows),
        issueCounts=dict(Counter(issue for row in rows for issue in row["issues"])),
        originalClassCounts=counts(rows), eligibleAfterExactChecks=len(exact), exactClassCounts=counts(exact),
        eligibleConservative=len(conservative), conservativeClassCounts=counts(conservative),
        visualScreen="dHash64 <= 8 or dual128 <= 12 against train and model selection only",
        strongVisualScreen="dHash64 <= 4 and dual128 <= 8; RGB MAE <= 12, relative edge <= 0.35, aspect <= 0.015",
        conservativeRule="Exclude all cross hash candidates and same-type identical capture timestamp, in addition to exact/label issues.",
        limits=["Similarity flags are screening candidates; not confirmed duplicates.",
                "No physical part identifiers; crop, angle, illumination and rephotographed part overlap can be missed.",
                "Visual screening does not cover reserved calibration or policy-development images.",
                "Conservative subset can change sample mix and favor visually distinctive cases."],
    )
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    (output / "summary.json").write_text(rendered + "\n", encoding="utf-8")
    print(rendered, flush=True)


if __name__ == "__main__":
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
