from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import Category, Customer, CustomerCreditEntry, Order, Outlet, PosTerminal, Product, Role, Subscription, SubscriptionPlan, Tenant, User


def test_repeated_credit_bills_accumulate_and_full_settlement_clears_balance() -> None:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as db:
        tenant = Tenant(id=str(uuid4()), code='CREDIT-CAFE', name='Credit Cafe', status='ACTIVE')
        outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='MAIN', name='Main')
        role = Role(id=str(uuid4()), code='ADMIN', name='Admin')
        user = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id, username='admin', display_name='Admin', password_hash='x', is_active=True)
        plan = SubscriptionPlan(id=str(uuid4()), code='PROFESSIONAL', name='Professional', max_terminals=3, feature_json='{"customer_credit":true}')
        subscription = Subscription(id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE', starts_at=datetime.now(UTC)-timedelta(days=1), ends_at=datetime.now(UTC)+timedelta(days=30))
        terminal = PosTerminal(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, terminal_code='POS01', terminal_name='Counter', device_key_hash='credit-test', status='ACTIVE')
        category = Category(id=str(uuid4()), tenant_id=tenant.id, code='DRINKS', name='Drinks')
        product = Product(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, category_id=category.id, code='TEA', name='Tea', selling_price=Decimal('40.00'), purchase_price=Decimal('10.00'), gst_percent=Decimal('0.00'), stock_quantity=Decimal('20.000'), low_stock_limit=Decimal('1.000'), is_available=True, is_active=True)
        customer = Customer(id=str(uuid4()), tenant_id=tenant.id, name='Arun', mobile='9876543210', loyalty_points=0)
        db.add_all([tenant, outlet, role, user, plan, subscription, terminal, category, product, customer])
        db.commit()
    user.role = role

    def test_session():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(app) as client:
            for quantity in (1, 2):
                response = client.post('/api/orders', json={
                    'order_id': str(uuid4()), 'terminal_code': 'POS01',
                    'items': [{'product_id': product.id, 'quantity': quantity}],
                    'payments': [], 'credit_customer_id': customer.id,
                    'credit_due_days': 10, 'order_type': 'DIRECT',
                })
                assert response.status_code == 201, response.text
                assert response.json()['payment_status'] == 'CREDIT'

            partial_bill = client.post('/api/orders', json={
                'order_id': str(uuid4()), 'terminal_code': 'POS01',
                'items': [{'product_id': product.id, 'quantity': 1}],
                'payments': [{'mode': 'CASH', 'amount': '10.00'}],
                'credit_customer_id': customer.id,
                'credit_due_days': 10, 'order_type': 'DIRECT',
            })
            assert partial_bill.status_code == 201, partial_bill.text
            assert partial_bill.json()['payment_status'] == 'PARTIAL_CREDIT'

            account = client.get('/api/customers/credit-accounts')
            assert account.status_code == 200, account.text
            assert account.json()[0]['outstanding_balance'] == '150.00'
            assert account.json()[0]['open_bill_count'] == 3

            partly_settled = client.post(
                f'/api/customers/{customer.id}/credit/settle',
                json={'payment_mode': 'UPI', 'amount': '50.00'},
            )
            assert partly_settled.status_code == 200, partly_settled.text
            assert partly_settled.json()['outstanding_balance'] == '100.00'

            with sessions() as db:
                assert {row.payment_status for row in db.query(Order).filter_by(customer_id=customer.id)} == {'CREDIT', 'PARTIAL_CREDIT'}

            settled = client.post(f'/api/customers/{customer.id}/credit/settle', json={'payment_mode': 'CASH'})
            assert settled.status_code == 200, settled.text
            assert settled.json()['outstanding_balance'] == '0.00'

        with sessions() as db:
            assert db.query(CustomerCreditEntry).filter_by(customer_id=customer.id).count() == 5
            assert {row.payment_status for row in db.query(Order).filter_by(customer_id=customer.id)} == {'SETTLED'}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
