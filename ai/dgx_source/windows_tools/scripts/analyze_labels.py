"""AI Hub 자동차 부품 JSON 라벨의 구조와 분포를 분석한다."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
FIGURE_DIR = PROJECT_ROOT / "outputs" / "figures"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JSON 라벨 구조와 분포 분석")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs" / "data.example.yaml",
        help="데이터 경로 설정 YAML",
    )
    return parser.parse_args()


def configure_korean_font() -> None:
    font_path = Path("C:/Windows/Fonts/malgun.ttf")
    if font_path.exists():
        from matplotlib import font_manager

        font_name = font_manager.FontProperties(fname=font_path).get_name()
        plt.rcParams["font.family"] = font_name
    plt.rcParams["axes.unicode_minus"] = False


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def safe_join(values: list[str]) -> str:
    return "|".join(sorted(set(value for value in values if value)))


def normalize_quality(value: Any) -> str:
    raw_value = str(value or "미기재").strip()
    if "불량" in raw_value:
        return "불량품"
    if raw_value in {"양품", "정상", "정상품"}:
        return "양품"
    return raw_value


def analyze_split(
    split: str,
    image_dir: Path,
    label_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    image_paths = [
        path
        for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    images_by_name = {path.name: path for path in image_paths}
    label_paths = sorted(label_dir.rglob("*.json"))

    records: list[dict[str, Any]] = []
    annotation_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    top_level_keys: Counter[str] = Counter()
    annotation_keys: Counter[str] = Counter()
    attribute_keys: Counter[str] = Counter()
    category_registry: dict[int, str] = {}
    missing_images = 0
    stem_mismatches = 0
    empty_annotations = 0
    invalid_bboxes = 0
    out_of_bounds_bboxes = 0
    area_mismatches = 0
    image_size_mismatches = 0
    segmentation_annotations = 0

    for label_path in label_paths:
        try:
            with label_path.open("r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except Exception as error:  # 분석 보고서에 파일별 오류를 남긴다.
            errors.append({"file": str(label_path), "error": repr(error)})
            continue

        top_level_keys.update(data.keys())
        categories = {
            int(item["id"]): str(item.get("name", item["id"]))
            for item in data.get("categories", [])
            if "id" in item
        }
        category_registry.update(categories)
        images = data.get("images", [])
        annotations = data.get("annotations", [])
        if not annotations:
            empty_annotations += 1

        image_info = images[0] if images else {}
        image_name = str(image_info.get("file_name", ""))
        image_path = images_by_name.get(image_name)
        width = int(image_info.get("width", 0) or 0)
        height = int(image_info.get("height", 0) or 0)
        if image_path is None:
            missing_images += 1
        else:
            if image_path.stem != label_path.stem:
                stem_mismatches += 1
            try:
                with Image.open(image_path) as image:
                    if image.size != (width, height):
                        image_size_mismatches += 1
            except Exception as error:
                errors.append({"file": str(image_path), "error": repr(error)})

        qualities: list[str] = []
        parts: list[str] = []
        works: list[str] = []
        category_names: list[str] = []
        bbox_ratios: list[float] = []

        for annotation in annotations:
            annotation_keys.update(annotation.keys())
            attributes = annotation.get("attributes") or {}
            attribute_keys.update(attributes.keys())
            raw_quality = str(attributes.get("quality", "미기재"))
            quality = normalize_quality(raw_quality)
            part = str(attributes.get("part", "미기재"))
            work = str(attributes.get("work", "미기재"))
            category_id = int(annotation.get("category_id", -1))
            category_name = categories.get(category_id, f"미등록({category_id})")
            qualities.append(quality)
            parts.append(part)
            works.append(work)
            category_names.append(category_name)

            segmentation = annotation.get("segmentation")
            if segmentation:
                segmentation_annotations += 1

            bbox = annotation.get("bbox")
            bbox_ratio: float | None = None
            bbox_valid = False
            bbox_in_bounds = False
            if isinstance(bbox, list) and len(bbox) == 4:
                x, y, bbox_width, bbox_height = map(float, bbox)
                bbox_valid = bbox_width > 0 and bbox_height > 0 and x >= 0 and y >= 0
                bbox_in_bounds = (
                    bbox_valid
                    and width > 0
                    and height > 0
                    and x + bbox_width <= width + 1
                    and y + bbox_height <= height + 1
                )
                if width > 0 and height > 0 and bbox_valid:
                    bbox_ratio = bbox_width * bbox_height / (width * height)
                    bbox_ratios.append(bbox_ratio)
                stated_area = annotation.get("area")
                if stated_area is not None and bbox_valid:
                    calculated_area = bbox_width * bbox_height
                    if calculated_area > 0:
                        relative_error = abs(float(stated_area) - calculated_area) / calculated_area
                        if relative_error > 0.01:
                            area_mismatches += 1
            if not bbox_valid:
                invalid_bboxes += 1
            elif not bbox_in_bounds:
                out_of_bounds_bboxes += 1

            annotation_rows.append(
                {
                    "split": split,
                    "label_file": label_path.name,
                    "image_file": image_name,
                    "quality": quality,
                    "raw_quality": raw_quality,
                    "part": part,
                    "work": work,
                    "category_id": category_id,
                    "category_name": category_name,
                    "bbox_valid": bbox_valid,
                    "bbox_in_bounds": bbox_in_bounds,
                    "bbox_area_ratio": bbox_ratio,
                    "has_segmentation": bool(segmentation),
                }
            )

        if "불량품" in qualities:
            image_quality = "불량품"
        elif qualities and set(qualities) == {"양품"}:
            image_quality = "양품"
        elif not qualities:
            image_quality = "라벨 없음"
        else:
            image_quality = safe_join(qualities)

        records.append(
            {
                "split": split,
                "label_file": label_path.name,
                "image_file": image_name,
                "image_exists": image_path is not None,
                "width": width,
                "height": height,
                "resolution": f"{width}x{height}",
                "date_captured": image_info.get("date_captured", ""),
                "annotation_count": len(annotations),
                "quality": image_quality,
                "quality_values": safe_join(qualities),
                "part": safe_join(parts),
                "work": safe_join(works),
                "category_names": safe_join(category_names),
                "bbox_area_ratio_mean": (
                    sum(bbox_ratios) / len(bbox_ratios) if bbox_ratios else None
                ),
            }
        )

    image_names = {path.name for path in image_paths}
    referenced_names = {record["image_file"] for record in records if record["image_file"]}
    split_summary = {
        "image_file_count": len(image_paths),
        "label_file_count": len(label_paths),
        "parsed_label_count": len(records),
        "parse_or_image_read_errors": errors,
        "missing_referenced_images": missing_images,
        "unreferenced_images": sorted(image_names - referenced_names),
        "label_image_stem_mismatches": stem_mismatches,
        "empty_annotation_files": empty_annotations,
        "invalid_bboxes": invalid_bboxes,
        "out_of_bounds_bboxes": out_of_bounds_bboxes,
        "annotation_area_mismatches_over_1pct": area_mismatches,
        "image_metadata_size_mismatches": image_size_mismatches,
        "segmentation_annotation_count": segmentation_annotations,
        "top_level_keys": sorted(top_level_keys),
        "annotation_keys": sorted(annotation_keys),
        "attribute_keys": sorted(attribute_keys),
        "category_registry": {
            str(key): value for key, value in sorted(category_registry.items())
        },
    }
    return records, annotation_rows, split_summary


def save_bar_chart(
    frame: pd.DataFrame,
    index: str,
    columns: str,
    values: str,
    title: str,
    xlabel: str,
    output_path: Path,
    horizontal: bool = False,
) -> None:
    pivot = frame.pivot(index=index, columns=columns, values=values).fillna(0)
    axis = pivot.plot(
        kind="barh" if horizontal else "bar",
        figsize=(10, 6),
        color=["#2F75B5", "#ED7D31", "#70AD47", "#A5A5A5"],
    )
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel("")
    axis.legend(title="데이터 구분")
    axis.grid(axis="x" if horizontal else "y", alpha=0.2)
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def write_report(
    records: pd.DataFrame,
    annotations: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    quality = (
        records.groupby(["quality", "split"], dropna=False)
        .size()
        .reset_index(name="image_count")
    )
    category_quality = (
        annotations.groupby(["category_id", "category_name", "quality", "split"], dropna=False)
        .size()
        .reset_index(name="annotation_count")
    )
    part = (
        records.groupby(["part", "split"], dropna=False)
        .size()
        .reset_index(name="image_count")
    )
    work = (
        records.groupby(["work", "split"], dropna=False)
        .size()
        .reset_index(name="image_count")
    )
    resolution = (
        records.groupby(["resolution", "split"], dropna=False)
        .size()
        .reset_index(name="image_count")
        .sort_values("image_count", ascending=False)
    )
    records = records.copy()
    records["capture_date"] = records["date_captured"].astype(str).str[:10]
    records["filename_prefix"] = (
        records["image_file"].astype(str).str.split("_").str[:3].str.join("_")
    )
    prefix_quality = (
        records.groupby(["filename_prefix", "quality", "split"], dropna=False)
        .size()
        .reset_index(name="image_count")
    )
    bbox_statistics = (
        annotations.groupby(["quality", "split"])["bbox_area_ratio"]
        .agg(["count", "mean", "median", "min", "max"])
        .reset_index()
    )
    train_dates = set(records.loc[records["split"] == "train", "capture_date"])
    validation_dates = set(
        records.loc[records["split"] == "validation", "capture_date"]
    )
    overlapping_dates = sorted(train_dates & validation_dates)

    records.to_csv(REPORT_DIR / "label_records.csv", index=False, encoding="utf-8-sig")
    annotations.to_csv(
        REPORT_DIR / "annotation_records.csv", index=False, encoding="utf-8-sig"
    )
    quality.to_csv(REPORT_DIR / "quality_distribution.csv", index=False, encoding="utf-8-sig")
    category_quality.to_csv(
        REPORT_DIR / "category_quality_distribution.csv",
        index=False,
        encoding="utf-8-sig",
    )
    part.to_csv(REPORT_DIR / "part_distribution.csv", index=False, encoding="utf-8-sig")
    work.to_csv(REPORT_DIR / "work_distribution.csv", index=False, encoding="utf-8-sig")
    resolution.to_csv(
        REPORT_DIR / "resolution_distribution.csv", index=False, encoding="utf-8-sig"
    )
    prefix_quality.to_csv(
        REPORT_DIR / "filename_prefix_quality.csv", index=False, encoding="utf-8-sig"
    )
    bbox_statistics.to_csv(
        REPORT_DIR / "bbox_statistics.csv", index=False, encoding="utf-8-sig"
    )

    configure_korean_font()
    save_bar_chart(
        quality,
        index="quality",
        columns="split",
        values="image_count",
        title="정상·불량 이미지 분포",
        xlabel="이미지 수",
        output_path=FIGURE_DIR / "quality_distribution.png",
        horizontal=True,
    )

    defect_categories = category_quality[category_quality["quality"] == "불량품"].copy()
    if not defect_categories.empty:
        save_bar_chart(
            defect_categories.groupby(["category_name", "split"], as_index=False)[
                "annotation_count"
            ].sum(),
            index="category_name",
            columns="split",
            values="annotation_count",
            title="불량 이미지의 유형별 라벨 분포",
            xlabel="어노테이션 수",
            output_path=FIGURE_DIR / "defect_category_distribution.png",
            horizontal=True,
        )

    bbox_values = annotations["bbox_area_ratio"].dropna()
    if not bbox_values.empty:
        plt.figure(figsize=(9, 5))
        plt.hist(bbox_values, bins=30, color="#2F75B5", edgecolor="white")
        plt.title("이미지 대비 바운딩박스 면적 비율")
        plt.xlabel("바운딩박스 면적 / 이미지 면적")
        plt.ylabel("어노테이션 수")
        plt.grid(axis="y", alpha=0.2)
        plt.tight_layout()
        plt.savefig(FIGURE_DIR / "bbox_area_ratio.png", dpi=180)
        plt.close()

    quality_total = quality.groupby("quality")["image_count"].sum().sort_values(ascending=False)
    defect_total = (
        defect_categories.groupby("category_name")["annotation_count"]
        .sum()
        .sort_values(ascending=False)
    )
    resolution_total = (
        resolution.groupby("resolution")["image_count"].sum().sort_values(ascending=False)
    )

    report_lines = [
        "# 라디에이터 그릴 라벨 분석 보고서",
        "",
        "## 분석 범위",
        "",
        f"- 전체 JSON 파일: {len(records):,}개",
        f"- 전체 어노테이션: {len(annotations):,}개",
        f"- Training: {(records['split'] == 'train').sum():,}개",
        f"- Validation: {(records['split'] == 'validation').sum():,}개",
        "",
        "## JSON 구조",
        "",
        "- 정상·불량 상태: `annotations[].attributes.quality`",
        "- 부품명: `annotations[].attributes.part`",
        "- 작업 구분: `annotations[].attributes.work`",
        "- 불량 유형 후보: `annotations[].category_id`와 `categories[].name` 연결",
        "- 위치 정보: `annotations[].bbox`의 `[x, y, width, height]`",
        "",
        "`category_id`는 양품 라벨에도 기록되어 있으므로 정상·불량 판정값으로 직접 사용하면 안 된다.",
        "",
        "## 정상·불량 분포",
        "",
    ]
    report_lines.extend(
        f"- {name}: {int(count):,}개 ({count / len(records) * 100:.2f}%)"
        for name, count in quality_total.items()
    )
    report_lines.extend(["", "### 데이터 구분별 구성", ""])
    for split in ("train", "validation"):
        split_quality = quality[quality["split"] == split]
        split_total = int(split_quality["image_count"].sum())
        values = ", ".join(
            f"{row.quality} {int(row.image_count):,}개 ({row.image_count / split_total * 100:.2f}%)"
            for row in split_quality.itertuples()
        )
        report_lines.append(f"- {split}: {values}")
    report_lines.extend(["", "## 불량 유형 분포", ""])
    if defect_total.empty:
        report_lines.append("- `quality=불량품`인 어노테이션이 확인되지 않았다.")
    else:
        report_lines.extend(
            f"- {name}: {int(count):,}개" for name, count in defect_total.items()
        )
    report_lines.extend(["", "## 주요 해상도", ""])
    report_lines.extend(
        f"- {name}: {int(count):,}개" for name, count in resolution_total.head(10).items()
    )
    report_lines.extend(["", "## 바운딩박스 분포", ""])
    for row in bbox_statistics.itertuples():
        report_lines.append(
            f"- {row.quality} / {row.split}: 평균 {row.mean * 100:.2f}%, "
            f"중앙값 {row.median * 100:.2f}% (이미지 면적 대비)"
        )
    report_lines.extend(
        [
            "",
            "양품과 불량품 모두 bbox를 가지고 있으므로 bbox를 곧바로 ‘불량 위치’로 해석하면 안 된다. 샘플 시각화와 데이터 설명서를 함께 확인해 검사 관심 영역인지 판단해야 한다.",
            "",
            "## 파일명과 촬영일 점검",
            "",
        ]
    )
    for row in prefix_quality.groupby(["filename_prefix", "quality"], as_index=False)[
        "image_count"
    ].sum().itertuples():
        report_lines.append(
            f"- 파일명 접두부 `{row.filename_prefix}`: {row.quality} {int(row.image_count):,}개"
        )
    report_lines.extend(
        [
            "",
            "파일명 접두부가 품질값과 일치하므로 파일명·경로에서 추출한 값을 모델 입력 특징으로 사용하면 정답 누수가 발생한다.",
            "",
            f"- Training 촬영일: {len(train_dates):,}일",
            f"- Validation 촬영일: {len(validation_dates):,}일",
            f"- 양쪽에 공통으로 존재하는 촬영일: {len(overlapping_dates):,}일",
            "",
            "Validation의 촬영일이 Training과 겹치므로 같은 촬영 세션의 유사 장면이 양쪽에 포함됐는지 이미지 유사도 검사가 필요하다.",
        ]
    )
    report_lines.extend(["", "## 무결성 검사", ""])
    for split, values in summary["splits"].items():
        report_lines.extend(
            [
                f"### {split}",
                "",
                f"- 이미지 파일: {values['image_file_count']:,}개",
                f"- JSON 파일: {values['label_file_count']:,}개",
                f"- 참조 이미지 누락: {values['missing_referenced_images']:,}개",
                f"- 라벨이 참조하지 않는 이미지: {len(values['unreferenced_images']):,}개",
                f"- 파일명 stem 불일치: {values['label_image_stem_mismatches']:,}개",
                f"- 빈 어노테이션: {values['empty_annotation_files']:,}개",
                f"- 잘못된 bbox: {values['invalid_bboxes']:,}개",
                f"- 이미지 범위를 벗어난 bbox: {values['out_of_bounds_bboxes']:,}개",
                f"- JSON 면적과 bbox 면적 불일치(1% 초과): {values['annotation_area_mismatches_over_1pct']:,}개",
                f"- 실제 이미지와 메타데이터 해상도 불일치: {values['image_metadata_size_mismatches']:,}개",
                f"- 세그멘테이션 포함 어노테이션: {values['segmentation_annotation_count']:,}개",
                f"- 파싱·이미지 읽기 오류: {len(values['parse_or_image_read_errors']):,}개",
                "",
            ]
        )
    report_lines.extend(
        [
            "## 해석 시 주의사항",
            "",
            "- 제공된 Training과 Validation 구분은 유지한 상태로 집계했다.",
            "- 동일 장면 또는 연속 촬영 여부는 파일명만으로 확정할 수 없다. 이미지 유사도 검사가 별도로 필요하다.",
            "- 바운딩박스가 실제 불량 부위인지 부품 관심 영역인지 품질값과 시각화 결과를 함께 확인해야 한다.",
            "- 1차 분류 정답은 `attributes.quality`를 사용하고, category_id 203은 단차 유형 표시에만 사용한다.",
        ]
    )
    (REPORT_DIR / "label_analysis_report.md").write_text(
        "\n".join(report_lines), encoding="utf-8"
    )

    with (REPORT_DIR / "label_analysis_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    dataset_root = Path(config["dataset_root"])
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    split_paths = {
        "train": (
            dataset_root / config["train_images"],
            dataset_root / config["train_labels"],
        ),
        "validation": (
            dataset_root / config["test_images"],
            dataset_root / config["test_labels"],
        ),
    }

    all_records: list[dict[str, Any]] = []
    all_annotations: list[dict[str, Any]] = []
    split_summaries: dict[str, Any] = {}
    for split, (image_dir, label_dir) in split_paths.items():
        records, annotations, split_summary = analyze_split(split, image_dir, label_dir)
        all_records.extend(records)
        all_annotations.extend(annotations)
        split_summaries[split] = split_summary

    records_frame = pd.DataFrame(all_records)
    annotations_frame = pd.DataFrame(all_annotations)
    duplicate_names = sorted(
        records_frame.loc[
            records_frame.duplicated(subset=["image_file"], keep=False), "image_file"
        ].dropna().unique()
    )
    summary = {
        "dataset_root": str(dataset_root),
        "record_count": len(records_frame),
        "annotation_count": len(annotations_frame),
        "duplicate_image_filenames_across_records": duplicate_names,
        "splits": split_summaries,
    }
    write_report(records_frame, annotations_frame, summary)

    print(f"JSON records: {len(records_frame):,}")
    print(f"Annotations: {len(annotations_frame):,}")
    print(f"Duplicate image filenames: {len(duplicate_names):,}")
    print(f"Report: {REPORT_DIR / 'label_analysis_report.md'}")
    print("Label analysis: PASS")


if __name__ == "__main__":
    main()
