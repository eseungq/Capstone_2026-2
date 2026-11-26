"""양품·불량품 JSON 라벨의 바운딩박스 예시를 한 장으로 만든다."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("D:/162.부품 품질 검사 영상 데이터(자동차)/radiator_grille")
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "figures" / "label_samples.png"
FONT_PATH = Path("C:/Windows/Fonts/malgun.ttf")


def load_items() -> dict[str, list[tuple[Path, Path, dict]]]:
    grouped: dict[str, list[tuple[Path, Path, dict]]] = {"양품": [], "불량품": []}
    label_dir = DATA_ROOT / "train" / "labels"
    image_dir = DATA_ROOT / "train" / "images"
    for label_path in sorted(label_dir.glob("*.json")):
        with label_path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        annotation = data["annotations"][0]
        quality = str(annotation["attributes"]["quality"])
        if quality not in grouped:
            continue
        image_path = image_dir / data["images"][0]["file_name"]
        grouped[quality].append((image_path, label_path, annotation))
    return grouped


def choose_spread(items: list, count: int = 3) -> list:
    if len(items) <= count:
        return items
    positions = [round(index * (len(items) - 1) / (count - 1)) for index in range(count)]
    return [items[position] for position in positions]


def render_sample(
    image_path: Path,
    annotation: dict,
    quality: str,
    panel_size: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> Image.Image:
    panel_width, panel_height = panel_size
    caption_height = 42
    content_height = panel_height - caption_height
    with Image.open(image_path) as source:
        source = source.convert("RGB")
        scale = min(panel_width / source.width, content_height / source.height)
        resized = source.resize(
            (round(source.width * scale), round(source.height * scale)),
            Image.Resampling.LANCZOS,
        )

    panel = Image.new("RGB", panel_size, "white")
    offset_x = (panel_width - resized.width) // 2
    offset_y = caption_height + (content_height - resized.height) // 2
    panel.paste(resized, (offset_x, offset_y))
    draw = ImageDraw.Draw(panel)
    x, y, width, height = map(float, annotation["bbox"])
    box = (
        round(offset_x + x * scale),
        round(offset_y + y * scale),
        round(offset_x + (x + width) * scale),
        round(offset_y + (y + height) * scale),
    )
    color = "#2E8B57" if quality == "양품" else "#D62728"
    draw.rectangle(box, outline=color, width=5)
    draw.rectangle((0, 0, panel_width, caption_height), fill=color)
    draw.text((12, 7), f"{quality} · 단차 · bbox", fill="white", font=font)
    return panel


def main() -> None:
    grouped = load_items()
    font = (
        ImageFont.truetype(str(FONT_PATH), 23)
        if FONT_PATH.exists()
        else ImageFont.load_default()
    )
    panel_size = (600, 400)
    canvas = Image.new("RGB", (panel_size[0] * 3, panel_size[1] * 2), "white")
    for row, quality in enumerate(("양품", "불량품")):
        for column, (image_path, _, annotation) in enumerate(
            choose_spread(grouped[quality])
        ):
            panel = render_sample(image_path, annotation, quality, panel_size, font)
            canvas.paste(panel, (column * panel_size[0], row * panel_size[1]))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT_PATH, quality=92)
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
