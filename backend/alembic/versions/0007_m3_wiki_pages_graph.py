"""m3 wiki pages and graph

Revision ID: 0007_m3_wiki_pages_graph
Revises: 0006_doc_uploader_username
Create Date: 2026-08-28 08:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeEngine

from alembic import op

revision: str = "0007_m3_wiki_pages_graph"
down_revision: str | None = "0006_doc_uploader_username"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def json_type() -> TypeEngine[object]:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kb_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("slug", sa.String(256), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("page_type", sa.String(16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category_path", json_type(), nullable=False),
        sa.Column("aliases", json_type(), nullable=False),
        sa.Column("source_refs", json_type(), nullable=False),
        sa.Column("current_revision_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kb_id", "slug", name="uq_wiki_pages_kb_slug"),
    )
    op.create_index("ix_wiki_pages_kb_id", "wiki_pages", ["kb_id"])

    op.create_table(
        "wiki_page_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "page_id",
            sa.String(36),
            sa.ForeignKey("wiki_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("editor_type", sa.String(16), nullable=False),
        sa.Column("editor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_wiki_page_revisions_page_id", "wiki_page_revisions", ["page_id"])

    op.create_table(
        "entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kb_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("slug", sa.String(256), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("aliases", json_type(), nullable=False),
        sa.Column("wiki_page_id", sa.String(36), sa.ForeignKey("wiki_pages.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kb_id", "slug", name="uq_entities_kb_slug"),
    )
    op.create_index("ix_entities_kb_id", "entities", ["kb_id"])

    op.create_table(
        "relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kb_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("source_entity_id", sa.String(36), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("target_entity_id", sa.String(36), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column("source_chunk_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "relation_type",
            name="uq_relations_source_target_type",
        ),
    )
    op.create_index("ix_relations_kb_id", "relations", ["kb_id"])


def downgrade() -> None:
    op.drop_index("ix_relations_kb_id", table_name="relations")
    op.drop_table("relations")
    op.drop_index("ix_entities_kb_id", table_name="entities")
    op.drop_table("entities")
    op.drop_index("ix_wiki_page_revisions_page_id", table_name="wiki_page_revisions")
    op.drop_table("wiki_page_revisions")
    op.drop_index("ix_wiki_pages_kb_id", table_name="wiki_pages")
    op.drop_table("wiki_pages")
