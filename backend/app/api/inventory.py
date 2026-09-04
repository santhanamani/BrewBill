from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .deps import require_role
from ..database import get_session
from ..models import AuditLog, Ingredient, IngredientStock, IngredientTransaction, Outlet, User
from ..schemas import (
    IngredientAdjustment,
    IngredientCreate,
    IngredientMovementRead,
    IngredientRead,
    IngredientUpdate,
)

router = APIRouter(prefix='/api/inventory', tags=['inventory'])


def current_outlet(user: User) -> str:
    if not user.outlet_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Select an outlet before managing inventory.')
    return user.outlet_id


def item_view(stock: IngredientStock) -> IngredientRead:
    item = stock.ingredient
    available = stock.available_quantity
    item_status = 'OUT_OF_STOCK' if available <= 0 else ('LOW_STOCK' if available <= stock.low_stock_limit else 'IN_STOCK')
    return IngredientRead(
        id=item.id, code=item.code, name=item.name, category=item.category,
        unit=item.unit, image_path=item.image_path,
        opening_quantity=stock.opening_quantity, stock_added=stock.stock_added,
        stock_used=stock.stock_used, available_quantity=available,
        low_stock_limit=stock.low_stock_limit, is_active=item.is_active, status=item_status,
    )


def find_stock(session: Session, user: User, ingredient_id: str, *, lock: bool = False) -> IngredientStock:
    statement = (
        select(IngredientStock)
        .join(Ingredient, Ingredient.id == IngredientStock.ingredient_id)
        .options(selectinload(IngredientStock.ingredient))
        .where(
            IngredientStock.tenant_id == user.tenant_id,
            IngredientStock.outlet_id == current_outlet(user),
            IngredientStock.ingredient_id == ingredient_id,
            Ingredient.tenant_id == user.tenant_id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    stock = session.scalar(statement)
    if stock is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Inventory item not found for this outlet.')
    return stock


@router.get('/items', response_model=list[IngredientRead])
def list_items(
    include_inactive: bool = Query(default=False),
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> list[IngredientRead]:
    statement = (
        select(IngredientStock)
        .join(Ingredient, Ingredient.id == IngredientStock.ingredient_id)
        .options(selectinload(IngredientStock.ingredient))
        .where(IngredientStock.tenant_id == user.tenant_id, IngredientStock.outlet_id == current_outlet(user))
        .order_by(Ingredient.name)
    )
    if not include_inactive:
        statement = statement.where(Ingredient.is_active.is_(True))
    return [item_view(row) for row in session.scalars(statement).all()]


@router.post('/items', response_model=IngredientRead, status_code=status.HTTP_201_CREATED)
def create_item(
    body: IngredientCreate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> IngredientRead:
    outlet_id = current_outlet(user)
    item = Ingredient(
        id=str(uuid4()), tenant_id=user.tenant_id, code=body.code.upper(),
        name=body.name, category=body.category, unit=body.unit,
        image_path=body.image_path, is_active=True,
    )
    session.add(item)
    selected_stock: IngredientStock | None = None
    try:
        session.flush()
        for outlet in session.scalars(select(Outlet).where(Outlet.tenant_id == user.tenant_id)).all():
            opening = body.opening_quantity if outlet.id == outlet_id else Decimal('0.000')
            stock = IngredientStock(
                id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=outlet.id, ingredient_id=item.id,
                opening_quantity=opening, stock_added=Decimal('0.000'), stock_used=Decimal('0.000'),
                available_quantity=opening, low_stock_limit=body.low_stock_limit,
            )
            session.add(stock)
            if outlet.id == outlet_id:
                selected_stock = stock
        session.add(AuditLog(
            id=str(uuid4()), tenant_id=user.tenant_id, actor_user_id=user.id,
            action='CREATE', entity_type='INGREDIENT', entity_id=item.id, payload='{}',
        ))
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Inventory item code already exists.') from error
    if selected_stock is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='No active outlet is available for inventory.')
    selected_stock.ingredient = item
    return item_view(selected_stock)


@router.patch('/items/{ingredient_id}', response_model=IngredientRead)
def update_item(
    ingredient_id: str,
    body: IngredientUpdate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> IngredientRead:
    stock = find_stock(session, user, ingredient_id, lock=True)
    values = body.model_dump(exclude_unset=True)
    low_stock_limit = values.pop('low_stock_limit', None)
    for field, value in values.items():
        setattr(stock.ingredient, field, value)
    if low_stock_limit is not None:
        stock.low_stock_limit = low_stock_limit
    session.add(AuditLog(
        id=str(uuid4()), tenant_id=user.tenant_id, actor_user_id=user.id,
        action='UPDATE', entity_type='INGREDIENT', entity_id=ingredient_id, payload='{}',
    ))
    session.commit()
    return item_view(stock)


@router.post('/items/{ingredient_id}/adjustments', response_model=IngredientRead)
def adjust_item(
    ingredient_id: str,
    body: IngredientAdjustment,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> IngredientRead:
    stock = find_stock(session, user, ingredient_id, lock=True)
    add = body.transaction_type == 'STOCK_IN' or (body.transaction_type == 'MANUAL_CORRECTION' and body.direction == 'ADD')
    delta = body.quantity if add else -body.quantity
    balance = stock.available_quantity + delta
    if balance < 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'Insufficient stock for {stock.ingredient.name}.')
    stock.available_quantity = balance
    if delta > 0:
        stock.stock_added += delta
    else:
        stock.stock_used += -delta
    session.add(IngredientTransaction(
        id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=current_outlet(user),
        ingredient_id=ingredient_id, transaction_type=body.transaction_type,
        quantity_delta=delta, balance_after=balance, reference=body.reference,
        notes=body.notes, created_by=user.id,
    ))
    session.add(AuditLog(
        id=str(uuid4()), tenant_id=user.tenant_id, actor_user_id=user.id,
        action=body.transaction_type, entity_type='INGREDIENT_STOCK', entity_id=stock.id,
        payload='{}',
    ))
    session.commit()
    return item_view(stock)


@router.get('/movements', response_model=list[IngredientMovementRead])
def list_movements(
    limit: int = Query(default=20, ge=1, le=200),
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> list[IngredientMovementRead]:
    rows = session.execute(
        select(IngredientTransaction, Ingredient.name, Ingredient.unit)
        .join(Ingredient, Ingredient.id == IngredientTransaction.ingredient_id)
        .where(
            IngredientTransaction.tenant_id == user.tenant_id,
            IngredientTransaction.outlet_id == current_outlet(user),
        )
        .order_by(IngredientTransaction.created_at.desc())
        .limit(limit)
    ).all()
    return [IngredientMovementRead(
        id=movement.id, ingredient_id=movement.ingredient_id, ingredient_name=name, unit=unit,
        transaction_type=movement.transaction_type, quantity_delta=movement.quantity_delta,
        balance_after=movement.balance_after, reference=movement.reference, notes=movement.notes,
        created_at=movement.created_at,
    ) for movement, name, unit in rows]
