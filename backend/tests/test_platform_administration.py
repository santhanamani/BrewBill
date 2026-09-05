from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import Role, SubscriptionPlan, Tenant, User


def test_super_admin_can_create_tenant_outlet_and_tenant_user() -> None:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as session:
        platform = Tenant(id=str(uuid4()), code='PLATFORM', name='Platform', status='ACTIVE')
        super_role = Role(id=str(uuid4()), code='SUPER_ADMIN', name='Super Administrator')
        tenant_role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Tenant Administrator')
        cashier_role = Role(id=str(uuid4()), code='CASHIER', name='Cashier')
        super_user = User(id=str(uuid4()), tenant_id=platform.id, role_id=super_role.id, username='owner', display_name='Owner', password_hash='x', is_active=True)
        plan = SubscriptionPlan(id=str(uuid4()), code='PROFESSIONAL', name='Professional', max_terminals=3, feature_json='{}')
        session.add_all([platform, super_role, tenant_role, cashier_role, super_user, plan]); session.commit()
        super_user.role = super_role

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: super_user
    try:
        with TestClient(app) as client:
            tenant_response = client.post('/api/platform/admin/tenants', json={
                'code':'BHV-CBE','name':'Brew Haven Coimbatore','outlet_code':'MAIN',
                'outlet_name':'RS Puram','outlet_address':'Coimbatore',
                'admin_username':'admin','admin_password':'Temporary@123',
                'admin_display_name':'Tenant Admin','plan_code':'PROFESSIONAL',
            })
            assert tenant_response.status_code == 201, tenant_response.text
            tenant = tenant_response.json()
            assert tenant['code'] == 'BHV-CBE'

            outlets = client.get(f"/api/platform/admin/outlets?tenant_id={tenant['id']}").json()
            assert len(outlets) == 1
            user_response = client.post('/api/platform/admin/users', json={
                'tenant_id':tenant['id'],'outlet_id':outlets[0]['id'],'role_code':'CASHIER',
                'username':'cashier2','display_name':'Cashier Two','email':None,'phone':'9876543210',
                'password':'Temporary@123',
            })
            assert user_response.status_code == 201, user_response.text
            user = user_response.json()
            assert user['tenant_name'] == 'Brew Haven Coimbatore'
            disabled = client.patch(f"/api/platform/admin/users/{user['id']}", json={'is_active':False})
            assert disabled.status_code == 200
            assert disabled.json()['is_active'] is False
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
