"""enable postgres extensions

Revision ID: 0001_enable_postgres_extensions
Revises:
Create Date: 2026-08-27 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_enable_postgres_extensions"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_bigm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_bigm")
    op.execute("DROP EXTENSION IF EXISTS vector")

