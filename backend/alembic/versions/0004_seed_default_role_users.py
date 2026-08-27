"""seed default role users

Revision ID: 0004_seed_default_role_users
Revises: 0003_seed_default_admin
Create Date: 2026-08-28 01:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_seed_default_role_users"
down_revision: str | None = "0003_seed_default_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADMIN_USER_ID = "00000000-0000-4000-8000-000000000001"
EDITOR_USER_ID = "00000000-0000-4000-8000-000000000005"
VIEWER_USER_ID = "00000000-0000-4000-8000-000000000006"
EDITOR_MEMBER_ID = "00000000-0000-4000-8000-000000000007"
VIEWER_MEMBER_ID = "00000000-0000-4000-8000-000000000008"
AUDIT_ID = "00000000-0000-4000-8000-000000000009"

PASSWORD_HASH = "$2b$12$6N.Ip5jke7h/rWMFstfyC.gtWFPrk2lTnzKH1CMwQC6QlQqggLq5u"


def upgrade() -> None:
    op.execute(
        f"""
DO $$
DECLARE
    admin_id text;
    editor_id text;
    viewer_id text;
    target_workspace_id text;
BEGIN
    INSERT INTO users (id, username, password_hash, created_at)
    VALUES
        ('{ADMIN_USER_ID}', 'admin', '{PASSWORD_HASH}', CURRENT_TIMESTAMP),
        ('{EDITOR_USER_ID}', 'editor', '{PASSWORD_HASH}', CURRENT_TIMESTAMP),
        ('{VIEWER_USER_ID}', 'viewer', '{PASSWORD_HASH}', CURRENT_TIMESTAMP)
    ON CONFLICT (username)
    DO UPDATE SET password_hash = EXCLUDED.password_hash;

    SELECT id INTO admin_id FROM users WHERE username = 'admin';
    SELECT id INTO editor_id FROM users WHERE username = 'editor';
    SELECT id INTO viewer_id FROM users WHERE username = 'viewer';

    SELECT wm.workspace_id INTO target_workspace_id
    FROM workspace_members wm
    JOIN users u ON u.id = wm.user_id
    WHERE u.username = 'admin'
    ORDER BY wm.created_at ASC, wm.id ASC
    LIMIT 1;

    INSERT INTO workspace_members (id, workspace_id, user_id, role, created_at)
    VALUES
        ('{EDITOR_MEMBER_ID}', target_workspace_id, editor_id, 'editor', CURRENT_TIMESTAMP),
        ('{VIEWER_MEMBER_ID}', target_workspace_id, viewer_id, 'viewer', CURRENT_TIMESTAMP)
    ON CONFLICT (workspace_id, user_id)
    DO UPDATE SET role = EXCLUDED.role;

    UPDATE workspace_members
    SET role = 'admin'
    WHERE workspace_id = target_workspace_id AND user_id = admin_id;

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
        '{AUDIT_ID}',
        target_workspace_id,
        admin_id,
        'system.seed_default_role_users',
        'workspace',
        target_workspace_id,
        '{{"users":["admin","editor","viewer"],"password":"password123"}}',
        CURRENT_TIMESTAMP
    )
    ON CONFLICT (id) DO NOTHING;
END $$;
"""
    )


def downgrade() -> None:
    op.execute(
        f"""
DELETE FROM audit_logs WHERE id = '{AUDIT_ID}';
DELETE FROM workspace_members WHERE id IN ('{EDITOR_MEMBER_ID}', '{VIEWER_MEMBER_ID}');
DELETE FROM refresh_tokens WHERE user_id IN ('{EDITOR_USER_ID}', '{VIEWER_USER_ID}');
DELETE FROM users WHERE id IN ('{EDITOR_USER_ID}', '{VIEWER_USER_ID}')
  AND username IN ('editor', 'viewer');
"""
    )
