import asyncio
import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import DbSession, Teacher
from app.core.config import get_settings
from app.models import Material
from app.models.enums import MaterialStatus, UserRole
from app.schemas.material import MaterialOut
from app.services.rag.ingest import ingest_material
from app.services.rag.loaders import SUPPORTED_EXTENSIONS
from app.services.rag.vectorstore import get_vector_store

router = APIRouter(prefix="/materials", tags=["materials"])
logger = logging.getLogger(__name__)

MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


async def _get_owned_material(db, material_id: int, user) -> Material:
    material = await db.get(Material, material_id)
    if material is None or (material.owner_id != user.id and user.role != UserRole.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Матеріал не знайдено")
    return material


@router.post("", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
async def upload_material(
    background: BackgroundTasks,
    db: DbSession,
    user: Teacher,
    file: UploadFile = File(...),
    title: str | None = Form(None),
) -> Material:
    settings = get_settings()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Підтримуються лише файли PDF і DOCX")

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Файл більший за {settings.MAX_UPLOAD_MB} МБ")
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Файл порожній")
    if not content.startswith(b"%PDF" if ext == ".pdf" else b"PK"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Файл пошкоджений або не є справжнім {ext[1:].upper()} — збережіть його ще раз і завантажте знову",
        )

    digest = hashlib.sha256(content).hexdigest()
    duplicate = await db.scalar(
        select(Material).where(Material.owner_id == user.id, Material.content_hash == digest)
    )
    if duplicate is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "Цей файл уже завантажено", "material_id": duplicate.id},
        )

    target_dir = Path(settings.UPLOAD_DIR) / str(user.id)
    target = target_dir / f"{uuid.uuid4().hex}{ext}"

    def _write() -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    await asyncio.to_thread(_write)

    material = Material(
        owner_id=user.id,
        title=((title or "").strip() or Path(file.filename or "material").stem)[:255],
        original_filename=(file.filename or "material")[:255],
        file_path=str(target),
        mime_type=MIME_BY_EXT[ext],
        file_size=len(content),
        content_hash=digest,
        status=MaterialStatus.UPLOADED,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    background.add_task(ingest_material, material.id)
    return material


@router.get("", response_model=list[MaterialOut])
async def list_materials(db: DbSession, user: Teacher) -> list[Material]:
    rows = await db.scalars(
        select(Material).where(Material.owner_id == user.id).order_by(Material.created_at.desc())
    )
    return list(rows)


@router.get("/{material_id}", response_model=MaterialOut)
async def get_material(material_id: int, db: DbSession, user: Teacher) -> Material:
    return await _get_owned_material(db, material_id, user)


@router.post("/{material_id}/reindex", response_model=MaterialOut)
async def reindex_material(
    material_id: int, background: BackgroundTasks, db: DbSession, user: Teacher
) -> Material:
    material = await _get_owned_material(db, material_id, user)
    if material.status == MaterialStatus.PROCESSING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Матеріал уже обробляється")
    background.add_task(ingest_material, material.id)
    return material


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(material_id: int, db: DbSession, user: Teacher) -> None:
    material = await _get_owned_material(db, material_id, user)
    try:
        await get_vector_store().delete_material(material.id)
    except Exception:  # noqa: BLE001 — недоступність Chroma не блокує видалення
        logger.exception("Не вдалося видалити вектори матеріалу %s", material.id)
    await asyncio.to_thread(Path(material.file_path).unlink, missing_ok=True)
    await db.delete(material)
    await db.commit()
