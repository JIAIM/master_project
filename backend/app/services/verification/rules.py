"""Рівень 1 перевірки: детерміновані правила без LLM (структура питання, типові помилки,
дослівність цитати-обґрунтування).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol, Sequence


class OptionLike(Protocol):
    text: str
    is_correct: bool


class QuestionLike(Protocol):
    question: str
    options: Sequence[OptionLike]
    evidence_quote: str


BANNED_OPTION_PATTERNS = [
    r"\ball of the above\b", r"\bnone of the above\b", r"\bboth [ab] and [ab]\b",
    r"всі (перелічені|вищезазначені|варіанти)", r"жоден (з|із) (перелічених|варіантів)",
    r"усі (перелічені|вищезазначені|варіанти)",
    r"все (перечисленн|вышеперечисленн|варианты)", r"ни один (из )?(вариант|перечисленн)",
    r"ничего из (перечисленного|вышеперечисленного)",
]

TEXT_REFERENCE_PATTERNS = [
    r"\baccording to the (text|passage|context)\b", r"\bin the (text|passage|context)\b",
    r"\bу тексті\b", r"\bв тексті\b", r"\bзгідно з текстом\b", r"\bу контексті\b",
    r"\bв тексте\b", r"\bсогласно тексту\b", r"\bв контексте\b",
]

LENGTH_BIAS_RATIO = 1.8
LENGTH_BIAS_MIN_DIFF = 25
QUOTE_SHINGLE_THRESHOLD = 0.6


@dataclass(frozen=True)
class RuleIssue:
    code: str
    message: str
    blocking: bool = True


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _shingles(words: list[str], n: int = 3) -> set[tuple[str, ...]]:
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def quote_grounding(quote: str, context: str) -> float:
    """Частка 3-грам цитати, знайдених у контексті (1.0 — цитата дослівна)."""
    q, c = normalize(quote), normalize(context)
    if not q:
        return 0.0
    if q in c:
        return 1.0
    q_sh = _shingles(q.split())
    if not q_sh:
        return 0.0
    c_sh = _shingles(c.split())
    return len(q_sh & c_sh) / len(q_sh)


def check_question(
    q: QuestionLike,
    *,
    question_type: str,
    expected_options: int,
    context: str,
) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    options = list(q.options)
    n_correct = sum(1 for o in options if o.is_correct)

    # --- Структура ---
    if len(normalize(q.question)) < 10:
        issues.append(RuleIssue("stem_too_short", "Текст питання занадто короткий"))

    if len(options) != expected_options:
        issues.append(RuleIssue(
            "option_count", f"Очікувалося варіантів відповіді: {expected_options}, отримано: {len(options)}"
        ))

    if question_type in ("single_choice", "true_false") and n_correct != 1:
        issues.append(RuleIssue("correct_count", f"Має бути рівно 1 правильна відповідь, позначено: {n_correct}"))
    elif question_type == "multiple_choice" and not (2 <= n_correct < len(options)):
        issues.append(RuleIssue(
            "correct_count", f"Для множинного вибору потрібно 2–3 правильні відповіді, позначено: {n_correct}"
        ))

    normalized = [normalize(o.text) for o in options]
    if any(not t for t in normalized):
        issues.append(RuleIssue("empty_option", "Є порожній варіант відповіді"))
    if len(set(normalized)) != len(normalized):
        issues.append(RuleIssue("duplicate_options", "Є варіанти відповіді, що повторюються"))

    # --- Типові помилки складання тестів ---
    for text in (o.text for o in options):
        if any(re.search(p, text, re.IGNORECASE) for p in BANNED_OPTION_PATTERNS):
            issues.append(RuleIssue(
                "banned_option", f"Неприпустимий варіант «{text}» (на кшталт «усе перелічене»)"
            ))
            break

    if any(re.search(p, q.question, re.IGNORECASE) for p in TEXT_REFERENCE_PATTERNS):
        issues.append(RuleIssue(
            "refers_to_text", "Питання посилається на «текст/контекст» — воно має бути самодостатнім"
        ))

    if question_type != "true_false" and n_correct >= 1 and len(options) > n_correct:
        correct_len = [len(o.text) for o in options if o.is_correct]
        wrong_len = [len(o.text) for o in options if not o.is_correct]
        avg_c = sum(correct_len) / len(correct_len)
        avg_w = sum(wrong_len) / len(wrong_len)
        if avg_c > LENGTH_BIAS_RATIO * avg_w and avg_c - avg_w > LENGTH_BIAS_MIN_DIFF:
            issues.append(RuleIssue(
                "length_bias",
                "Правильна відповідь помітно довша за хибні варіанти — це підказка для студента",
            ))

    stem_norm = normalize(q.question)
    for o in options:
        opt = normalize(o.text)
        if o.is_correct and len(opt.split()) >= 4 and opt in stem_norm:
            issues.append(RuleIssue("answer_in_stem", "Правильна відповідь дослівно міститься в питанні"))
            break

    # --- Підтвердження матеріалом (захист від галюцинацій) ---
    score = quote_grounding(q.evidence_quote, context)
    if score < QUOTE_SHINGLE_THRESHOLD:
        issues.append(RuleIssue(
            "quote_not_found",
            f"Цитату-обґрунтування не знайдено у вихідному матеріалі (збіг {score:.0%}) — "
            "можлива галюцинація ШІ",
        ))

    return issues


def blocking(issues: list[RuleIssue]) -> list[RuleIssue]:
    return [i for i in issues if i.blocking]
