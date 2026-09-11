from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Inventory, InventoryTransaction, Product, User


def adjust_stock(
    session: Session,
    *,
    user: User,
    outlet_id: str,
    product: Product,
    quantity_delta: Decimal,
    transaction_type: str,
    reference_type: str,
    reference_id: str,
    notes: str | None = None,
) -> None:
    inventory = session.scalar(
        select(Inventory)
        .where(
            Inventory.tenant_id == user.tenant_id,
            Inventory.outlet_id == outlet_id,
            Inventory.product_id == product.id,
        )
        .with_for_update()
    )
    if inventory is None:
        # Legacy databases stored opening stock on products. Import it once into
        # the outlet ledger; all later reads and writes use this inventory row.
        inventory = Inventory(
            id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=outlet_id,
            product_id=product.id, opening_quantity=product.stock_quantity,
            stock_added=Decimal('0.000'), stock_sold=Decimal('0.000'),
            available_quantity=product.stock_quantity, low_stock_limit=product.low_stock_limit,
        )
        session.add(inventory)
        session.flush()
    new_quantity = inventory.available_quantity + quantity_delta
    if new_quantity < 0:
        raise ValueError(f'Insufficient stock for {product.name}.')
    inventory.available_quantity = new_quantity
    if transaction_type == 'PURCHASE_REVERSAL':
        inventory.stock_added = max(Decimal('0.000'), inventory.stock_added + quantity_delta)
    elif quantity_delta > 0:
        inventory.stock_added += quantity_delta
    elif transaction_type == 'SALE':
        inventory.stock_sold += -quantity_delta
    elif transaction_type == 'VOID_REVERSAL':
        inventory.stock_sold = max(Decimal('0.000'), inventory.stock_sold - quantity_delta)
    session.add(InventoryTransaction(
        id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=outlet_id,
        product_id=product.id, transaction_type=transaction_type,
        quantity_delta=quantity_delta, reference_type=reference_type,
        reference_id=reference_id, notes=notes, created_by=user.id,
    ))
