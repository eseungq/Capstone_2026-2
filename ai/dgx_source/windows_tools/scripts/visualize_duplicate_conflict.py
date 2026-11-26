"""동일 이미지에 서로 다른 품질·bbox가 부여된 사례를 시각화한다."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("D:/162.부품 품질 검사 영상 데이터(자동차)/radiator_grille")
CSV_PATH = PROJECT_ROOT / "outputs" / "reports" / "exact_duplicate_images.csv"
OUTPUT_PATH = (
    PROJECT_ROOT / "outputs" / "figures" / "duplicate_quality_conflict_example.png"
)
FONT_PATH = Path("C:/Windows/Fonts/malgun.ttf")


def main() -> None:
    frame = pd.read_csv(CSV_PATH)
    quality_counts = frame.groupby("duplicate_group")["quality"].nunique()
    conflict_groups = quality_counts[quality_counts > 1]
    if conflict_groups.empty:
        print("품질 라벨 충돌 그룹이 없습니다.")
        return

    group_number = int(conflict_groups.index[0])
    rows = frame[frame["duplicate_group"] == group_number]
    first = rows.iloc[0]
    image_path = DATA_ROOT / str(first["split"]) / "images" / str(first["file_name"])
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = (
        ImageFont.truetype(str(FONT_PATH), max(28, image.width // 80))
        if FONT_PATH.exists()
        else ImageFont.load_default()
    )

    colors = {"양품": "#00A651", "불량품": "#E31A1C"}
    for _, row in rows.iterrows():
        x, y, width, height = json.loads(row["bbox"])
        color = colors.get(str(row["quality"]), "#FFD700")
        line_width = max(5, image.width // 400)
        draw.rectangle((x, y, x + width, y + height), outline=color, width=line_width)
        label = f"{row['quality']} bbox"
        text_box = draw.textbbox((x, y), label, font=font)
        text_height = text_box[3] - text_box[1]
        draw.rectangle((x, max(0, y - text_height - 12), x + 240, y), fill=color)
        draw.text((x + 6, max(0, y - text_height - 8)), label, fill="white", font=font)

    max_width = 1800
    if image.width > max_width:
        scale = max_width / image.width
        image = image.resize(
            (max_width, round(image.height * scale)), Image.Resampling.LANCZOS
        )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT_PATH, quality=92)
    print(f"Duplicate group: {group_number}")
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
