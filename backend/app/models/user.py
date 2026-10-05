from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, str_enum
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.material import Material
    from app.models.test import Test


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), default=UserRole.STUDENT)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    materials: Mapped[list[Material]] = relationship(back_populates="owner")
    tests: Mapped[list[Test]] = relationship(back_populates="owner")
