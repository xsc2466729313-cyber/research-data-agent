from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "images" / "system-architecture-journal-20260831.png"
OUTPUT = ROOT / "docs" / "images" / "system-architecture-journal-small-arrows-20260901.png"


def _polygon_overlay(
    image: Image.Image,
    points: list[tuple[float, float]],
    color: tuple[int, int, int],
    *,
    scale: int = 4,
) -> None:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    left = int(min(xs)) - 2
    top = int(min(ys)) - 2
    right = int(max(xs)) + 3
    bottom = int(max(ys)) + 3
    overlay = Image.new("RGBA", ((right - left) * scale, (bottom - top) * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.polygon(
        [((x - left) * scale, (y - top) * scale) for x, y in points],
        fill=(*color, 255),
    )
    overlay = overlay.resize((right - left, bottom - top), Image.Resampling.LANCZOS)
    image.alpha_composite(overlay, (left, top))


def _down_arrow(
    image: Image.Image,
    *,
    center_x: float,
    top: float,
    bottom: float,
    color: tuple[int, int, int],
    shaft_width: float = 3,
    head_width: float = 10,
    head_height: float = 5,
) -> None:
    half_shaft = shaft_width / 2
    half_head = head_width / 2
    head_top = bottom - head_height
    _polygon_overlay(
        image,
        [
            (center_x - half_shaft, top),
            (center_x + half_shaft, top),
            (center_x + half_shaft, head_top),
            (center_x + half_head, head_top),
            (center_x, bottom),
            (center_x - half_head, head_top),
            (center_x - half_shaft, head_top),
        ],
        color,
    )


def _double_vertical_arrow(
    image: Image.Image,
    *,
    center_x: float,
    top: float,
    bottom: float,
    color: tuple[int, int, int],
    shaft_width: float = 3,
    head_width: float = 9,
    head_height: float = 5,
) -> None:
    half_shaft = shaft_width / 2
    half_head = head_width / 2
    upper_base = top + head_height
    lower_base = bottom - head_height
    _polygon_overlay(
        image,
        [
            (center_x, top),
            (center_x + half_head, upper_base),
            (center_x + half_shaft, upper_base),
            (center_x + half_shaft, lower_base),
            (center_x + half_head, lower_base),
            (center_x, bottom),
            (center_x - half_head, lower_base),
            (center_x - half_shaft, lower_base),
            (center_x - half_shaft, upper_base),
            (center_x - half_head, upper_base),
        ],
        color,
    )


def main() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    if image.size != (1122, 1402):
        raise ValueError(f"Unexpected architecture image size: {image.size}")

    draw = ImageDraw.Draw(image)
    for box in [
        (540, 283, 579, 308),
        (541, 483, 581, 509),
        (550, 690, 571, 718),
        (130, 1014, 151, 1042),
        (969, 1018, 990, 1045),
    ]:
        draw.rectangle(box, fill=(255, 255, 255, 255))

    _down_arrow(image, center_x=561, top=284, bottom=306, color=(0, 59, 156))
    _double_vertical_arrow(image, center_x=561, top=485, bottom=507, color=(4, 59, 158))
    _double_vertical_arrow(image, center_x=560.5, top=691, bottom=716, color=(5, 54, 139))
    _double_vertical_arrow(image, center_x=140, top=1015, bottom=1040, color=(2, 60, 151))
    _double_vertical_arrow(image, center_x=979.5, top=1019, bottom=1043, color=(6, 39, 132))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(OUTPUT, quality=96, optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
