"""Фонова індексація матеріалу: розбір → фрагменти → ембедінги → Chroma."""
from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models import Material
from app.models.enums import MaterialStatus
from app.services.rag.chunking import split_documents
from app.services.rag.loaders import load_document
from app.services.rag.vectorstore import get_vector_store

logger = logging.getLogger(__name__)


async def ingest_material(material_id: int) -> None:
    async with AsyncSessionLocal() as db:
        material = await db.get(Material, material_id)
        if material is None:
            logger.warning("Матеріал %s не знайдено для індексації", material_id)
            return

        material.status = MaterialStatus.PROCESSING
        material.error_message = None
        await db.commit()

        try:
            docs = await asyncio.to_thread(load_document, material.file_path)
            chunks = split_documents(docs)
            if not chunks:
                raise ValueError("Після розбиття не лишилося змістовних фрагментів тексту")

            store = get_vector_store()
            await store.delete_material(material.id)  # повторна індексація замінює старі фрагменти
            await store.add_chunks(material.id, material.owner_id, chunks)

            material.chunk_count = len(chunks)
            material.chroma_collection = get_settings().CHROMA_COLLECTION
            material.status = MaterialStatus.INDEXED
            logger.info("Матеріал %s проіндексовано, фрагментів: %s", material.id, len(chunks))
        except Exception as exc:  # noqa: BLE001 — будь-яка помилка має потрапити в статус
            logger.exception("Не вдалося проіндексувати матеріал %s", material_id)
            material.status = MaterialStatus.FAILED
            material.error_message = str(exc)[:2000]

        await db.commit()
