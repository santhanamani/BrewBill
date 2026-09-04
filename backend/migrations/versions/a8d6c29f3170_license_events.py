"""signed offline license events

Revision ID: a8d6c29f3170
Revises: 55d4c12be901
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa

revision = 'a8d6c29f3170'
down_revision = '55d4c12be901'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'license_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('terminal_id', sa.String(36), nullable=False),
        sa.Column('event_type', sa.String(48), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['terminal_id'], ['pos_terminals.id']),
    )
    op.create_index('ix_license_events_tenant_id', 'license_events', ['tenant_id'])
    op.create_index('ix_license_events_terminal_id', 'license_events', ['terminal_id'])
    op.create_index('ix_license_events_event_type', 'license_events', ['event_type'])


def downgrade() -> None:
    op.drop_index('ix_license_events_event_type', table_name='license_events')
    op.drop_index('ix_license_events_terminal_id', table_name='license_events')
    op.drop_index('ix_license_events_tenant_id', table_name='license_events')
    op.drop_table('license_events')
