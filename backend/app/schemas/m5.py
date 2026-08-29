from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kb_id: str
    title: str | None = Field(default=None, max_length=256)


class ChatSessionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=256)


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    kb_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatSessionPage(BaseModel):
    items: list[ChatSessionOut]
    total: int
    page: int
    page_size: int


class Citation(BaseModel):
    id: int = Field(ge=1)
    source_type: Literal["document", "wiki_page"]
    kb_id: str
    document_id: str | None = None
    wiki_page_id: str | None = None
    chunk_id: str | None = None
    filename: str | None = None
    title: str | None = None
    header_path: list[str] = []
    snippet: str


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation]
    trace_id: str | None = None
    token_usage: dict[str, Any] = {}
    created_at: datetime


class ChatMessagePage(BaseModel):
    items: list[ChatMessageOut]
    total: int
    page: int
    page_size: int
