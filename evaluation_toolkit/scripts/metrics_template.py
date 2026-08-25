from __future__ import annotations
import math
from typing import Iterable, Sequence, Set, Tuple

def precision_recall_f1(gold: Set, pred: Set):
    tp = len(gold & pred)
    fp = len(pred - gold)
    fn = len(gold - pred)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}

def cell_detection_f1(gold_error_cells: Set[Tuple[int, str]], pred_error_cells: Set[Tuple[int, str]]):
    """Cell 用 (row_id, column_name) 表示。"""
    return precision_recall_f1(gold_error_cells, pred_error_cells)

def ndcg_at_k(relevances: Sequence[float], k: int = 10) -> float:
    rel = list(relevances)[:k]
    dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rel))
    ideal = sorted(rel, reverse=True)
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg else 0.0

def integration_macro_f1(schema_f1: float, entity_f1: float) -> float:
    """仅用于项目内部总览，不作为外部标准指标。"""
    return (schema_f1 + entity_f1) / 2

def geometric_fitness(dim_scores_0_to_4: Iterable[float]) -> float:
    vals = [max(0.0, min(4.0, float(x))) / 4.0 for x in dim_scores_0_to_4]
    if not vals or any(v == 0 for v in vals):
        return 0.0
    prod = math.prod(vals)
    return 100.0 * prod ** (1.0 / len(vals))

if __name__ == "__main__":
    print("Cleaning example:", cell_detection_f1({(1,'age'), (2,'HER2')}, {(1,'age'), (3,'ER')}))
    print("nDCG example:", ndcg_at_k([3, 1, 2, 0, 2], 5))
    print("Fitness example:", geometric_fitness([4, 3, 4, 3]))
