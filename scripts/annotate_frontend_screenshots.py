"""Create red, non-overlapping explanatory callouts for review screenshots."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "docs" / "images"
FONT_PATH = Path("C:/Windows/Fonts/msyh.ttc")


def font(size: int):
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        return ImageFont.load_default()


TITLE = font(27)
BODY = font(20)
SMALL = font(16)
RED = (201, 39, 39)
RED_DARK = (145, 26, 26)
INK = (44, 55, 68)
PAPER = (255, 249, 247)
LINE = (235, 174, 174)


def marker(draw: ImageDraw.ImageDraw, xy: tuple[int, int], number: int):
    x, y = xy
    draw.ellipse((x - 15, y - 15, x + 15, y + 15), fill=RED, outline="white", width=3)
    text = str(number)
    bounds = draw.textbbox((0, 0), text, font=BODY)
    draw.text((x - (bounds[2] - bounds[0]) / 2, y - (bounds[3] - bounds[1]) / 2 - 2), text, font=BODY, fill="white")


def box(draw: ImageDraw.ImageDraw, region: tuple[int, int, int, int]):
    draw.rounded_rectangle(region, radius=10, outline=RED, width=4)


def arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]]):
    """Draw a thin red polyline and a triangular arrowhead at its final point."""
    draw.line(points, fill=RED, width=3, joint="curve")
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    size = 10
    tip = (x2, y2)
    left = (x2 - ux * size + px * size * 0.55, y2 - uy * size + py * size * 0.55)
    right = (x2 - ux * size - px * size * 0.55, y2 - uy * size - py * size * 0.55)
    draw.polygon([tip, left, right], fill=RED)


def legend_panel(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    title: str,
    items: list[tuple[int, str, str, int]],
):
    title_lines = title.count("\n") + 1
    height = 104 + len(items) * 104 + max(0, title_lines - 1) * 32
    draw.rounded_rectangle((x, y, x + width, y + height), radius=18, fill=PAPER, outline=LINE, width=2)
    draw.multiline_text((x + 22, y + 18), title, font=TITLE, fill=RED_DARK, spacing=4)
    note_y = y + 70 + max(0, title_lines - 1) * 32
    draw.text((x + 22, note_y), "红框定位，箭头说明；原始界面内容不覆盖。", font=SMALL, fill=INK)
    row_y = note_y + 48
    for number, heading, detail, target_y in items:
        marker(draw, (x + 30, row_y + 27), number)
        draw.text((x + 60, row_y + 5), heading, font=BODY, fill=RED_DARK)
        draw.text((x + 60, row_y + 39), detail, font=SMALL, fill=INK)
        arrow(draw, [(x, row_y + 27), (x - 12, row_y + 27), (x - 28, target_y), (x - 42, target_y)])
        row_y += 104


def planner_desktop():
    source = Image.open(IMAGE_DIR / "frontend-home-clean-20260906.png").convert("RGB")
    width, height = source.size
    canvas = Image.new("RGB", (width + 430, height), "white")
    canvas.paste(source, (0, 0))
    draw = ImageDraw.Draw(canvas)
    regions = [
        ((14, 134, 207, 405), (207, 165)),
        ((284, 220, 1046, 444), (1046, 270)),
        ((249, 824, 1080, 974), (1080, 850)),
        ((1099, 10, 1429, 75), (1429, 43)),
        ((1190, 905, 1428, 987), (1428, 944)),
    ]
    for number, (region, point) in enumerate(regions, 1):
        box(draw, region)
        marker(draw, point, number)
    legend_panel(
        draw,
        width + 18,
        22,
        390,
        "科研助手首页 · 关键区域",
        [
            (1, "五阶段规划", "提出方向 → 准备数据", 165),
            (2, "示例问题卡", "从研究想法进入问题规划", 270),
            (3, "研究问题输入", "提交后启动真实规划", 850),
            (4, "结果审查标签", "依据、方案、数据准备、覆盖矩阵", 43),
            (5, "科研助手（科研兔）", "独立只读解析入口", 944),
        ],
    )
    canvas.save(IMAGE_DIR / "frontend-home-annotated-20260906.png", optimize=True)


def planner_mobile():
    source = Image.open(IMAGE_DIR / "frontend-home-mobile-clean-20260906.png").convert("RGB")
    width, height = source.size
    legend_x = width + 40
    canvas = Image.new("RGB", (legend_x + 380, height), "white")
    canvas.paste(source, (0, 0))
    draw = ImageDraw.Draw(canvas)
    regions = [
        ((10, 195, 380, 649), (380, 230)),
        ((10, 685, 380, 834), (380, 725)),
        ((11, 854, 379, 1235), (379, 900)),
        ((254, 731, 378, 820), (378, 770)),
    ]
    for number, (region, point) in enumerate(regions, 1):
        box(draw, region)
        marker(draw, point, number)
    legend_panel(
        draw,
        legend_x,
        44,
        350,
        "移动端科研助手\n· 关键区域",
        [
            (1, "示例问题卡", "四个研究方向入口", 230),
            (2, "研究问题输入", "输入一句话开始研究", 725),
            (3, "结果审查标签", "窄屏下向下展开", 900),
            (4, "科研助手（科研兔）", "独立标注，不混入输入区", 770),
        ],
    )
    canvas.save(IMAGE_DIR / "frontend-home-mobile-annotated-20260906.png", optimize=True)


def companion_panel():
    source = Image.open(IMAGE_DIR / "research-companion-panel-20260906.png").convert("RGB")
    width, height = source.size
    canvas = Image.new("RGB", (width + 350, height), "white")
    canvas.paste(source, (0, 0))
    draw = ImageDraw.Draw(canvas)
    box(draw, (4, 4, width - 4, height - 4))
    marker(draw, (width - 24, 26), 1)
    panel_x = width + 26
    draw.rounded_rectangle((panel_x, 62, panel_x + 300, 290), radius=16, fill=PAPER, outline=LINE, width=2)
    draw.text((panel_x + 20, 84), "科研助手（科研兔）", font=TITLE, fill=RED_DARK)
    draw.multiline_text((panel_x + 20, 132), "独立的只读解析入口\n帮助整理研究问题与主入口上下文\n不替代后端证据和质量门。", font=BODY, fill=INK, spacing=8)
    arrow(draw, [(panel_x, 170), (width + 10, 170), (width - 24, 28)])
    canvas.save(IMAGE_DIR / "research-companion-panel-annotated-20260906.png", optimize=True)


def kernel_overview():
    source = Image.open(IMAGE_DIR / "kernel-lab-desktop-clean-20260906.png").convert("RGB")
    width, height = source.size
    canvas = Image.new("RGB", (width + 430, height), "white")
    canvas.paste(source, (0, 0))
    draw = ImageDraw.Draw(canvas)
    regions = [
        ((58, 125, 1382, 384), (1382, 180)),
        ((58, 400, 1382, 488), (1382, 440)),
        ((58, 504, 1382, 1270), (1382, 640)),
        ((77, 1389, 1363, 1612), (1363, 1470)),
        ((58, 1790, 1382, 2287), (1382, 1980)),
    ]
    for number, (region, point) in enumerate(regions, 1):
        box(draw, region)
        marker(draw, point, number)
    legend_panel(
        draw,
        width + 18,
        38,
        390,
        "内核实验室 · 前端关键区域",
        [
            (1, "内核总览", "研究协议、边界与运行说明", 180),
            (2, "运行配置", "模型与数据边界状态", 440),
            (3, "Agent 架构图", "规划—证据—独立校验—交付", 640),
            (4, "Agent Runtime", "7 个角色的真实运行状态位", 1470),
            (5, "任务入口", "一句话启动自主研究", 1980),
        ],
    )
    canvas.save(IMAGE_DIR / "kernel-lab-desktop-annotated-20260906.png", optimize=True)


def architecture_crop():
    source = Image.open(IMAGE_DIR / "kernel-lab-agent-architecture-20260906.png").convert("RGB")
    width, height = source.size
    canvas = Image.new("RGB", (width + 360, height), "white")
    canvas.paste(source, (0, 0))
    draw = ImageDraw.Draw(canvas)
    box(draw, (20, 78, width - 20, 742))
    marker(draw, (width - 34, 96), 1)
    x = width + 22
    draw.rounded_rectangle((x, 140, x + 310, 390), radius=16, fill=PAPER, outline=LINE, width=2)
    draw.text((x + 18, 164), "Agent 流程图", font=TITLE, fill=RED_DARK)
    draw.multiline_text((x + 18, 214), "红框定位主流程区域\n任务规划 → 证据与规则\n→ 独立校验 → 可追溯交付。", font=BODY, fill=INK, spacing=8)
    arrow(draw, [(x, 250), (width + 5, 250), (width - 34, 96)])
    canvas.save(IMAGE_DIR / "kernel-lab-agent-architecture-annotated-20260906.png", optimize=True)


if __name__ == "__main__":
    planner_desktop()
    planner_mobile()
    companion_panel()
    kernel_overview()
    architecture_crop()
    print("Wrote red, non-overlapping explanatory callouts")
