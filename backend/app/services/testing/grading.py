"""Оцінювання спроби: бал за питання — його вага при правильній відповіді, підсумок — сума.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def is_answer_correct(selected: Iterable[int], correct: Iterable[int]) -> bool:
    chosen = set(selected)
    return bool(chosen) and chosen == set(correct)


@dataclass(frozen=True)
class GradedItem:
    question_id: int
    points: float
    selected: tuple[int, ...]
    correct: tuple[int, ...]

    @property
    def answered(self) -> bool:
        return bool(self.selected)

    @property
    def is_correct(self) -> bool:
        return is_answer_correct(self.selected, self.correct)

    @property
    def score(self) -> float:
        return self.points if self.is_correct else 0.0


@dataclass(frozen=True)
class Grade:
    score: float
    max_score: float
    correct_count: int
    answered_count: int
    total: int


def grade(items: list[GradedItem]) -> Grade:
    return Grade(
        score=sum(i.score for i in items),
        max_score=sum(i.points for i in items),
        correct_count=sum(1 for i in items if i.is_correct),
        answered_count=sum(1 for i in items if i.answered),
        total=len(items),
    )
