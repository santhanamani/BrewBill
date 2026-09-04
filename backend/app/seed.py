"""Idempotent PostgreSQL fixture importer.

Business records intentionally live in ``backend/seed_data/*.json``. This
module contains orchestration only, so changing a catalogue never requires a
Python code change and the running application always reads PostgreSQL.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from .database import SessionLocal
from .models import (
    Category,
    GlobalProduct,
    Ingredient,
    IngredientStock,
    Inventory,
    Outlet,
    OutletProductMapping,
    PosTerminal,
    Product,
    ProductVariant,
    Role,
    Subscription,
    SubscriptionPlan,
    Tenant,
    User,
)
from .security import hash_password

FIXTURE_DIRECTORY = Path(__file__).resolve().parent.parent / 'seed_data'


def decimal(value: object, default: str = '0.000') -> Decimal:
    return Decimal(str(value if value is not None else default))


def get_or_create(session, model, defaults: dict, **filters):
    item = session.scalar(select(model).filter_by(**filters))
    if item is None:
        item = model(id=str(uuid4()), **defaults, **filters)
        session.add(item)
        session.flush()
    return item


def load_fixture(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as fixture_file:
        return json.load(fixture_file)


def import_fixture(session, fixture: dict) -> tuple[str, int, int]:
    tenant_data = fixture['tenant']
    tenant = get_or_create(
        session, Tenant, {
            'code': tenant_data.get('code'),
            'status': tenant_data.get('status', 'ACTIVE'),
            'logo_url': tenant_data.get('logo_url'),
            'cover_image_url': tenant_data.get('cover_image_url'),
            'primary_color': tenant_data.get('primary_color', '#5A2D18'),
            'secondary_color': tenant_data.get('secondary_color', '#C8874A'),
            'tagline': tenant_data.get('tagline'),
        }, name=tenant_data['name']
    )
    tenant.code = tenant_data.get('code') or tenant.code
    plan_data = fixture['plan']
    plan = get_or_create(
        session,
        SubscriptionPlan,
        {
            'name': plan_data['name'],
            'max_terminals': plan_data['max_terminals'],
            'feature_json': json.dumps(plan_data.get('features', {}), separators=(',', ':')),
        },
        code=plan_data['code'],
    )
    if not session.scalar(select(Subscription.id).where(Subscription.tenant_id == tenant.id)):
        session.add(Subscription(
            id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE',
            starts_at=datetime.now(UTC),
            ends_at=datetime.now(UTC) + timedelta(days=int(fixture['subscription_days'])),
        ))

    outlets: dict[str, Outlet] = {}
    for row in fixture.get('outlets', []):
        outlet = get_or_create(
            session, Outlet,
            {'name': row['name'], 'address': row.get('address')},
            tenant_id=tenant.id, code=row['code'],
        )
        outlets[row['code']] = outlet

    roles: dict[str, Role] = {}
    for row in fixture.get('roles', []):
        roles[row['code']] = get_or_create(session, Role, {'name': row['name']}, code=row['code'])
    roles['SUPER_ADMIN'] = get_or_create(session, Role, {'name': 'Super Administrator'}, code='SUPER_ADMIN')
    roles['TENANT_ADMIN'] = get_or_create(session, Role, {'name': 'Tenant Administrator'}, code='TENANT_ADMIN')

    for row in fixture.get('users', []):
        get_or_create(
            session, User,
            {
                'outlet_id': outlets[row['outlet_code']].id if row.get('outlet_code') else None,
                'role_id': roles[row['role_code']].id,
                'display_name': row['display_name'],
                'password_hash': hash_password(row['password']),
                'is_active': True,
            },
            tenant_id=tenant.id, username=row['username'],
        )

    for row in fixture.get('terminals', []):
        get_or_create(
            session, PosTerminal,
            {
                'terminal_name': row['name'],
                'device_key_hash': row['device_key_hash'],
                'status': 'ACTIVE',
                'activated_at': datetime.now(UTC),
            },
            tenant_id=tenant.id, terminal_code=row['code'], outlet_id=outlets[row['outlet_code']].id,
        )

    categories: dict[str, Category] = {}
    for index, row in enumerate(fixture.get('categories', [])):
        category = get_or_create(
            session, Category,
            {
                'name': row['name'], 'image_path': row.get('image_path'),
                'display_order': index, 'is_active': True,
            },
            tenant_id=tenant.id, code=row['code'],
        )
        category.name = row['name']
        category.image_path = row.get('image_path')
        category.display_order = index
        categories[row['code']] = category

    for row in fixture.get('products', []):
        price = decimal(row['selling_price'], '0.00')
        opening = decimal(row.get('opening_quantity', '40.000'))
        low_limit = decimal(row.get('low_stock_limit', '5.000'))
        product = session.scalar(select(Product).where(Product.tenant_id == tenant.id, Product.code == row['code']))
        if product is None:
            product = Product(
                id=str(uuid4()), tenant_id=tenant.id, outlet_id=None,
                category_id=categories[row['category']].id, code=row['code'], name=row['name'],
                selling_price=price, purchase_price=decimal(row.get('purchase_price', price * Decimal('0.45')), '0.00'),
                gst_percent=decimal(row.get('gst_percent', '5.00'), '0.00'),
                description=row.get('description'), image_path=row.get('image_path'), unit=row.get('unit', 'pcs'),
                stock_quantity=Decimal('0.000'), low_stock_limit=Decimal('0.000'),
                is_favourite=bool(row.get('favourite', False)), kot_required=bool(row.get('kot_required', True)),
                is_available=bool(row.get('is_available', True)), is_active=True,
            )
            session.add(product)
            session.flush()
        else:
            product.outlet_id = None
            product.category_id = categories[row['category']].id
            product.name = row['name']
            product.image_path = row.get('image_path')
        global_product = session.scalar(select(GlobalProduct).where(GlobalProduct.code == row['code'].upper()))
        if global_product is None:
            global_product = GlobalProduct(
                id=str(uuid4()), code=row['code'].upper(), name=row['name'],
                description=row.get('description'), category_name=categories[row['category']].name,
                base_unit=row.get('unit', 'pcs'),
                default_gst=decimal(row.get('gst_percent', '5.00'), '0.00'),
                image_path=row.get('image_path'), status='ACTIVE',
            )
            session.add(global_product)
            session.flush()
        for outlet in outlets.values():
            stock = session.scalar(select(Inventory).where(
                Inventory.tenant_id == tenant.id, Inventory.outlet_id == outlet.id,
                Inventory.product_id == product.id,
            ))
            if stock is None:
                session.add(Inventory(
                    id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, product_id=product.id,
                    opening_quantity=opening, stock_added=Decimal('0.000'), stock_sold=Decimal('0.000'),
                    available_quantity=opening, low_stock_limit=low_limit,
                ))
            mapping = session.scalar(select(OutletProductMapping).where(
                OutletProductMapping.outlet_id == outlet.id,
                OutletProductMapping.global_product_id == global_product.id,
            ))
            if mapping is None:
                session.add(OutletProductMapping(
                    id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id,
                    global_product_id=global_product.id, legacy_product_id=product.id,
                    selling_price=price, favourite=bool(row.get('favourite', False)),
                    kot_required=bool(row.get('kot_required', True)),
                    is_available=bool(row.get('is_available', True)), is_active=True,
                    display_order=0,
                ))
        for index, variant_data in enumerate(row.get('variants', [])):
            get_or_create(
                session, ProductVariant,
                {
                    'tenant_id': tenant.id,
                    'price_adjustment': decimal(variant_data.get('price_adjustment', '0.00'), '0.00'),
                    'display_order': index, 'is_active': True,
                },
                product_id=product.id, name=variant_data['name'],
            )

    for row in fixture.get('ingredients', []):
        item = session.scalar(select(Ingredient).where(Ingredient.tenant_id == tenant.id, Ingredient.code == row['code']))
        if item is None:
            item = Ingredient(
                id=str(uuid4()), tenant_id=tenant.id, code=row['code'], name=row['name'],
                category=row['category'], unit=row['unit'], image_path=row.get('image_path'), is_active=True,
            )
            session.add(item)
            session.flush()
        else:
            item.name, item.category, item.unit = row['name'], row['category'], row['unit']
            item.image_path = row.get('image_path')
        opening = decimal(row.get('opening_quantity'))
        added = decimal(row.get('stock_added'))
        used = decimal(row.get('stock_used'))
        for outlet in outlets.values():
            stock = session.scalar(select(IngredientStock).where(
                IngredientStock.tenant_id == tenant.id, IngredientStock.outlet_id == outlet.id,
                IngredientStock.ingredient_id == item.id,
            ))
            if stock is None:
                session.add(IngredientStock(
                    id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, ingredient_id=item.id,
                    opening_quantity=opening, stock_added=added, stock_used=used,
                    available_quantity=opening + added - used,
                    low_stock_limit=decimal(row.get('low_stock_limit')),
                ))

    return tenant.name, len(fixture.get('products', [])), len(fixture.get('ingredients', []))


def main() -> None:
    paths = sorted(FIXTURE_DIRECTORY.glob('*.json'))
    if not paths:
        raise RuntimeError(f'No seed fixtures found in {FIXTURE_DIRECTORY}')
    with SessionLocal() as session:
        imported = [import_fixture(session, load_fixture(path)) for path in paths]
        session.commit()
    for tenant_name, product_count, ingredient_count in imported:
        print(f'Imported {tenant_name}: {product_count} products, {ingredient_count} inventory items')


if __name__ == '__main__':
    main()
