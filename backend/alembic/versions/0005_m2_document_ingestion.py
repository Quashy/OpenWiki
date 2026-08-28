"""m2 document ingestion

Revision ID: 0005_m2_document_ingestion
Revises: 0004_seed_default_role_users
Create Date: 2026-08-28 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeEngine

from alembic import op

revision: str = "0005_m2_document_ingestion"
down_revision: str | None = "0004_seed_default_role_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def json_type() -> TypeEngine[object]:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kb_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.UniqueConstraint("kb_id", "name", name="uq_tags_kb_name"),
    )
    op.create_index("ix_tags_kb_id", "tags", ["kb_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kb_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kb_id", "file_hash", name="uq_documents_kb_file_hash"),
    )
    op.create_index("ix_documents_kb_id", "documents", ["kb_id"])

    op.create_table(
        "document_tags",
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.String(36),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("kb_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("header_path", json_type(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("start_pos", sa.Integer(), nullable=False),
        sa.Column("end_pos", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("chunk_type", sa.String(16), nullable=False),
        sa.Column("source_page_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_kb_id", "chunks", ["kb_id"])
    op.create_index("ix_chunks_kb_document_seq", "chunks", ["kb_id", "document_id", "seq"])

    op.create_table(
        "task_pending_ops",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kb_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("payload", json_type(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedup_key", sa.String(256), nullable=True),
        sa.Column("error", json_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_pending_ops_kb_id", "task_pending_ops", ["kb_id"])

    if op.get_context().dialect.name == "postgresql":
        op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector")
        op.execute("CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)")
        op.execute("CREATE INDEX ix_chunks_search_text_bigm ON chunks USING gin (search_text gin_bigm_ops)")


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_chunks_search_text_bigm")
        op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_index("ix_task_pending_ops_kb_id", table_name="task_pending_ops")
    op.drop_table("task_pending_ops")
    op.drop_index("ix_chunks_kb_document_seq", table_name="chunks")
    op.drop_index("ix_chunks_kb_id", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("document_tags")
    op.drop_index("ix_documents_kb_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_tags_kb_id", table_name="tags")
    op.drop_table("tags")
