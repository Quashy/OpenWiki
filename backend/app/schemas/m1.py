from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Role = Literal["admin", "editor", "viewer"]
KbType = Literal["document", "wiki"]
KbStatus = Literal["active", "building", "disabled", "embedding_incompatible"]
LlmProvider = Literal["openai", "deepseek"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    created_at: datetime


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_by: str
    created_at: datetime


class WorkspaceUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class WorkspaceMemberOut(BaseModel):
    id: str
    workspace_id: str
    user: UserOut
    role: Role
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserOut
    workspace: WorkspaceOut | None = None
    membership: WorkspaceMemberOut | None = None
    tokens: TokenPair


class MemberCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    role: Role


class MemberRoleUpdateRequest(BaseModel):
    role: Role


class MemberListResponse(BaseModel):
    items: list[WorkspaceMemberOut]


class LlmConfigResponse(BaseModel):
    provider: LlmProvider
    model: str
    base_url: str
    api_key_configured: bool
    api_key_masked: str
    temperature: float
    max_tokens: int
    timeout_seconds: int
    updated_at: datetime


class LlmConfigUpdateRequest(BaseModel):
    provider: LlmProvider
    model: str = Field(min_length=1, max_length=128)
    base_url: HttpUrl
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1)
    timeout_seconds: int = Field(default=60, ge=1)


class ModelTestResult(BaseModel):
    ok: bool
    code: Literal[
        "ok",
        "network_error",
        "auth_error",
        "model_not_found",
        "timeout",
        "invalid_response",
    ]
    message: str
    latency_ms: int


class OllamaConfig(BaseModel):
    base_url: str
    updated_at: datetime


class OllamaConfigUpdateRequest(BaseModel):
    base_url: HttpUrl


class OllamaModelProbeRequest(BaseModel):
    tag: str = Field(min_length=1, max_length=128)


class OllamaModelProbeResult(BaseModel):
    tag: str
    digest: str
    capabilities: list[str]
    embedding_dim: int | None
    usable_for_v1: bool
    unusable_reason: Literal[
        "network_error",
        "model_not_found",
        "not_embedding_model",
        "dimension_incompatible",
        "probe_failed",
    ] | None


class OllamaModelListResponse(BaseModel):
    items: list[OllamaModelProbeResult]


class ChunkingConfig(BaseModel):
    chunk_size: int = Field(default=512, ge=128, le=4096)
    chunk_overlap: int = Field(default=80, ge=0, le=1024)
    strategy: Literal["header_aware"] = "header_aware"


class WikiConfig(BaseModel):
    auto_ingest: bool = False
    llm_timeout_seconds: int = Field(default=60, ge=1)
    llm_max_retries: int = Field(default=3, ge=0, le=5)
    temperature: float = Field(default=0.7, ge=0, le=2)


class SourceKnowledgeBaseCreateRequest(BaseModel):
    type: Literal["document"]
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    embedding_model_tag: str
    chunking_config: ChunkingConfig | None = None


class WikiKnowledgeBaseCreateRequest(BaseModel):
    type: Literal["wiki"]
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    embedding_model_tag: str
    source_knowledge_base_ids: list[str] = Field(min_length=1)
    wiki_config: WikiConfig | None = None


class KnowledgeBaseUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "disabled"] | None = None
    chunking_config: ChunkingConfig | None = None
    wiki_config: WikiConfig | None = None


class KnowledgeBaseSummary(BaseModel):
    id: str
    name: str
    type: KbType
    status: KbStatus


class KnowledgeBaseOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str
    type: KbType
    status: KbStatus
    embedding_provider: Literal["ollama"]
    embedding_model_tag: str
    embedding_model_digest: str
    embedding_dim: Literal[1024]
    chunking_config: ChunkingConfig | None = None
    wiki_config: WikiConfig | None = None
    document_count: int = 0
    page_count: int = 0
    bound_source_kbs: list[KnowledgeBaseSummary] = []
    created_at: datetime
    updated_at: datetime


class KnowledgeBasePage(BaseModel):
    items: list[KnowledgeBaseOut]
    total: int
    page: int
    page_size: int


class WikiSourceBindingRequest(BaseModel):
    source_kb_id: str


class WikiSourceBindingOut(BaseModel):
    id: str
    wiki_kb_id: str
    source_kb_id: str
    created_at: datetime


class AuditLogOut(BaseModel):
    id: str
    workspace_id: str
    user_id: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict[str, Any]
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int
