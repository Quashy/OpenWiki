from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.m1 import ChunkingConfig

DocumentStatus = Literal["pending", "running", "completed", "failed"]
TaskStatus = Literal["pending", "running", "completed", "failed"]
TaskType = Literal["document_process", "wiki_ingest", "wiki_rebuild"]
TaskStage = Literal[
    "pending",
    "chunking",
    "embedding",
    "indexing",
    "extracting",
    "citing",
    "taxonomy",
    "summarizing",
    "reducing",
    "postprocessing",
    "completed",
    "failed",
]
ChunkType = Literal["text", "wiki_page"]


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kb_id: str
    name: str


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str | None = None
    kb_id: str
    content: str
    header_path: list[str]
    seq: int
    start_pos: int
    end_pos: int
    chunk_type: ChunkType
    source_page_id: str | None = None
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kb_id: str
    filename: str
    file_hash: str
    file_size: int
    status: DocumentStatus
    error_message: str | None = None
    chunk_count: int
    tags: list[TagOut] = []
    created_by: str
    created_by_username: str
    created_at: datetime
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class DocumentDetail(DocumentOut):
    content: str
    chunks: list[ChunkOut]


class DocumentUploadResponse(BaseModel):
    documents: list[DocumentOut]
    task_ids: list[str]


class ChunkPreviewRequest(BaseModel):
    content: str = Field(min_length=1)
    content_type: Literal["markdown", "text"]
    chunking_config: ChunkingConfig | None = None

    @model_validator(mode="after")
    def validate_overlap(self) -> "ChunkPreviewRequest":
        config = self.chunking_config
        if config is not None and config.chunk_overlap >= config.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class ChunkPreviewItem(BaseModel):
    content: str
    header_path: list[str]
    seq: int
    start_pos: int
    end_pos: int
    char_count: int


class ChunkPreviewResponse(BaseModel):
    items: list[ChunkPreviewItem]


class TaskAcceptedResponse(BaseModel):
    task_id: str


class TaskError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kb_id: str
    task_type: TaskType
    status: TaskStatus
    stage: TaskStage
    progress: int
    payload: dict[str, Any]
    run_after: datetime | None = None
    dedup_key: str | None = None
    error: TaskError | None = None
    created_at: datetime
    updated_at: datetime
