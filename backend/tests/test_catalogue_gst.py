from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app.models import GlobalProduct, PosTerminal, Role, Subscription, SubscriptionPlan
from test_catalogue_stock import catalogue


def test_outlet_gst_off_custom_and_inherit_are_persisted_and_isolated(catalogue):
    client, active, users, mappings, engine, sessions = catalogue
    url = f'/api/products/catalogue/{mappings[0]["id"]}'
    for override, expected in [('0.00', '0.00'), ('12.50', '12.50'), (None, '5.00')]:
        saved = client.patch(url, json={'tax_override': override})
        assert saved.status_code == 200, saved.text
        engine.dispose()
        assert client.get('/api/products/catalogue').json()[0]['tax_override'] == override
        assert client.get('/api/products').json()[0]['gst_percent'] == expected
        for other in users[1:]:
            active['user'] = other
            assert client.get('/api/products').json()[0]['gst_percent'] == '5.00'
            assert client.patch(url, json={'tax_override': '99.00'}).status_code == 404
        active['user'] = users[0]
    with sessions() as db:
        assert db.get(GlobalProduct, mappings[0]['global_product_id']).default_gst == Decimal('5.00')


@pytest.mark.parametrize('rate', ['-1', '100.01', '1.234', 'NaN', 'Infinity', 'abc'])
def test_invalid_gst_rejected_without_saving_other_fields(catalogue, rate):
    client, _, _, mappings, _, _ = catalogue
    result = client.patch(f'/api/products/catalogue/{mappings[0]["id"]}', json={'tax_override': rate, 'selling_price': '1.00'})
    assert result.status_code == 422
    assert client.get('/api/products/catalogue').json()[0]['selling_price'] == '80.00'


@pytest.mark.parametrize('role', ['ADMIN', 'TENANT_ADMIN', 'CASHIER'])
def test_only_super_admin_can_create_or_edit_global_master_including_legacy_path(catalogue, role):
    client, active, _, mappings, _, _ = catalogue
    active['user'].role = Role(id=str(uuid4()), code=role, name=role)
    master = mappings[0]['global_product_id']
    assert client.get('/api/products/master').status_code == 200
    assert client.post('/api/products/master', json={'code':'NEW','name':'New','category_name':'Coffee'}).status_code == 403
    assert client.patch(f'/api/products/master/{master}', json={'name':'Changed'}).status_code == 403
    assert client.post('/api/products', json={'code':'NEW','name':'New','selling_price':'1'}).status_code == 403
    if role == 'CASHIER':
        assert client.patch(f'/api/products/catalogue/{mappings[0]["id"]}', json={'tax_override':'0'}).status_code == 403


def test_gst_matches_pos_holds_and_completed_bills_and_does_not_rewrite_history(catalogue):
    client, _, users, mappings, _, sessions = catalogue
    user = users[0]
    with sessions() as db:
        plan = SubscriptionPlan(id=str(uuid4()), code='GST', name='GST Test', max_terminals=2, feature_json='{}')
        db.add_all([plan, Subscription(id=str(uuid4()), tenant_id=user.tenant_id, plan_id=plan.id, status='ACTIVE', starts_at=datetime.now(UTC)-timedelta(days=1), ends_at=datetime.now(UTC)+timedelta(days=30)),
                    PosTerminal(id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=user.outlet_id, terminal_code='GST01', terminal_name='GST Test', device_key_hash='test', status='ACTIVE')])
        # Master changes must also reach holds when no override is set.
        db.get(GlobalProduct, mappings[0]['global_product_id']).default_gst = Decimal('10.00')
        db.commit()
    url = f'/api/products/catalogue/{mappings[0]["id"]}'
    bills = []
    items = [{'product_id': mappings[0]['legacy_product_id'], 'quantity': 1}]
    for override, expected_tax in [(None, '8.00'), ('0.00', '0.00'), ('12.50', '10.00')]:
        assert client.patch(url, json={'tax_override': override}).status_code == 200
        hold = client.post('/api/holds', json={'terminal_code':'GST01', 'items':items})
        assert hold.status_code == 201, hold.text
        assert hold.json()['tax'] == expected_tax
        total = Decimal('80.00') + Decimal(expected_tax)
        order = client.post('/api/orders', json={'order_id':str(uuid4()), 'terminal_code':'GST01', 'items':items, 'payments':[{'mode':'CASH','amount':str(total)}], 'order_type':'DIRECT'})
        assert order.status_code == 201, order.text
        assert order.json()['tax'] == expected_tax
        assert Decimal(order.json()['grand_total']) == total
        bills.append((order.json()['id'], expected_tax))
    history = {row['id']: row for row in client.get('/api/orders').json()}
    for order_id, tax in bills:
        assert history[order_id]['tax'] == tax
