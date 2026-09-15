from decimal import Decimal

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.cafe_catalogue import load_catalogue, sync_catalogue, validate_assets
from app.database import Base
from app.models import GlobalProduct, Product, Tenant


@pytest.fixture
def session():
    engine = create_engine('sqlite+pysqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_manifest_has_distinct_products_and_images():
    rows = load_catalogue()
    assert len(rows) == 54
    assert len({r['image_path'] for r in rows}) == 54


def test_partial_sync_and_resume_are_idempotent(session):
    rows = load_catalogue()[:2]
    report = sync_catalogue(session, rows, {'APPLE_JUICE'})
    session.commit()
    assert len(report['created']) == 2
    assert report['pending_images'] == ['ORANGE_JUICE']
    products = {p.code: p for p in session.scalars(select(GlobalProduct))}
    assert products['ORANGE_JUICE'].image_path is None
    assert products['APPLE_JUICE'].image_path == rows[0]['image_path']
    assert not sync_catalogue(session, rows, {'APPLE_JUICE'})['created']
    resumed = sync_catalogue(session, rows, {r['code'] for r in rows})
    session.commit()
    assert len(resumed['images_updated']) == 1
    assert not resumed['pending_images']
    assert not sync_catalogue(session, rows, {r['code'] for r in rows})['images_updated']


def test_repair_preserves_custom_photos_and_outlet_values(session):
    rows = load_catalogue()[:2]
    session.add(Tenant(id='tenant', code='TEST', name='Test', status='ACTIVE'))
    session.add_all([
        GlobalProduct(id='apple', code='APPLE_JUICE', name='Apple Juice', category_name='Juices',
                      image_path='products/photos/juice.png'),
        GlobalProduct(id='orange', code='ORANGE_JUICE', name='Orange Juice', category_name='Juices',
                      image_path='uploads/my-orange.png'),
        Product(id='legacy', tenant_id='tenant', code='APPLE_JUICE', name='Custom Apple Name',
                selling_price=Decimal('123.45'), stock_quantity=Decimal('17.000'),
                is_favourite=True, image_path='products/photos/juice.png'),
    ])
    session.commit()
    report = sync_catalogue(session, rows, {r['code'] for r in rows})
    session.commit()
    assert report['custom_images_preserved'] == ['ORANGE_JUICE']
    assert len(report['images_updated']) == 2
    legacy = session.get(Product, 'legacy')
    assert legacy.image_path == rows[0]['image_path']
    assert legacy.name == 'Custom Apple Name'
    assert legacy.selling_price == Decimal('123.45')
    assert legacy.stock_quantity == Decimal('17.000')
    assert legacy.is_favourite
    assert session.get(GlobalProduct, 'orange').image_path == 'uploads/my-orange.png'


def test_name_alias_does_not_create_duplicate(session):
    session.add(GlobalProduct(id='alias', code='CUSTOM_APPLE', name='Apple-Juice', category_name='Juices'))
    session.commit()
    report = sync_catalogue(session, load_catalogue()[:1], {'APPLE_JUICE'})
    assert report['name_conflicts'] == ['APPLE_JUICE']
    assert not report['created']


def test_assets_require_real_alpha_and_distinct_files(tmp_path):
    rows = load_catalogue()[:2]
    folder = tmp_path / 'products/cafe'
    folder.mkdir(parents=True)
    assert len(validate_assets(rows, tmp_path)['missing']) == 2
    sample = Image.new('RGBA', (8, 8), (255, 0, 0, 255))
    sample.putpixel((0, 0), (0, 0, 0, 0))
    sample.save(tmp_path / rows[0]['image_path'])
    assert not validate_assets(rows, tmp_path)['invalid']
    sample.save(tmp_path / rows[1]['image_path'])
    assert any('Duplicate' in v for v in validate_assets(rows, tmp_path)['invalid'])
    Image.new('RGB', (8, 8), 'white').save(tmp_path / rows[1]['image_path'])
    assert 'ORANGE_JUICE' in validate_assets(rows, tmp_path)['invalid']
    Image.new('RGBA', (8, 8), (0, 0, 0, 0)).save(tmp_path / rows[1]['image_path'])
    assert 'ORANGE_JUICE' in validate_assets(rows, tmp_path)['invalid']
