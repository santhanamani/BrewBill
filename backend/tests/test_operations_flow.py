from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import (
    Category, Expense, Ingredient, IngredientStock, IngredientTransaction,
    Inventory, InventoryTransaction, Outlet, Product, PurchaseItem, Role, Tenant, User,
)


def test_purchase_increases_stock_and_expense_is_persisted() -> None:
    engine = create_engine(
        'sqlite+pysqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as session:
        tenant = Tenant(id=str(uuid4()), name='Operations Tenant', status='ACTIVE')
        outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='OPER', name='Operations Outlet')
        role = Role(id=str(uuid4()), code='ADMIN', name='Administrator')
        user = User(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id,
            username='operations-admin', display_name='Operations Admin', password_hash='not-used', is_active=True,
        )
        user.role = role
        category = Category(id=str(uuid4()), tenant_id=tenant.id, code='COFFEE', name='Coffee')
        product = Product(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, category_id=category.id,
            code='ARABICA_BEANS', name='Arabica Beans', selling_price=Decimal('90.00'),
            purchase_price=Decimal('40.00'), gst_percent=Decimal('5.00'), stock_quantity=Decimal('4.000'),
            low_stock_limit=Decimal('2.000'), kot_required=False, is_available=True, is_active=True,
        )
        ingredient = Ingredient(
            id=str(uuid4()), tenant_id=tenant.id, code='MILK', name='Fresh Milk',
            category='Dairy', unit='L', is_active=True,
        )
        ingredient_stock = IngredientStock(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, ingredient_id=ingredient.id,
            opening_quantity=Decimal('2.000'), stock_added=Decimal('0.000'),
            stock_used=Decimal('0.000'), available_quantity=Decimal('2.000'),
            low_stock_limit=Decimal('1.000'),
        )
        session.add_all([tenant, outlet, role, user, category, product, ingredient, ingredient_stock])
        session.commit()

    def test_session():
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(app) as client:
            supplier_response = client.post('/api/suppliers', json={'name': 'Global Foods'})
            assert supplier_response.status_code == 201, supplier_response.text
            supplier_id = supplier_response.json()['id']

            purchase_response = client.post('/api/purchases', json={
                'supplier_id': supplier_id,
                'invoice_number': 'INV-OPS-001',
                'purchase_date': datetime.now(UTC).isoformat(),
                'payment_status': 'PAID',
                'items': [{
                    'product_id': product.id,
                    'quantity': '6.000',
                    'unit_cost': '50.00',
                    'tax_percent': '5.00',
                }],
            })
            assert purchase_response.status_code == 201, purchase_response.text
            assert purchase_response.json()['total'] == '315.00'

            ingredient_purchase = client.post('/api/purchases', json={
                'supplier_id': supplier_id,
                'invoice_number': 'INV-OPS-ING-001',
                'purchase_date': datetime.now(UTC).isoformat(),
                'payment_status': 'PENDING',
                'notes': 'Dairy delivery',
                'items': [{
                    'ingredient_id': ingredient.id,
                    'quantity': '5.000',
                    'unit_cost': '20.00',
                    'tax_percent': '0.00',
                }],
            })
            assert ingredient_purchase.status_code == 201, ingredient_purchase.text
            ingredient_purchase_id = ingredient_purchase.json()['id']
            assert ingredient_purchase.json()['items'][0]['ingredient_id'] == ingredient.id

            edited_purchase = client.patch(f'/api/purchases/{ingredient_purchase_id}', json={
                'supplier_id': supplier_id,
                'invoice_number': 'INV-OPS-ING-001',
                'purchase_date': datetime.now(UTC).isoformat(),
                'payment_status': 'PAID',
                'notes': 'Corrected dairy delivery',
                'items': [{
                    'ingredient_id': ingredient.id,
                    'quantity': '7.000',
                    'unit_cost': '22.00',
                    'tax_percent': '5.00',
                }],
            })
            assert edited_purchase.status_code == 200, edited_purchase.text
            assert edited_purchase.json()['total'] == '161.70'
            assert edited_purchase.json()['payment_status'] == 'PAID'

            expense_response = client.post('/api/expenses', json={
                'expense_date': datetime.now(UTC).isoformat(),
                'category': 'Supplies',
                'description': 'Cleaning supplies',
                'amount': '750.00',
                'payment_mode': 'CASH',
            })
            assert expense_response.status_code == 201, expense_response.text
            assert client.get('/api/expenses').json()[0]['created_by_name'] == 'Operations Admin'

        with testing_session() as session:
            inventory = session.scalar(select(Inventory).where(
                Inventory.outlet_id == outlet.id, Inventory.product_id == product.id,
            ))
            assert inventory is not None
            assert inventory.available_quantity == Decimal('10.000')
            stored_product = session.get(Product, product.id)
            assert stored_product is not None
            assert stored_product.purchase_price == Decimal('50.00')
            assert session.scalar(select(Expense).where(Expense.tenant_id == tenant.id)) is not None
            movement = session.scalar(
                select(InventoryTransaction).where(InventoryTransaction.product_id == product.id)
            )
            assert movement is not None
            assert movement.transaction_type == 'PURCHASE'
            assert movement.quantity_delta == Decimal('6.000')
            stored_ingredient = session.scalar(select(IngredientStock).where(
                IngredientStock.outlet_id == outlet.id,
                IngredientStock.ingredient_id == ingredient.id,
            ))
            assert stored_ingredient is not None
            assert stored_ingredient.available_quantity == Decimal('9.000')
            assert stored_ingredient.stock_added == Decimal('7.000')
            ingredient_movements = session.scalars(
                select(IngredientTransaction)
                .where(IngredientTransaction.ingredient_id == ingredient.id)
                .order_by(IngredientTransaction.created_at)
            ).all()
            assert [row.quantity_delta for row in ingredient_movements] == [
                Decimal('5.000'), Decimal('-5.000'), Decimal('7.000'),
            ]
            ingredient_line = session.scalar(select(PurchaseItem).where(
                PurchaseItem.ingredient_id == ingredient.id,
            ))
            assert ingredient_line is not None
            assert ingredient_line.product_id is None
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
