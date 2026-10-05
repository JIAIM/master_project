from __future__ import annotations

from app.services.generation.schemas import LLMQuestion
from app.services.rag.vectorstore import Chunk


def format_context(chunks: list[Chunk]) -> str:
    parts = []
    for c in chunks:
        loc = f"стр. {c.page}" if c.page else (c.section or "")
        header = f"[фрагмент {c.id}{', ' + loc if loc else ''}]"
        parts.append(f"{header}\n{c.text}")
    return "\n\n".join(parts)


def format_question_block(q: LLMQuestion) -> str:
    lines = [f"QUESTION: {q.question}", "OPTIONS:"]
    lines += [f"{i}. {o.text}" for i, o in enumerate(q.options, start=1)]
    return "\n".join(lines)


def keyed_numbers(q: LLMQuestion) -> list[int]:
    return [i for i, o in enumerate(q.options, start=1) if o.is_correct]
