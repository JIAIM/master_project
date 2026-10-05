"""Добір фрагментів матеріалу для N питань: за темою або рівномірно по всьому матеріалу.
"""
from __future__ import annotations

import random

from app.services.generation.content_filters import is_reference_like
from app.services.rag.vectorstore import Chunk, MaterialVectorStore

MIN_SEED_CHARS = 300


class NoIndexedContentError(ValueError):
    pass


def evenly_spaced(items: list, n: int) -> list:
    if n <= 0 or not items:
        return []
    if n >= len(items):
        return list(items)
    step = len(items) / n
    return [items[int(i * step + step / 2)] for i in range(n)]


async def build_contexts(
    store: MaterialVectorStore,
    material_ids: list[int],
    n: int,
    topic: str | None = None,
) -> list[list[Chunk]]:
    all_chunks = await store.get_material_chunks(material_ids)
    if not all_chunks:
        raise NoIndexedContentError("В обраних матеріалах немає обробленого тексту")

    by_position = {(c.material_id, c.chunk_index): c for c in all_chunks}

    if topic:
        k = min(len(all_chunks), max(n * 2, 8))
        found = await store.search(topic, material_ids, k=k)
        seeds = [c for c in found if not is_reference_like(c.text)] or found
    else:
        candidates = [c for c in all_chunks if len(c.text) >= MIN_SEED_CHARS]
        usable = [c for c in candidates if not is_reference_like(c.text)] or candidates or all_chunks
        seeds = evenly_spaced(usable, n)

    contexts: list[list[Chunk]] = []
    for i in range(n):
        seed = seeds[i % len(seeds)]
        nxt = by_position.get((seed.material_id, seed.chunk_index + 1))
        if nxt is not None and is_reference_like(nxt.text):
            nxt = None
        contexts.append([seed, nxt] if nxt else [seed])
    return contexts


def plan_difficulties(n: int, difficulty: str) -> list[str]:
    """'mixed' → 30% легких / 50% середніх / 20% складних, перемішано."""
    if difficulty != "mixed":
        return [difficulty] * n
    easy = round(n * 0.3)
    hard = round(n * 0.2)
    medium = n - easy - hard
    plan = ["easy"] * easy + ["medium"] * medium + ["hard"] * hard
    random.Random(n).shuffle(plan)
    return plan
