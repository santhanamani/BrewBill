from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .deps import require_role
from ..database import get_session
from ..models import AuditLog, Category, User
from ..schemas import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix='/api/categories', tags=['categories'])


@router.get('', response_model=list[CategoryRead])
def list_categories(
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> list[Category]:
    statement = select(Category).where(Category.tenant_id == user.tenant_id, Category.is_active.is_(True)).order_by(Category.display_order, Category.name)
    return list(session.scalars(statement))


@router.post('', response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryCreate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> Category:
    category = Category(id=str(uuid4()), tenant_id=user.tenant_id, is_active=True, **body.model_dump())
    session.add(category)
    session.add(AuditLog(id=str(uuid4()), tenant_id=user.tenant_id, actor_user_id=user.id, action='CREATE', entity_type='CATEGORY', entity_id=category.id, payload='{}'))
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Category code already exists.') from error
    session.refresh(category)
    return category


@router.patch('/{category_id}', response_model=CategoryRead)
def update_category(
    category_id: str,
    body: CategoryUpdate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> Category:
    category = session.scalar(select(Category).where(Category.id == category_id, Category.tenant_id == user.tenant_id))
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Category not found.')
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    session.add(AuditLog(id=str(uuid4()), tenant_id=user.tenant_id, actor_user_id=user.id, action='UPDATE', entity_type='CATEGORY', entity_id=category.id, payload='{}'))
    session.commit()
    session.refresh(category)
    return category
