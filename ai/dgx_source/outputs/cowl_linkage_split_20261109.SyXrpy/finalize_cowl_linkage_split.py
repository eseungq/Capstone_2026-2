"""Freeze a linkage-only baseline while preserving fixed-pin group assignments."""

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys
import tarfile

from frame_model.check import read_image
from frame_model.train import manifests, subset


ROLES = {"train": 0.7, "model_selection": 0.1, "calibration_fit": 0.1, "policy_development": 0.1}
TARGET = "연계 불량"
SEED = "cowl-linkage-v1-20261109"


def read_json(path):
    return json.loads(path.read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_json(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def write_csv(path, rows):
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def latest(key):
    return Path(read_json(Path(f"cowl_model/latest_{key}.json"))["directory"])


def review_decisions(out, linkage, fingerprints, prior):
    selection_path = out / "review_selection.json"
    review_path = out / "user_review.json"
    selection = read_json(selection_path)
    review = read_json(review_path)
    observations = review["observations"]
    by_id = {r["id"]: r for r in observations}
    if (review["schema"] != "cowl-linkage-review-v1" or not review["reviewer"].strip()
            or review["selectionSha256"] != file_hash(selection_path)
            or len(selection) != 15 or len(observations) != 15
            or set(by_id) != {r["id"] for r in selection} or len(by_id) != 15
            or len({r["image_id"] for r in selection}) != 15):
        raise ValueError("Incomplete or mismatched linkage review")
    decisions = {
        r["image_id"]: {"visibility": r["visibility224"], "label": "동의",
                        "source": r["id"], "notes": r["notes"]}
        for r in prior if r["annotation_types"] == TARGET and r["labelAgreement"] == "원천 라벨에 동의"
    }
    applied = []
    for item in selection:
        image_id = item["image_id"]
        row = by_id[item["id"]]
        if (item["image_sha256"] != fingerprints[image_id]["source_sha256"]
                or item["label_sha256"] != linkage[image_id]["label_sha256"]
                or item["quality"] != linkage[image_id]["source_quality"]
                or row["visibility"] not in {"224에서도 판단 가능", "원본에서만 판단 가능", "둘 다 판단 어려움"}
                or row["label"] not in {"동의", "불일치 의심", "판단 보류"}
                or not isinstance(row["notes"], str)):
            raise ValueError(f"Invalid review: {item['id']}")
        decisions[image_id] = {**row, "source": item["id"]}
        applied.append({**item, **row})
    write_json(out / "review_applied.json", applied)
    return decisions, observations


def main(out, pin_split, pin_prep):
    inventory_path = latest("inventory") / "image_label_inventory.csv"
    full = latest("full_similarity")
    audit = read_json(full / "summary.json")
    if audit["inventory_sha256"] != file_hash(inventory_path) or audit["decode_errors"]:
        raise ValueError("Source audit does not match the inventory")
    inventory = read_csv(inventory_path)
    rows = {r["image_id"]: r for r in inventory}
    fingerprints = {r["image_id"]: r for r in read_jsonl(full / "fingerprints.jsonl")}
    if len(rows) != len(inventory) or rows.keys() != fingerprints.keys():
        raise ValueError("Inventory and fingerprints differ")
    linkage = {i: r for i, r in rows.items() if r["annotation_types"] == TARGET}
    if any(r["status"] != "ok" or r["source_quality"] != fingerprints[i]["quality"] for i, r in linkage.items()):
        raise ValueError("Unexpected source quality or image status")
    split_proof = read_json(pin_split / "summary.json")
    candidate_path = full / "candidates.jsonl"
    imported = latest("similarity_import")
    decisions, observations = review_decisions(
        out, linkage, fingerprints, read_csv(latest("scope_import") / "observations.csv"))

    parent = {i: i for i in rows}

    def group(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(a, b):
        a, b = sorted((group(a), group(b)))
        parent[b] = a

    hold = defaultdict(set)
    exact_groups = defaultdict(list)
    for image_id, item in fingerprints.items():
        exact_groups[item["display_sha256"]].append(image_id)
    for members in exact_groups.values():
        for other in members[1:]:
            join(members[0], other)
        linked = sorted(set(members) & linkage.keys())
        if len(linked) > 1:
            if len({linkage[i]["class_id"] for i in linked}) > 1:
                for i in linked:
                    hold[i].add("동일 표시 픽셀의 양품·불량 라벨 충돌")
            else:
                ranked = sorted(linked, key=lambda i: (not usable(decisions.get(i)), i))
                for i in ranked[1:]:
                    hold[i].add("동일 표시 픽셀 중복 사본")

    relations = read_jsonl(candidate_path)
    for edge in relations:
        a, b = edge["a"], edge["b"]
        join(a, b)
        if edge["cross_quality"] and a in linkage and b in linkage:
            for i in (a, b):
                hold[i].add("양품·불량이 다른 유사 후보")
    for edge in read_json(imported / "future_split_constraints.json")["links"]:
        join(edge["a"], edge["b"])
    for proposal in read_json(imported / "label_hold_proposals.json"):
        a, b = proposal["images"]
        if a in linkage and b in linkage:
            for i in (a, b):
                hold[i].add("이전 사람 검수의 라벨 충돌")
    for i, decision in decisions.items():
        if not usable(decision):
            hold[i].add("224 가시성 또는 원천 라벨 판단 보류")

    anchored = {}
    for role in ROLES:
        pin_csv = pin_split / f"{role}.csv"
        if file_hash(pin_csv) != split_proof["roles"][role]["manifest_sha256"]:
            raise ValueError(f"Fixed-pin split changed: {role}")
        for r in read_csv(pin_csv):
            root = group(r["image_id"])
            if anchored.setdefault(root, role) != role:
                raise ValueError("A connected component crosses fixed-pin roles")

    candidates = defaultdict(list)
    for image_id in sorted(linkage):
        if not hold[image_id]:
            candidates[group(image_id)].append(image_id)
    totals = Counter(linkage[i]["class_id"] for ids in candidates.values() for i in ids)
    distribution = {role: Counter() for role in ROLES}
    assignments = {root: anchored[root] for root in candidates if root in anchored}
    anchored_count = len(assignments)
    composition = {root: Counter(linkage[i]["class_id"] for i in ids) for root, ids in candidates.items()}
    for root, role in assignments.items():
        distribution[role].update(composition[root])
    free = sorted(candidates.keys() - assignments.keys(),
                  key=lambda root: (-len(candidates[root]), digest(f"{SEED}:{root}".encode())))
    for root in free:
        counts = composition[root]

        def penalty(role):
            score = 0
            for cls, count in counts.items():
                target = totals[cls] * ROLES[role]
                previous = distribution[role][cls] - target
                score += ((previous + count) ** 2 - previous ** 2) / target
            return score

        role = min(ROLES, key=penalty)
        assignments[root] = role
        distribution[role].update(counts)
    if any(len(distribution[role]) != 2 for role in ROLES):
        raise ValueError("Both classes are required in every role")
    if sum(map(len, candidates.values())) + sum(bool(reason) for reason in hold.values()) != len(linkage):
        raise ValueError("Linkage scope coverage changed")

    role_rows = defaultdict(list)
    for root, ids in candidates.items():
        for image_id in ids:
            row = linkage[image_id]
            role_rows[assignments[root]].append(dict(
                image_id=image_id, image_archive=row["image_archive"], offset=row["image_offset"],
                size=row["image_bytes"], image_sha256=fingerprints[image_id]["source_sha256"],
                group_id="cowl-" + digest(root.encode())[:20], defect_type=TARGET,
                class_id=row["class_id"], label_sha256=row["label_sha256"],
            ))
    written = {}
    for role in ROLES:
        path = out / f"{role}.csv"
        write_csv(path, sorted(role_rows[role], key=lambda row: row["image_id"]))
        written[role] = {"path": str(path), "sha256": file_hash(path)}
    holds = [dict(image_id=i, class_id=linkage[i]["class_id"], reasons=" | ".join(sorted(reason)))
             for i, reason in sorted(hold.items()) if reason]
    write_csv(out / "held_images.csv", holds)

    pin_config = read_json(pin_prep / "config.json")
    pin_preflight = read_json(pin_prep / "preflight.json")
    if pin_preflight["config_sha256"] != file_hash(pin_prep / "config.json"):
        raise ValueError("Fixed-pin training configuration changed")
    config_keys = ("model_name", "image_size", "epochs", "batch_size", "learning_rate", "weight_decay",
                   "mean", "std", "seed", "prediction_cutoff", "initialization", "trainer_sha256", "class_mapping")
    config = {key: pin_config[key] for key in config_keys}
    if file_hash(Path(config["initialization"]["path"])) != config["initialization"]["sha256"]:
        raise ValueError("Baseline initialization changed")
    for name, expected in config["trainer_sha256"].items():
        if file_hash(Path(name)) != expected:
            raise ValueError("Shared training code changed")
    archive_stats = {}
    for row in linkage.values():
        for archive in (row["image_archive"], row["label_archive"]):
            if archive not in archive_stats:
                stat = Path(archive).stat()
                archive_stats[archive] = dict(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)
    config.update(part_code="COWL_COVER", scope="Linkage only", inspection_types=[TARGET], archive_stats=archive_stats,
                  manifests=written, roles={r: len(role_rows[r]) for r in ROLES})
    write_json(out / "config.json", config)
    manifests(out)

    label_archive, = {r["label_archive"] for r in linkage.values()}
    verified_images = 0
    with tarfile.open(label_archive) as tar:
        for role in ROLES:
            for item in subset(role_rows[role], 2):
                row = linkage[item["image_id"]]
                source_label = tar.extractfile(row["label_member"]).read()
                anns = [a for a in json.loads(source_label)["annotations"] if a["category_id"] == 205]
                if (digest(source_label) != item["label_sha256"] or not anns
                        or {a["attributes"]["quality"] for a in anns} != {row["source_quality"]}
                        or read_image(item)[1].size != (224, 224)):
                    raise ValueError(f"Source check failed: {role}")
                verified_images += 1
    report = dict(
        status="linkage_baseline_manifests_verified", source="AI-Hub Training only",
        review=dict(total=len(observations), visibility=Counter(r["visibility"] for r in observations),
                    labels=Counter(r["label"] for r in observations), known_reviewed_images=len(decisions),
                    retained_by_review=sum(usable(r) for r in decisions.values())),
        original_classes=Counter(r["class_id"] for r in linkage.values()), held_count=len(holds),
        held_reasons=Counter(reason for reasons in hold.values() for reason in reasons),
        roles={role: dict(total=len(role_rows[role]), good=distribution[role]["0"],
                          defect=distribution[role]["1"], manifest_sha256=written[role]["sha256"]) for role in ROLES},
        anchored_linkage_groups=anchored_count, verified_sample_images=verified_images,
        cross_role_group_overlap=0, candidate_edges_sha256=file_hash(candidate_path),
        fixed_pin_summary_sha256=file_hash(pin_split / "summary.json"),
        config_sha256=file_hash(out / "config.json"), official_validation_used=False,
        training_started=False, model_forward_tested=False, calibration_ready=False, policy_ready=False,
        limits="Visible linkage labels at photo level. Similarity groups approximate physical identity.",
    )
    write_json(out / "summary.json", report)
    print(json.dumps(report, ensure_ascii=False))


def usable(decision):
    return bool(decision and decision["visibility"] == "224에서도 판단 가능" and decision["label"] == "동의")


if __name__ == "__main__":
    main(*(Path(arg).resolve(strict=True) for arg in sys.argv[1:]))
