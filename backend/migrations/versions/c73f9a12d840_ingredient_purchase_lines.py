"""ingredient-backed purchase lines

Revision ID: c73f9a12d840
Revises: b62e4a91c730
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = 'c73f9a12d840'
down_revision = 'b62e4a91c730'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('purchase_items', sa.Column('ingredient_id', sa.String(36), nullable=True))
    op.create_foreign_key(
        'fk_purchase_items_ingredient_id',
        'purchase_items',
        'ingredients',
        ['ingredient_id'],
        ['id'],
    )
    op.create_index('ix_purchase_items_ingredient_id', 'purchase_items', ['ingredient_id'])
    op.alter_column('purchase_items', 'product_id', existing_type=sa.String(36), nullable=True)
    op.create_check_constraint(
        'ck_purchase_items_single_source',
        'purchase_items',
        '(product_id IS NULL) <> (ingredient_id IS NULL)',
    )


def downgrade() -> None:
    # Ingredient-only lines cannot satisfy the legacy non-null product column.
    op.drop_constraint('ck_purchase_items_single_source', 'purchase_items', type_='check')
    op.execute('DELETE FROM purchase_items WHERE product_id IS NULL')
    op.alter_column('purchase_items', 'product_id', existing_type=sa.String(36), nullable=False)
    op.drop_index('ix_purchase_items_ingredient_id', table_name='purchase_items')
    op.drop_constraint('fk_purchase_items_ingredient_id', 'purchase_items', type_='foreignkey')
    op.drop_column('purchase_items', 'ingredient_id')
