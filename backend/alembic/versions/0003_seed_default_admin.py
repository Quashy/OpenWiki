"""seed default admin

Revision ID: 0003_seed_default_admin
Revises: 0002_m1_core_tables
Create Date: 2026-08-27 02:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_seed_default_admin"
down_revision: str | None = "0002_m1_core_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADMIN_USER_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_WORKSPACE_ID = "00000000-0000-4000-8000-000000000002"
DEFAULT_MEMBER_ID = "00000000-0000-4000-8000-000000000003"
DEFAULT_AUDIT_ID = "00000000-0000-4000-8000-000000000004"


def upgrade() -> None:
    op.execute(
        f"""
DO $$
DECLARE
    admin_id text;
    target_workspace_id text;
BEGIN
    INSERT INTO users (id, username, password_hash, created_at)
    VALUES (
        '{ADMIN_USER_ID}',
        'admin',
        '$2b$12$6N.Ip5jke7h/rWMFstfyC.gtWFPrk2lTnzKH1CMwQC6QlQqggLq5u',
        CURRENT_TIMESTAMP
    )
    ON CONFLICT (username)
    DO UPDATE SET password_hash = EXCLUDED.password_hash;

    SELECT id INTO admin_id FROM users WHERE username = 'admin';
    SELECT id INTO target_workspace_id FROM workspaces ORDER BY created_at ASC, id ASC LIMIT 1;

    IF target_workspace_id IS NULL THEN
        target_workspace_id := '{DEFAULT_WORKSPACE_ID}';
        INSERT INTO workspaces (id, name, created_by, created_at)
        VALUES (target_workspace_id, '默认团队', admin_id, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO NOTHING;
    END IF;

    INSERT INTO workspace_members (id, workspace_id, user_id, role, created_at)
    VALUES ('{DEFAULT_MEMBER_ID}', target_workspace_id, admin_id, 'admin', CURRENT_TIMESTAMP)
    ON CONFLICT (workspace_id, user_id)
    DO UPDATE SET role = 'admin';

    INSERT INTO audit_logs (
        id,
        workspace_id,
        user_id,
        action,
        resource_type,
        resource_id,
        details,
        created_at
    )
    VALUES (
        '{DEFAULT_AUDIT_ID}',
        target_workspace_id,
        admin_id,
        'system.seed_default_admin',
        'workspace',
        target_workspace_id,
        '{{"username":"admin"}}',
        CURRENT_TIMESTAMP
    )
    ON CONFLICT (id) DO NOTHING;
END $$;
"""
    )


def downgrade() -> None:
    op.execute(
        f"""
DELETE FROM audit_logs WHERE id = '{DEFAULT_AUDIT_ID}';
DELETE FROM workspace_members WHERE id = '{DEFAULT_MEMBER_ID}';
DELETE FROM workspaces WHERE id = '{DEFAULT_WORKSPACE_ID}';
DELETE FROM refresh_tokens WHERE user_id = '{ADMIN_USER_ID}';
DELETE FROM users WHERE id = '{ADMIN_USER_ID}' AND username = 'admin';
"""
    )
