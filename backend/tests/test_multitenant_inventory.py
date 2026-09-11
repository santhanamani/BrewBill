from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.inventory_service import adjust_stock
from app.main import app
from app.models import Category, IngredientStock, Inventory, Outlet, Role, Tenant, User


def test_shared_catalogue_and_outlet_inventory_are_isolated() -> None:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as session:
        tenant = Tenant(id=str(uuid4()), name='Two Outlet Tenant', status='ACTIVE')
        outlet_a = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='AAAA', name='Outlet A')
        outlet_b = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='BAAA', name='Outlet B')
        role = Role(id=str(uuid4()), code='ADMIN', name='Administrator')
        user_a = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet_a.id, role_id=role.id, username='admin-a', display_name='Admin A', password_hash='x', is_active=True)
        user_b = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet_b.id, role_id=role.id, username='admin-b', display_name='Admin B', password_hash='x', is_active=True)
        user_a.role = role
        user_b.role = role
        category = Category(id=str(uuid4()), tenant_id=tenant.id, code='COFFEE', name='Coffee')
        session.add_all([tenant, outlet_a, outlet_b, role, user_a, user_b, category])
        session.commit()

    active_user = {'value': user_a}

    def test_session():
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: active_user['value']
    try:
        with TestClient(app) as client:
            # Legacy creation can insert a global master and is now owner-only.
            owner = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet_a.id)
            owner.role = Role(id=str(uuid4()), code='SUPER_ADMIN', name='Owner')
            active_user['value'] = owner
            created = client.post('/api/products', json={
                'code': 'SHARED_FILTER', 'name': 'Shared Filter Coffee',
                'selling_price': '40.00', 'purchase_price': '18.00', 'gst_percent': '5.00',
                'category_id': category.id, 'unit': 'pcs', 'stock_quantity': '10.000',
                'low_stock_limit': '2.000', 'is_favourite': True, 'kot_required': True,
                'is_available': True, 'is_active': True, 'shared_across_outlets': True,
            })
            assert created.status_code == 201, created.text
            product_id = created.json()['id']
            assert created.json()['shared_across_outlets'] is True
            assert created.json()['stock_quantity'] == '10.000'

            active_user['value'] = user_a
            ingredient = client.post('/api/inventory/items', json={
                'code': 'WHOLE_MILK', 'name': 'Milk (Whole)', 'category': 'Milk', 'unit': 'L',
                'opening_quantity': '50.000', 'low_stock_limit': '10.000',
            })
            assert ingredient.status_code == 201, ingredient.text
            ingredient_id = ingredient.json()['id']
            adjusted = client.post(f'/api/inventory/items/{ingredient_id}/adjustments', json={
                'transaction_type': 'STOCK_OUT', 'quantity': '5.000', 'notes': 'Kitchen issue',
            })
            assert adjusted.status_code == 200, adjusted.text
            assert adjusted.json()['available_quantity'] == '45.000'

            active_user['value'] = user_b
            outlet_b_products = client.get('/api/products')
            assert outlet_b_products.status_code == 200, outlet_b_products.text
            assert outlet_b_products.json()[0]['stock_quantity'] == '10.000'
            outlet_b_ingredients = client.get('/api/inventory/items')
            assert outlet_b_ingredients.status_code == 200
            assert outlet_b_ingredients.json()[0]['available_quantity'] == '0.000'

        with testing_session() as session:
            product = next(row for row in session.execute(select(Inventory).where(Inventory.product_id == product_id)).scalars() if row.outlet_id == outlet_a.id)
            product_model = product
            from app.models import Product
            catalogue_product = session.get(Product, product_id)
            assert catalogue_product is not None
            adjust_stock(session, user=user_a, outlet_id=outlet_a.id, product=catalogue_product, quantity_delta=Decimal('-2.000'), transaction_type='SALE', reference_type='TEST', reference_id='sale-a')
            session.commit()
            stocks = session.scalars(select(Inventory).where(Inventory.product_id == product_id)).all()
            balances = {row.outlet_id: row.available_quantity for row in stocks}
            assert balances[outlet_a.id] == Decimal('8.000')
            assert balances[outlet_b.id] == Decimal('10.000')
            ingredient_stocks = session.scalars(select(IngredientStock).where(IngredientStock.ingredient_id == ingredient_id)).all()
            ingredient_balances = {row.outlet_id: row.available_quantity for row in ingredient_stocks}
            assert ingredient_balances[outlet_a.id] == Decimal('45.000')
            assert ingredient_balances[outlet_b.id] == Decimal('0.000')
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
