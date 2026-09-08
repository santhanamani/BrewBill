from decimal import Decimal
from uuid import uuid4

from sqlalchemy import event
from app.models import GlobalProduct
from test_catalogue_stock import catalogue


def test_catalogue_reads_use_bounded_queries_and_fresh_stock(catalogue):
    client, _, _, mappings, engine, sessions = catalogue
    with sessions() as db:
        masters = [GlobalProduct(id=str(uuid4()), code=f'EXTRA-{i}', name=f'Extra {i}',
                                 category_name='Coffee', base_unit='pcs', default_gst=Decimal('5'), status='ACTIVE')
                   for i in range(8)]
        db.add_all(masters); db.commit()
    for master in masters:
        response=client.post(f'/api/products/catalogue/{master.id}',json={'selling_price':'10','opening_stock':'20'})
        assert response.status_code == 201, response.text
    queries=[]
    def count(conn,cursor,statement,parameters,context,many):
        if statement.lstrip().upper().startswith('SELECT'):
            queries.append(statement)
    event.listen(engine,'before_cursor_execute',count)
    try:
        for endpoint in ['/api/products','/api/products/catalogue']:
            queries.clear()
            response=client.get(endpoint)
            assert response.status_code == 200, response.text
            assert len(response.json()) == 9
            assert len(queries) <= 8, f'{endpoint} used {len(queries)} SELECT queries'
    finally:
        event.remove(engine,'before_cursor_execute',count)
    changed=client.patch(f'/api/products/catalogue/{mappings[0]["id"]}',json={'stock_quantity':'35','expected_stock_quantity':'40'})
    assert changed.status_code == 200
    rows=client.get('/api/products').json()
    assert next(row for row in rows if row['id']==mappings[0]['legacy_product_id'])['stock_quantity']=='35.000'
