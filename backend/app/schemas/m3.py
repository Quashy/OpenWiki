from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WikiPageType = Literal["index", "source", "entity", "concept", "overview", "analysis"]
EditorType = Literal["agent", "manual"]


class WikiIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[str] | None = None


class WikiRebuildRequest(BaseModel):
    confirm: Literal["REBUILD"]


class WikiPageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kb_id: str
    slug: str
    title: str
    page_type: WikiPageType
    summary: str
    category_path: list[str]
    aliases: list[str]
    source_refs: list[str]
    updated_at: datetime


class WikiPageOut(WikiPageSummary):
    content: str
    current_revision_id: str
    manual_edit_warning: bool = False
    created_at: datetime


class WikiPageSourceChunk(BaseModel):
    id: str
    seq: int
    header_path: list[str]
    content: str
    start_pos: int
    end_pos: int


class WikiPageSource(BaseModel):
    document_id: str
    filename: str
    status: str
    precise: bool
    chunks: list[WikiPageSourceChunk]


class WikiPageSourceResponse(BaseModel):
    items: list[WikiPageSource]


class WikiPageTreeNode(BaseModel):
    name: str
    path: list[str]
    pages: list[WikiPageSummary]
    children: list["WikiPageTreeNode"]


class WikiPageListResponse(BaseModel):
    items: list[WikiPageSummary]
    tree: list[WikiPageTreeNode]


class WikiPageUpdateRequest(BaseModel):
    content: str = Field(min_length=1)
    change_summary: str | None = Field(default=None, max_length=512)


class WikiPageRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    page_id: str
    content: str
    editor_type: EditorType
    editor_id: str | None = None
    change_summary: str
    created_at: datetime


class WikiRevisionPage(BaseModel):
    items: list[WikiPageRevisionOut]
    total: int
    page: int
    page_size: int


class WikiGraphNode(BaseModel):
    id: str
    name: str
    slug: str
    entity_type: str
    wiki_page_id: str | None = None


class WikiGraphEdge(BaseModel):
    id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    source_chunk_id: str | None = None


class WikiGraph(BaseModel):
    nodes: list[WikiGraphNode]
    edges: list[WikiGraphEdge]
