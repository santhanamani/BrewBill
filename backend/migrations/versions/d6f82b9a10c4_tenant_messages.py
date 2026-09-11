"""ultra professional tenant messaging

Revision ID: d6f82b9a10c4
Revises: b3c91f4a2d10
Create Date: 2026-09-10
"""

from alembic import op
import sqlalchemy as sa


revision = 'd6f82b9a10c4'
down_revision = 'b3c91f4a2d10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenant_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('sender_user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recipient_user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('audience', sa.String(16), nullable=False, server_default='DIRECT'),
        sa.Column('subject', sa.String(160), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ('tenant_id', 'sender_user_id', 'recipient_user_id', 'audience', 'read_at', 'created_at'):
        op.create_index(f'ix_tenant_messages_{column}', 'tenant_messages', [column])
    op.execute("UPDATE subscription_plans SET feature_json = CAST(CAST(feature_json AS jsonb) || '{\"tenant_messaging\": true}'::jsonb AS text) WHERE code = 'ULTRA_PROFESSIONAL'")
    op.execute("UPDATE subscription_plans SET feature_json = CAST(CAST(feature_json AS jsonb) || '{\"tenant_messaging\": false}'::jsonb AS text) WHERE code = 'PROFESSIONAL'")


def downgrade() -> None:
    op.drop_table('tenant_messages')
