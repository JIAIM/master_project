from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import MaterialStatus


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    original_filename: str
    mime_type: str
    file_size: int
    status: MaterialStatus
    chunk_count: int
    error_message: str | None
    created_at: datetime


class MaterialBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: MaterialStatus
