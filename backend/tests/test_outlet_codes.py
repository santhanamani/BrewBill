from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Outlet, Tenant
from app.outlet_codes import next_outlet_code


def test_outlet_codes_are_four_letters_and_global() -> None:
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first_tenant = Tenant(id='tenant-1', code='FIRST', name='First', status='ACTIVE')
        second_tenant = Tenant(id='tenant-2', code='SECOND', name='Second', status='ACTIVE')
        session.add_all([first_tenant, second_tenant])
        session.flush()

        first_code = next_outlet_code(session)
        first = Outlet(id='outlet-1', tenant_id=first_tenant.id, code=first_code, name='First Outlet')
        session.add(first)
        second_code = next_outlet_code(session)
        second = Outlet(id='outlet-2', tenant_id=second_tenant.id, code=second_code, name='Second Outlet')
        session.add(second)
        session.commit()

    assert first_code == 'AAAA'
    assert second_code == 'AAAB'
    assert len(first_code) == len(second_code) == 4
    assert first_code.isalpha() and second_code.isalpha()
    assert first_code.isupper() and second_code.isupper()
    assert first_code != second_code
