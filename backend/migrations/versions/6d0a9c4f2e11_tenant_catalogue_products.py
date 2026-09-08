"""allow tenant-owned outlet catalogue products

Revision ID: 6d0a9c4f2e11
Revises: a61e03bc219f
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa


revision = '6d0a9c4f2e11'
down_revision = 'a61e03bc219f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A null master identifies a product owned by the tenant catalogue. The
    # legacy product remains the operational record used by orders/inventory.
    op.alter_column(
        'outlet_product_mappings',
        'global_product_id',
        existing_type=sa.String(length=36),
        nullable=True,
    )


def downgrade() -> None:
    # Older application versions cannot read local mappings.
    op.execute(sa.text(
        'DELETE FROM outlet_product_mappings WHERE global_product_id IS NULL'
    ))
    op.alter_column(
        'outlet_product_mappings',
        'global_product_id',
        existing_type=sa.String(length=36),
        nullable=False,
    )
