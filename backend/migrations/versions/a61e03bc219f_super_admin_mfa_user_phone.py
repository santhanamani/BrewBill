"""super admin mfa and user phone

Revision ID: a61e03bc219f
Revises: e4c2a9f18b70
"""

from alembic import op
import sqlalchemy as sa

revision = 'a61e03bc219f'
down_revision = 'e4c2a9f18b70'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(32), nullable=True))
    op.add_column('users', sa.Column('mfa_secret_encrypted', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('users', 'mfa_enabled')
    op.drop_column('users', 'mfa_secret_encrypted')
    op.drop_column('users', 'phone')
