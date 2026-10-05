"""Обгортка над Chroma: одна колекція, фільтрація за material_id.

Клієнт Chroma синхронний, тому важкі операції виконуються в asyncio.to_thread.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from langchain_core.documents import Document

from app.core.config import get_settings
from app.services.rag.embeddings import get_embeddings

ADD_BATCH_SIZE = 128


@dataclass(slots=True)
class Chunk:
    id: str
    text: str
    material_id: int
    chunk_index: int
    page: int | None = None
    section: str | None = None
    score: float | None = None  # косинусна подібність під час пошуку

    @classmethod
    def from_chroma(cls, id_: str, text: str, meta: dict[str, Any], distance: float | None = None):
        page = meta.get("page")
        return cls(
            id=id_,
            text=text,
            material_id=int(meta["material_id"]),
            chunk_index=int(meta["chunk_index"]),
            page=int(page) if page not in (None, -1) else None,
            section=meta.get("section") or None,
            score=(1.0 - distance) if distance is not None else None,
        )


def make_chunk_id(material_id: int, index: int) -> str:
    return f"m{material_id}-c{index}"


class MaterialVectorStore:
    def __init__(self) -> None:
        import chromadb

        settings = get_settings()
        self._client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
        self._collection_name = settings.CHROMA_COLLECTION
        self._collection = None
        self._embeddings = get_embeddings()

    @property
    def collection(self):
        if self._collection is None:
            # вектори передаємо самі, вбудована модель Chroma не потрібна
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None,
            )
        return self._collection

    @staticmethod
    def _where(material_ids: list[int]) -> dict[str, Any]:
        return {"material_id": {"$in": [int(m) for m in material_ids]}}

    # --- Запис ---
    async def add_chunks(self, material_id: int, owner_id: int, chunks: list[Document]) -> list[str]:
        texts = [c.page_content for c in chunks]
        ids = [make_chunk_id(material_id, i) for i in range(len(chunks))]
        metadatas = [
            {
                "material_id": material_id,
                "owner_id": owner_id,
                "chunk_index": i,
                "page": int(c.metadata.get("page") or -1),
                "section": str(c.metadata.get("section") or ""),
            }
            for i, c in enumerate(chunks)
        ]
        vectors = await asyncio.to_thread(self._embeddings.embed_documents, texts)

        for start in range(0, len(ids), ADD_BATCH_SIZE):
            end = start + ADD_BATCH_SIZE
            await asyncio.to_thread(
                self.collection.upsert,
                ids=ids[start:end],
                documents=texts[start:end],
                metadatas=metadatas[start:end],
                embeddings=vectors[start:end],
            )
        return ids

    async def delete_material(self, material_id: int) -> None:
        await asyncio.to_thread(self.collection.delete, where={"material_id": int(material_id)})

    # --- Читання ---
    async def get_material_chunks(self, material_ids: list[int]) -> list[Chunk]:
        res = await asyncio.to_thread(
            self.collection.get,
            where=self._where(material_ids),
            include=["documents", "metadatas"],
        )
        chunks = [
            Chunk.from_chroma(i, d, m)
            for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
        ]
        chunks.sort(key=lambda c: (c.material_id, c.chunk_index))
        return chunks

    async def get_by_ids(self, ids: list[str]) -> list[Chunk]:
        if not ids:
            return []
        res = await asyncio.to_thread(
            self.collection.get, ids=list(ids), include=["documents", "metadatas"]
        )
        chunks = [
            Chunk.from_chroma(i, d, m)
            for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
        ]
        chunks.sort(key=lambda c: (c.material_id, c.chunk_index))
        return chunks

    async def search(self, query: str, material_ids: list[int], k: int = 8) -> list[Chunk]:
        vector = await asyncio.to_thread(self._embeddings.embed_query, query)
        res = await asyncio.to_thread(
            self.collection.query,
            query_embeddings=[vector],
            n_results=k,
            where=self._where(material_ids),
            include=["documents", "metadatas", "distances"],
        )
        return [
            Chunk.from_chroma(i, d, m, dist)
            for i, d, m, dist in zip(
                res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
            )
        ]


@lru_cache
def get_vector_store() -> MaterialVectorStore:
    return MaterialVectorStore()
