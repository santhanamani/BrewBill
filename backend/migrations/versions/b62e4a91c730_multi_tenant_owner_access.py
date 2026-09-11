"""multi-tenant read-only owner access

Revision ID: b62e4a91c730
Revises: a41d7c92e650
Create Date: 2026-09-11
"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = 'b62e4a91c730'
down_revision = 'a41d7c92e650'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    owner_role = connection.execute(sa.text("SELECT id FROM roles WHERE code = 'OWNER'" )).scalar_one_or_none()
    if owner_role is None:
        connection.execute(
            sa.text("INSERT INTO roles (id, code, name) VALUES (:id, 'OWNER', 'Multi-Tenant Owner')"),
            {'id': str(uuid4())},
        )
    # Assignment IDs are persisted as validated JSON in tenant_settings. That table
    # already exists and keeps upgrades compatible with restored installations where
    # the runtime role has CRUD access but intentionally has no schema CREATE grant.


def downgrade() -> None:
    op.execute("DELETE FROM tenant_settings WHERE setting_key LIKE '__platform_owner_tenants__:%'")
    op.execute("DELETE FROM roles WHERE code = 'OWNER' AND NOT EXISTS (SELECT 1 FROM users WHERE users.role_id = roles.id)")
