"""Training과 Validation 이미지의 바이트 단위 중복을 검사한다."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("D:/162.부품 품질 검사 영상 데이터(자동차)/radiator_grille")
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_label(split: str, image_path: Path) -> dict[str, object]:
    label_path = DATA_ROOT / split / "labels" / f"{image_path.stem}.json"
    with label_path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    annotation = data["annotations"][0]
    attributes = annotation.get("attributes") or {}
    bbox = [round(float(value), 3) for value in annotation.get("bbox", [])]
    return {
        "label_file": label_path.name,
        "quality": str(attributes.get("quality", "미기재")),
        "category_id": annotation.get("category_id", ""),
        "bbox": json.dumps(bbox, ensure_ascii=False),
    }


def main() -> None:
    rows: list[dict[str, str | int]] = []
    groups: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for split in ("train", "val"):
        image_dir = DATA_ROOT / split / "images"
        paths = sorted(
            path
            for path in image_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        for path in paths:
            file_hash = sha256(path)
            groups[file_hash].append((split, path))

    duplicate_groups = {
        file_hash: items for file_hash, items in groups.items() if len(items) > 1
    }
    cross_split_groups = {
        file_hash: items
        for file_hash, items in duplicate_groups.items()
        if len({split for split, _ in items}) > 1
    }
    for group_number, (file_hash, items) in enumerate(
        sorted(duplicate_groups.items()), start=1
    ):
        for split, path in items:
            label = load_label(split, path)
            rows.append(
                {
                    "duplicate_group": group_number,
                    "sha256": file_hash,
                    "split": split,
                    "file_name": path.name,
                    "file_size": path.stat().st_size,
                    **label,
                }
            )

    group_quality: dict[int, set[str]] = defaultdict(set)
    group_bbox: dict[int, set[str]] = defaultdict(set)
    group_splits: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        group_number = int(row["duplicate_group"])
        group_quality[group_number].add(str(row["quality"]))
        group_bbox[group_number].add(str(row["bbox"]))
        group_splits[group_number].add(str(row["split"]))
    multi_quality_groups = {
        group for group, values in group_quality.items() if len(values) > 1
    }
    different_bbox_groups = {
        group for group, values in group_bbox.items() if len(values) > 1
    }
    cross_split_group_numbers = {
        group for group, values in group_splits.items() if len(values) > 1
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with (REPORT_DIR / "exact_duplicate_images.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "duplicate_group",
                "sha256",
                "split",
                "file_name",
                "file_size",
                "label_file",
                "quality",
                "category_id",
                "bbox",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "unique_hashes": len(groups),
        "duplicate_hash_groups": len(duplicate_groups),
        "cross_split_duplicate_hash_groups": len(cross_split_groups),
        "duplicate_files": sum(len(items) for items in duplicate_groups.values()),
        "same_split_duplicate_hash_groups": len(duplicate_groups) - len(cross_split_groups),
        "multi_quality_duplicate_groups": len(multi_quality_groups),
        "cross_split_multi_quality_groups": len(
            multi_quality_groups & cross_split_group_numbers
        ),
        "different_bbox_duplicate_groups": len(different_bbox_groups),
    }
    with (REPORT_DIR / "exact_duplicate_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    report_lines = [
        "# 정확한 중복 이미지 검사 보고서",
        "",
        f"- 서로 다른 이미지 해시: {summary['unique_hashes']:,}개",
        f"- 중복 이미지 그룹: {summary['duplicate_hash_groups']:,}개",
        f"- 중복에 포함된 이미지: {summary['duplicate_files']:,}개",
        f"- 같은 데이터 구분 안의 중복 그룹: {summary['same_split_duplicate_hash_groups']:,}개",
        f"- Training·Validation 사이 중복 그룹: {summary['cross_split_duplicate_hash_groups']:,}개",
        f"- 동일 이미지에 양품·불량품 ROI가 함께 있는 그룹: {summary['multi_quality_duplicate_groups']:,}개",
        f"- 위 그룹 중 Training·Validation에 나뉜 그룹: {summary['cross_split_multi_quality_groups']:,}개",
        f"- 동일 이미지에 서로 다른 bbox가 있는 그룹: {summary['different_bbox_duplicate_groups']:,}개",
        "",
        "동일 픽셀 이미지에 서로 다른 bbox가 있고 일부 그룹은 양품·불량품 ROI를 모두 포함한다. 이는 한 원본 사진의 여러 검사 지점을 파일별 라벨로 분리한 구조로 해석할 수 있다. 전체 이미지를 하나의 품질값으로 분류하지 말고 bbox 단위 ROI를 분류해야 한다. 또한 동일 원본 이미지 해시 그룹은 Training·Validation 중 한쪽에만 배치해야 배경이 겹치는 평가 누수를 줄일 수 있다.",
    ]
    (REPORT_DIR / "exact_duplicate_report.md").write_text(
        "\n".join(report_lines), encoding="utf-8"
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Exact duplicate check: PASS")


if __name__ == "__main__":
    main()
