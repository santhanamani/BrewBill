"""message replies, group identity and emoji reactions

Revision ID: d84c2f17a950
Revises: c73f9a12d840
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = 'd84c2f17a950'
down_revision = 'c73f9a12d840'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tenant_messages', sa.Column('group_message_id', sa.String(36), nullable=True))
    op.add_column('tenant_messages', sa.Column('reply_to_id', sa.String(36), nullable=True))
    op.create_index('ix_tenant_messages_group_message_id', 'tenant_messages', ['group_message_id'])
    op.create_index('ix_tenant_messages_reply_to_id', 'tenant_messages', ['reply_to_id'])
    op.create_foreign_key(
        'fk_tenant_messages_reply_to_id', 'tenant_messages', 'tenant_messages', ['reply_to_id'], ['id'],
    )
    op.create_table(
        'tenant_message_reactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('message_id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('emoji', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['message_id'], ['tenant_messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('message_id', 'user_id', name='uq_tenant_message_reaction_user'),
    )
    for column in ('tenant_id', 'message_id', 'user_id'):
        op.create_index(f'ix_tenant_message_reactions_{column}', 'tenant_message_reactions', [column])


def downgrade() -> None:
    for column in ('user_id', 'message_id', 'tenant_id'):
        op.drop_index(f'ix_tenant_message_reactions_{column}', table_name='tenant_message_reactions')
    op.drop_table('tenant_message_reactions')
    op.drop_constraint('fk_tenant_messages_reply_to_id', 'tenant_messages', type_='foreignkey')
    op.drop_index('ix_tenant_messages_reply_to_id', table_name='tenant_messages')
    op.drop_index('ix_tenant_messages_group_message_id', table_name='tenant_messages')
    op.drop_column('tenant_messages', 'reply_to_id')
    op.drop_column('tenant_messages', 'group_message_id')
