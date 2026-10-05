"""Пошук розділу матеріалу за номером («Лекція 6», «Тема 3», «розділ 2»)."""
from __future__ import annotations

import re
from typing import Protocol, Sequence, TypeVar

_WORDS = r"(?:лекці\w*|тем[аиуі]?|розділ\w*|глав[аиі]?|модул\w*|lecture|chapter|section|topic)"
_HEADING_RE = re.compile(rf"\b{_WORDS}\s*№?\s*(\d+)\b", re.IGNORECASE)
_TOPIC_RE = re.compile(
    rf"\b{_WORDS}\s*№?\s*(\d+)\b|\b(\d+)(?:-?(?:а|я|ий|ої|ій))?\s+{_WORDS}", re.IGNORECASE
)


class _ChunkLike(Protocol):
    text: str
    material_id: int
    chunk_index: int


C = TypeVar("C", bound=_ChunkLike)


def topic_section(topic: str) -> tuple[int, str] | None:
    """Номер розділу з теми та решта тексту теми без посилання на розділ."""
    m = _TOPIC_RE.search(topic)
    if not m:
        return None
    rest = (topic[:m.start()] + " " + topic[m.end():]).strip(" .,:;-–—«»\"'")
    if not re.search(r"\w{3,}", rest):
        rest = ""
    return int(m.group(1) or m.group(2)), rest


def section_chunks(chunks: Sequence[C], number: int) -> list[C]:
    """Фрагменти розділу: від заголовка з номером до заголовка іншого розділу.

    Зміст і тематичний план теж згадують розділ, але одразу за ним ідуть інші
    номери, тому з кількох кандидатів обирається найдовший.
    """
    result: list[C] = []
    for material_id in dict.fromkeys(c.material_id for c in chunks):
        ordered = sorted((c for c in chunks if c.material_id == material_id), key=lambda c: c.chunk_index)
        refs = [[int(m.group(1)) for m in _HEADING_RE.finditer(c.text)] for c in ordered]
        best: list[C] = []
        for start, found in enumerate(refs):
            if not found or found[-1] != number:
                continue
            end = start + 1
            while end < len(ordered) and all(n == number for n in refs[end]):
                end += 1
            if end - start > len(best):
                best = ordered[start:end]
        result.extend(best)
    return result
