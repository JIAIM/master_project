"""Фільтр фрагментів RAG: відсіює списки літератури й посилань, щоб на них
не генерувалися питання.
"""
from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://\S+")
_DOT_LEADER_RE = re.compile(r"[.…]{4,}")
_REFERENCE_HEADING_RE = re.compile(
    r"(рекомендован\w*\s+літератур\w*|рекомендуем\w*\s+литератур\w*|"
    r"список\s+(використан\w*|использованн\w*)?\s*джерел\w*|список\s+использованных\s+источников|"
    r"бібліографі\w*|библиографи\w*|джерела\s+та\s+література|список\s+літератури|"
    r"список\s+литературы|references|bibliography|further\s+reading)",
    re.IGNORECASE,
)
MAX_URL_DENSITY = 0.15   
MIN_URL_COUNT = 3        
MIN_DOT_LEADERS = 3


def is_reference_like(text: str) -> bool:
    """True, якщо фрагмент схожий на список літератури, а не на навчальний текст."""
    if _REFERENCE_HEADING_RE.search(text[:200]):
        return True
    if len(_DOT_LEADER_RE.findall(text)) >= MIN_DOT_LEADERS:
        return True
    urls = _URL_RE.findall(text)
    if not urls:
        return False
    if len(urls) >= MIN_URL_COUNT:
        return True
    url_chars = sum(len(u) for u in urls)
    return url_chars / max(len(text), 1) > MAX_URL_DENSITY
