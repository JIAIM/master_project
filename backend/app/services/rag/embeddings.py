"""Локальні ембедінги через sentence-transformers.

Моделі E5 потребують префіксів «passage: » / «query: » — клас додає їх сам.
"""
from __future__ import annotations

import threading
from functools import lru_cache

from langchain_core.embeddings import Embeddings

from app.core.config import get_settings


class SentenceTransformerEmbeddings(Embeddings):
    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._is_e5 = "e5" in model_name.lower()
        self._model = None
        self._lock = threading.Lock()

    @property
    def model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefix = "passage: " if self._is_e5 else ""
        return self._encode([prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        prefix = "query: " if self._is_e5 else ""
        return self._encode([prefix + text])[0]


@lru_cache
def get_embeddings() -> SentenceTransformerEmbeddings:
    return SentenceTransformerEmbeddings(get_settings().EMBEDDING_MODEL)
