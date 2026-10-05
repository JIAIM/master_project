from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, str_enum
from app.models.enums import MaterialStatus

if TYPE_CHECKING:
    from app.models.user import User


class Material(TimestampMixin, Base):
    """Завантажений навчальний файл (PDF/DOCX); фрагменти та ембедінги зберігаються в Chroma."""

    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    file_size: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256, захист від дублікатів

    status: Mapped[MaterialStatus] = mapped_column(
        str_enum(MaterialStatus), default=MaterialStatus.UPLOADED
    )
    chroma_collection: Mapped[str | None] = mapped_column(String(128))
    chunk_count: Mapped[int] = mapped_column(default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[User] = relationship(back_populates="materials")
