# -*- coding: utf-8 -*-
"""Generate fully Chinese architecture and agent-loop figures for the report."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, FancyBboxPatch as Box
from matplotlib.patches import Circle, FancyArrow

ROOT = Path(r"C:\Users\xsc\OneDrive\Desktop\CODEX_项目启动包_乳腺癌精准治疗科研数据智能体")
OUT_DOCS = ROOT / "docs" / "images"
OUT_SHOTS = ROOT / "output" / "report_xsc"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Source Han Sans SC"]
plt.rcParams["axes.unicode_minus"] = False

TEAL = "#1F6F64"
TEAL_DARK = "#164E48"
CREAM = "#F4F7F4"
CARD = "#FFFFFF"
LINE = "#2A6B62"
ACCENT = "#3D9B8F"


def rounded(ax, x, y, w, h, fc=CARD, ec=TEAL, lw=1.6, radius=0.04):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.012,rounding_size={radius}",
        linewidth=lw,
        edgecolor=ec,
        facecolor=fc,
        mutation_aspect=0.6,
    )
    ax.add_patch(box)
    return box


def save(fig, name: str) -> None:
    OUT_DOCS.mkdir(parents=True, exist_ok=True)
    OUT_SHOTS.mkdir(parents=True, exist_ok=True)
    for folder in (OUT_DOCS, OUT_SHOTS):
        path = folder / name
        fig.savefig(path, dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
        print(path)


def draw_architecture() -> None:
    fig, ax = plt.subplots(figsize=(13.2, 5.6), facecolor="white")
    ax.set_xlim(0, 13.2)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    ax.set_title("乳腺癌科研数据智能体　系统架构", fontsize=18, color=TEAL_DARK, pad=10, fontweight="bold")

    layers = [
        (0.35, "第一层", "科研需求与数据发现", ["研究问题解析", "研究规格生成", "公开数据库发现"]),
        (4.55, "第二层", "多源处理与融合", ["字段标准化", "实体对齐", "同研究内整合"]),
        (8.75, "第三层", "质量闭环与输出", ["四层质量门", "分析矩阵", "多格式导出"]),
    ]
    for x, kicker, title, items in layers:
        rounded(ax, x, 1.35, 3.85, 3.55, fc=CREAM, ec=TEAL, lw=2.0, radius=0.08)
        ax.text(x + 1.92, 4.52, kicker, ha="center", va="center", fontsize=11, color=ACCENT, fontweight="bold")
        ax.text(x + 1.92, 4.08, title, ha="center", va="center", fontsize=14, color=TEAL_DARK, fontweight="bold")
        for i, item in enumerate(items):
            yy = 3.35 - i * 0.72
            rounded(ax, x + 0.28, yy - 0.22, 3.28, 0.55, fc=CARD, ec="#B7D4CE", lw=1.1, radius=0.05)
            ax.text(x + 1.92, yy + 0.05, item, ha="center", va="center", fontsize=12, color=TEAL_DARK)

    for x in (4.22, 8.42):
        ax.annotate(
            "",
            xy=(x + 0.28, 3.1),
            xytext=(x - 0.28, 3.1),
            arrowprops=dict(arrowstyle="-|>", color=TEAL, lw=2.4, mutation_scale=14),
        )

    ax.annotate(
        "",
        xy=(2.28, 0.72),
        xytext=(10.68, 0.72),
        arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.8, mutation_scale=12, connectionstyle="arc3,rad=0.0"),
    )
    rounded(ax, 4.15, 0.38, 4.9, 0.7, fc=CARD, ec=ACCENT, lw=1.4, radius=0.08)
    ax.text(6.6, 0.73, "目标闭环：持续换方法，直至形成可用科研数据包", ha="center", va="center", fontsize=11, color=TEAL_DARK)
    save(fig, "agent-architecture.png")
    save(fig, "13_architecture.png")
    plt.close(fig)


def draw_loop() -> None:
    fig, ax = plt.subplots(figsize=(13.6, 5.4), facecolor="white")
    ax.set_xlim(0, 13.6)
    ax.set_ylim(0, 5.4)
    ax.axis("off")
    ax.set_title("智能体换方法闭环", fontsize=18, color=TEAL_DARK, pad=10, fontweight="bold")

    steps = [
        ("1 观察", "查看主表、结局域\n与队列规模"),
        ("2 诊断", "识别缺口类型\n并定位改进方向"),
        ("3 换方法", "启用尚未尝试的\n检索与解析策略"),
        ("4 执行", "调用公开数据库\n完成真实数据获取"),
        ("5 判定", "达标则输出结果\n可继续则进入下一轮"),
    ]
    width = 2.18
    y = 1.85
    for i, (title, detail) in enumerate(steps):
        x = 0.35 + i * 2.62
        rounded(ax, x, y, width, 2.55, fc=CREAM, ec=TEAL, lw=1.8, radius=0.08)
        circ = Circle((x + width / 2, 4.05), 0.22, facecolor=TEAL, edgecolor=TEAL)
        ax.add_patch(circ)
        ax.text(x + width / 2, 4.05, str(i + 1), ha="center", va="center", fontsize=11, color="white", fontweight="bold")
        ax.text(x + width / 2, 3.52, title.split(" ", 1)[1], ha="center", va="center", fontsize=14, color=TEAL_DARK, fontweight="bold")
        ax.text(x + width / 2, 2.55, detail, ha="center", va="center", fontsize=11, color=TEAL_DARK, linespacing=1.45)
        if i < 4:
            ax.annotate(
                "",
                xy=(x + width + 0.18, 3.05),
                xytext=(x + width + 0.02, 3.05),
                arrowprops=dict(arrowstyle="-|>", color=TEAL, lw=2.2, mutation_scale=12),
            )

    ax.annotate(
        "",
        xy=(1.45, 1.35),
        xytext=(12.05, 1.35),
        arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.8, mutation_scale=12),
    )
    ax.text(6.8, 1.08, "持续检索，直到形成可用科研数据包或达到轮次门限", ha="center", va="center", fontsize=12, color=TEAL_DARK)
    rounded(ax, 3.3, 0.28, 7.0, 0.58, fc=CARD, ec=ACCENT, lw=1.3, radius=0.06)
    ax.text(6.8, 0.57, "同研究内对齐　·　来源可追溯　·　结局与问题同域", ha="center", va="center", fontsize=11, color=TEAL_DARK)
    save(fig, "agent-loop.png")
    save(fig, "14_agent_loop.png")
    plt.close(fig)


if __name__ == "__main__":
    draw_architecture()
    draw_loop()
