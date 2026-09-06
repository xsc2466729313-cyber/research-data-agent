"""Annotate the two current-run screenshots in the supplied red-callout style.

The source images are temporary browser captures in ``.tmp``.  The two PNGs
written to ``docs/images`` are the review-facing assets: the UI remains legible,
while short red labels, boxes, and arrows identify the evidence a reader
should notice first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
TMP_DIR = ROOT / ".tmp"
IMAGE_DIR = ROOT / "docs" / "images"
FONT_PATH = Path("C:/Windows/Fonts/msyh.ttc")

RED = (205, 36, 36)
RED_DARK = (166, 28, 28)
WHITE = (255, 255, 255)


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.ImageFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=face)
    return right - left, bottom - top


def label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    size: tuple[int, int],
    text: str,
    font_size: int = 28,
) -> tuple[int, int, int, int]:
    x, y = xy
    width, height = size
    # A subtle offset keeps the callout readable against the page without
    # creating the thick, overlapping bands in the old mobile annotation.
    draw.rounded_rectangle((x + 2, y + 3, x + width + 2, y + height + 3), radius=12, fill=(245, 245, 245))
    draw.rounded_rectangle((x, y, x + width, y + height), radius=12, fill=WHITE, outline=RED, width=4)
    face = font(font_size)
    tw, th = text_size(draw, text, face)
    if tw > width - 20:
        face = font(max(18, int(font_size * (width - 20) / max(tw, 1))))
        tw, th = text_size(draw, text, face)
    draw.text((x + (width - tw) / 2, y + (height - th) / 2 - 2), text, font=face, fill=RED_DARK)
    return x, y, x + width, y + height


def outline(draw: ImageDraw.ImageDraw, region: tuple[int, int, int, int], width: int = 4) -> None:
    draw.rounded_rectangle(region, radius=12, outline=RED, width=width)


def arrow(draw: ImageDraw.ImageDraw, points: Iterable[tuple[int, int]], width: int = 4) -> None:
    points = list(points)
    draw.line(points, fill=RED, width=width, joint="curve")
    if len(points) < 2:
        return
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    head = 13
    left = (x2 - ux * head + px * head * 0.55, y2 - uy * head + py * head * 0.55)
    right = (x2 - ux * head - px * head * 0.55, y2 - uy * head - py * head * 0.55)
    draw.polygon([(x2, y2), left, right], fill=RED)


def annotate_quality_data() -> Path:
    source_path = TMP_DIR / "current-reference-quality-data-clean.png"
    output_path = IMAGE_DIR / "kernel-lab-current-quality-data-callout-20260906.png"
    image = Image.open(source_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    # Coordinates are tied to the 1440×1100 viewport emitted by the capture
    # script. They deliberately frame the cards and the count text, not the
    # explanatory prose around them.
    gate_group = (76, 463, 1041, 576)
    gate_four = (1047, 463, 1364, 576)
    patient_sample_count = (232, 682, 470, 711)
    outline(draw, gate_group)
    outline(draw, gate_four)
    outline(draw, patient_sample_count)

    label_one = label(draw, (250, 274), (300, 54), "三层基础质量通过", 28)
    label_two = label(draw, (1030, 274), (310, 54), "科研适用性独立校验", 27)
    label_three = label(draw, (448, 598), (470, 54), "69名患者·156个样本完成结构化", 25)

    arrow(draw, [((label_one[0] + label_one[2]) // 2, label_one[3]), (520, 421), (540, 463)])
    arrow(draw, [((label_two[0] + label_two[2]) // 2, label_two[3]), (1200, 421), (1200, 463)])
    arrow(draw, [(label_three[0], (label_three[1] + label_three[3]) // 2), (430, 672), (355, 696)])

    image.save(output_path, optimize=True)
    return output_path


def annotate_raw_modal() -> Path:
    source_path = TMP_DIR / "current-reference-raw-modal-clean.png"
    output_path = IMAGE_DIR / "kernel-lab-current-raw-characteristics-callout-20260906.png"
    image = Image.open(source_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    # The browser capture constrains the scrollable audit table to eight visible
    # rows, matching the proportions of the supplied reference while retaining
    # the scrollbar and all remaining raw rows for interactive review.
    normalized_column = (523, 376, 836, 736)
    raw_column = (829, 376, 1083, 736)
    provenance_note = (357, 747, 1082, 778)
    outline(draw, normalized_column)
    outline(draw, raw_column)
    outline(draw, provenance_note)

    label_one = label(draw, (85, 160), (310, 54), "标准值便于分析", 28)
    label_two = label(draw, (1030, 160), (320, 54), "原值保留，可回查", 28)
    label_three = label(draw, (70, 805), (330, 54), "原始记录完整保留", 27)

    arrow(draw, [(label_one[2], (label_one[1] + label_one[3]) // 2), (735, 330), (680, 376)])
    arrow(draw, [(label_two[0], (label_two[1] + label_two[3]) // 2), (1010, 330), (950, 376)])
    arrow(draw, [(label_three[2], (label_three[1] + label_three[3]) // 2), (520, 790), (590, 762)])

    image.save(output_path, optimize=True)
    return output_path


if __name__ == "__main__":
    outputs = [annotate_quality_data(), annotate_raw_modal()]
    for path in outputs:
        print(path)
