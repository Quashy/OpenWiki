"""wiki page source citations

Revision ID: 0008_wiki_page_source_citations
Revises: 0007_m3_wiki_pages_graph
Create Date: 2026-08-29 01:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeEngine

from alembic import op

revision: str = "0008_wiki_page_source_citations"
down_revision: str | None = "0007_m3_wiki_pages_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def json_type() -> TypeEngine[object]:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "wiki_pages",
        sa.Column("source_citations", json_type(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("wiki_pages", "source_citations", server_default=None)


def downgrade() -> None:
    op.drop_column("wiki_pages", "source_citations")
