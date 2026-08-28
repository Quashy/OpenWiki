"""add document uploader username

Revision ID: 0006_doc_uploader_username
Revises: 0005_m2_document_ingestion
Create Date: 2026-08-28 05:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_doc_uploader_username"
down_revision: str | None = "0005_m2_document_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("created_by_username", sa.String(64), nullable=True))
    op.execute(
        """
        UPDATE documents
        SET created_by_username = users.username
        FROM users
        WHERE documents.created_by = users.id
        """
    )
    op.execute("UPDATE documents SET created_by_username = created_by WHERE created_by_username IS NULL")
    op.alter_column("documents", "created_by_username", nullable=False)


def downgrade() -> None:
    op.drop_column("documents", "created_by_username")
