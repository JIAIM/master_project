"""Аналіз якості питань за класичною теорією тестів (CTT): індекс складності p,
розрізнювальна здатність r_pb, непрацюючі хибні варіанти, надійність тесту KR-20.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

MIN_N_FOR_DISCRIMINATION = 5
NONFUNCTIONAL_DISTRACTOR_SHARE = 0.05


@dataclass(frozen=True)
class Response:
    participant_id: int
    question_id: int
    is_correct: bool
    response_ms: int | None = None
    option_ids: tuple[int, ...] = ()


@dataclass
class ItemStats:
    question_id: int
    n: int
    p_value: float | None
    discrimination: float | None
    avg_response_ms: float | None
    option_counts: dict[int, int] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)


@dataclass
class TestStats:
    n_participants: int
    n_items: int
    mean_score: float | None
    kr20: float | None
    items: list[ItemStats]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _pvariance(xs: list[float]) -> float:
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx, my = _mean(xs), _mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def kr20(matrix: list[list[int]]) -> float | None:
    """matrix[учасник][питання] ∈ {0,1}; потрібно ≥2 питань і ненульова дисперсія."""
    if not matrix or len(matrix[0]) < 2:
        return None
    k = len(matrix[0])
    totals = [sum(row) for row in matrix]
    var_total = _pvariance(totals)
    if var_total == 0:
        return None
    pq = 0.0
    for j in range(k):
        p = _mean([row[j] for row in matrix])
        pq += p * (1 - p)
    return (k / (k - 1)) * (1 - pq / var_total)


def analyze(
    responses: Iterable[Response],
    correct_options: dict[int, set[int]] | None = None,
    all_options: dict[int, set[int]] | None = None,
) -> TestStats:
    """all_options потрібен, щоб знайти хибні варіанти, які не обрав ніхто."""
    responses = list(responses)
    correct_options = correct_options or {}
    all_options = all_options or {}
    by_q: dict[int, dict[int, Response]] = defaultdict(dict)
    for r in responses:
        by_q[r.question_id][r.participant_id] = r

    q_ids = sorted(by_q)
    p_ids = sorted({r.participant_id for r in responses})
    # Матриця 0/1; немає відповіді = 0
    matrix = [[1 if (r := by_q[q].get(p)) and r.is_correct else 0 for q in q_ids] for p in p_ids]
    totals = [sum(row) for row in matrix]

    items: list[ItemStats] = []
    for j, q in enumerate(q_ids):
        answers = list(by_q[q].values())
        n = len(answers)
        p_value = sum(a.is_correct for a in answers) / n if n else None
        times = [a.response_ms for a in answers if a.response_ms is not None]

        discrimination = None
        if len(p_ids) >= MIN_N_FOR_DISCRIMINATION:
            item = [row[j] for row in matrix]
            rest = [t - x for t, x in zip(totals, item)]
            discrimination = pearson([float(x) for x in item], [float(x) for x in rest])

        counts: dict[int, int] = {oid: 0 for oid in all_options.get(q, ())}
        for a in answers:
            for oid in a.option_ids:
                counts[oid] = counts.get(oid, 0) + 1

        flags: list[str] = []
        if p_value is not None and n >= MIN_N_FOR_DISCRIMINATION:
            if p_value > 0.9:
                flags.append("too_easy")
            elif p_value < 0.2:
                flags.append("too_hard")
        if discrimination is not None:
            if discrimination < 0:
                flags.append("negative_discrimination")  # імовірна помилка в ключі
            elif discrimination < 0.2:
                flags.append("low_discrimination")
        keyed = correct_options.get(q)
        if keyed and n >= MIN_N_FOR_DISCRIMINATION:
            for oid, cnt in sorted(counts.items()):
                if oid not in keyed and cnt / n < NONFUNCTIONAL_DISTRACTOR_SHARE:
                    flags.append(f"nonfunctional_distractor:{oid}")
        items.append(ItemStats(
            question_id=q, n=n, p_value=p_value, discrimination=discrimination,
            avg_response_ms=_mean([float(t) for t in times]) if times else None,
            option_counts=dict(counts), flags=flags,
        ))

    return TestStats(
        n_participants=len(p_ids), n_items=len(q_ids),
        mean_score=_mean([float(t) for t in totals]) if totals else None,
        kr20=kr20(matrix) if len(p_ids) >= 2 else None,
        items=items,
    )
