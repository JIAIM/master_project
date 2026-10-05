from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Question, Test, User
from app.models.enums import UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(db: DbSession, token: str = Depends(oauth2_scheme)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недійсний токен — увійдіть знову",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise credentials_error from None
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_teacher(user: CurrentUser) -> User:
    if user.role not in (UserRole.TEACHER, UserRole.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступно лише викладачам")
    return user


Teacher = Annotated[User, Depends(require_teacher)]


def _can_manage(owner_id: int, user: User) -> bool:
    return owner_id == user.id or user.role == UserRole.ADMIN


async def get_owned_test(db: AsyncSession, test_id: int, user: User) -> Test:
    test = await db.scalar(
        select(Test).where(Test.id == test_id).options(selectinload(Test.materials))
    )
    if test is None or not _can_manage(test.owner_id, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тест не знайдено")
    return test


async def get_owned_question(db: AsyncSession, question_id: int, user: User) -> tuple[Question, Test]:
    question = await db.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.verifications))
    )
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Питання не знайдено")
    test = await get_owned_test(db, question.test_id, user)
    return question, test


oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_optional_user(db: DbSession, token: str | None = Depends(oauth2_optional)) -> User | None:
    """Студент може увійти анонімно (лише ім'я) або з обліковим записом."""
    if not token:
        return None
    try:
        user = await db.get(User, int(decode_access_token(token)["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    return user if user and user.is_active else None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
