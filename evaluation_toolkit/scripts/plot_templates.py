"""
读取 templates/results_template.csv 后生成基础结果图。
正式论文/PPT中建议一图一主题；不要把不同量纲硬塞在同一张图。
"""
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

DATA = Path(__file__).resolve().parents[1] / "templates" / "results_template.csv"

def plot_metric(stage: str, metric: str, output: str):
    df = pd.read_csv(DATA)
    sub = df[(df["stage"] == stage) & (df["metric"] == metric)].dropna(subset=["value"])
    if sub.empty:
        print(f"No data for {stage}/{metric}")
        return
    agg = sub.groupby("method", as_index=False)["value"].mean().sort_values("value")
    fig, ax = plt.subplots(figsize=(8, max(4, len(agg)*0.45)))
    ax.barh(agg["method"], agg["value"])
    ax.set_xlabel(metric)
    ax.set_title(f"{stage}: {metric}")
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)

if __name__ == "__main__":
    # 填入真实 results_template.csv 后启用
    plot_metric("cleaning", "f1", "cleaning_f1.png")
