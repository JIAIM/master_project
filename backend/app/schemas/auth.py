from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.enums import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt обмежений 72 байтами
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=255)]
    role: UserRole = UserRole.STUDENT


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
