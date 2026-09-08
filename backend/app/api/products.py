from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .deps import current_user, require_role
from ..database import get_session
from ..inventory_service import adjust_stock
from ..product_media import (
    MAX_PRODUCT_IMAGE_BYTES, product_media_path, save_product_image, validate_product_image_path,
)
from ..models import (
    AuditLog, Category, GlobalProduct, Inventory, Outlet, OutletProductMapping, Product, ProductVariant, User,
)
from ..schemas import (
    GlobalProductCreate, GlobalProductRead, GlobalProductUpdate, OutletProductMappingCreate,
    OutletProductMappingRead, OutletProductMappingUpdate, ProductCreate, ProductRead,
    ProductUpdate, ProductVariantCreate, ProductVariantRead, ProductFavouriteUpdate,
)

router = APIRouter(prefix='/api/products', tags=['products'])


def mapping_view(session: Session, mapping: OutletProductMapping, inventory: Inventory | None = None) -> OutletProductMappingRead:
    if inventory is None:
        inventory = inventory_for(session, mapping.tenant_id, mapping.outlet_id, mapping.legacy_product)
    master = mapping.global_product
    product = mapping.legacy_product
    return OutletProductMappingRead(
        id=mapping.id,
        global_product_id=master.id if master else None,
        legacy_product_id=mapping.legacy_product_id,
        code=master.code if master else product.code,
        name=mapping.outlet_specific_name or (master.name if master else product.name),
        category_name=master.category_name if master else (product.category_name or 'Uncategorised'),
        image_path=master.image_path if master else product.image_path,
        base_unit=master.base_unit if master else product.unit,
        default_gst=(mapping.tax_override if mapping.tax_override is not None else
                     (master.default_gst if master else product.gst_percent)),
        tax_override=mapping.tax_override,
        selling_price=mapping.selling_price,
        stock_quantity=inventory.available_quantity,
        low_stock_limit=inventory.low_stock_limit,
        favourite=mapping.favourite,
        kot_required=mapping.kot_required,
        is_available=mapping.is_available,
        is_active=mapping.is_active and (master is None or master.status == 'ACTIVE'),
        display_order=mapping.display_order,
        source='GLOBAL' if master else 'TENANT',
    )

@router.get('/master', response_model=list[GlobalProductRead])
def list_global_products(
    include_inactive: bool = Query(default=False),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[GlobalProduct]:
    query = select(GlobalProduct)
    if not include_inactive:
        query = query.where(GlobalProduct.status == 'ACTIVE')
    return list(session.scalars(query.order_by(GlobalProduct.category_name, GlobalProduct.name)).all())


@router.post('/master', response_model=GlobalProductRead, status_code=status.HTTP_201_CREATED)
def create_global_product(
    body: GlobalProductCreate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> GlobalProduct:
    product = GlobalProduct(id=str(uuid4()), **body.model_dump())
    product.code = product.code.upper()
    session.add(product)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Global product code already exists.') from error
    session.refresh(product)
    return product


@router.patch('/master/{product_id}', response_model=GlobalProductRead)
def update_global_product(
    product_id: str, body: GlobalProductUpdate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> GlobalProduct:
    product = session.get(GlobalProduct, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Global product not found.')
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    session.commit()
    session.refresh(product)
    return product


@router.get('/catalogue', response_model=list[OutletProductMappingRead])
def list_outlet_catalogue(
    outlet_id: str | None = Query(default=None, max_length=36),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[OutletProductMappingRead]:
    selected_outlet = resolve_outlet(session, user, outlet_id)
    mappings = session.scalars(
        select(OutletProductMapping)
        .options(selectinload(OutletProductMapping.global_product), selectinload(OutletProductMapping.legacy_product))
        .where(
            OutletProductMapping.tenant_id == user.tenant_id,
            OutletProductMapping.outlet_id == selected_outlet,
        )
        .order_by(OutletProductMapping.display_order, OutletProductMapping.id)
    ).all()
    inventories = inventories_for_products(session, user.tenant_id, selected_outlet,
                                          [row.legacy_product for row in mappings])
    rows = [mapping_view(session, row, inventories[row.legacy_product_id]) for row in mappings]
    session.commit()
    return rows


@router.post('/catalogue/local', response_model=OutletProductMappingRead, status_code=status.HTTP_201_CREATED)
def create_tenant_catalogue_product(
    body: ProductCreate,
    user: User = Depends(require_role('ADMIN', 'TENANT_ADMIN')),
    session: Session = Depends(get_session),
) -> OutletProductMappingRead:
    """Create a tenant-owned product and map it only to the signed-in outlet."""
    outlet_id = resolve_outlet(session, user)
    if not body.category_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Category is required.')
    category = session.scalar(select(Category).where(
        Category.id == body.category_id, Category.tenant_id == user.tenant_id,
    ))
    if category is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Category is not available for this tenant.')
    validate_product_image_path(user.tenant_id, outlet_id, body.image_path)
    values = body.model_dump(exclude={'shared_across_outlets', 'stock_quantity', 'low_stock_limit', 'outlet_id'})
    values['code'] = body.code.upper()
    product = Product(
        id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=outlet_id,
        stock_quantity=Decimal('0.000'), low_stock_limit=Decimal('0.000'), **values,
    )
    session.add(product)
    try:
        session.flush()
        mapping = OutletProductMapping(
            id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=outlet_id,
            global_product_id=None, legacy_product_id=product.id,
            selling_price=product.selling_price, favourite=product.is_favourite,
            kot_required=product.kot_required, is_available=product.is_available,
            is_active=product.is_active, display_order=0,
        )
        session.add(mapping)
        inventory = inventory_for(session, user.tenant_id, outlet_id, product)
        inventory.opening_quantity = body.stock_quantity
        inventory.available_quantity = body.stock_quantity
        inventory.low_stock_limit = body.low_stock_limit
        session.add(AuditLog(
            id=str(uuid4()), tenant_id=user.tenant_id, actor_user_id=user.id,
            action='CREATE', entity_type='TENANT_CATALOGUE_PRODUCT', entity_id=product.id, payload='{}',
        ))
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Product code already exists for this tenant.') from error
    mapping = session.scalar(select(OutletProductMapping).options(
        selectinload(OutletProductMapping.global_product),
        selectinload(OutletProductMapping.legacy_product).selectinload(Product.category),
    ).where(OutletProductMapping.id == mapping.id))
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Tenant product could not be reloaded.')
    return mapping_view(session, mapping)


@router.post('/catalogue/local/image')
def upload_tenant_product_image(
    file: UploadFile = File(...),
    user: User = Depends(require_role('ADMIN', 'TENANT_ADMIN')),
    session: Session = Depends(get_session),
) -> dict:
    outlet_id = resolve_outlet(session, user)
    return save_product_image(
        user.tenant_id, outlet_id, file.file.read(MAX_PRODUCT_IMAGE_BYTES + 1),
    )


@router.get('/media/{tenant_id}/{outlet_id}/{filename}')
def read_tenant_product_image(
    tenant_id: str, outlet_id: str, filename: str,
    session: Session = Depends(get_session),
):
    outlet = session.scalar(select(Outlet.id).where(
        Outlet.id == outlet_id, Outlet.tenant_id == tenant_id,
    ))
    if outlet is None:
        raise HTTPException(404, 'Product image not found.')
    path = product_media_path(tenant_id, outlet_id, filename)
    if not path.is_file():
        raise HTTPException(404, 'Product image not found.')
    return FileResponse(path, media_type='image/webp', headers={
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'public, max-age=31536000, immutable',
    })


@router.post('/catalogue/{global_product_id}', response_model=OutletProductMappingRead, status_code=status.HTTP_201_CREATED)
def map_global_product(
    global_product_id: str,
    body: OutletProductMappingCreate,
    user: User = Depends(require_role('ADMIN', 'TENANT_ADMIN')),
    session: Session = Depends(get_session),
) -> OutletProductMappingRead:
    outlet_id = resolve_outlet(session, user)
    master = session.get(GlobalProduct, global_product_id)
    if master is None or master.status != 'ACTIVE':
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Global product is not available.')
    existing = session.scalar(select(OutletProductMapping).where(
        OutletProductMapping.outlet_id == outlet_id,
        OutletProductMapping.global_product_id == master.id,
    ))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Product is already mapped to this outlet.')

    category_code = 'GLOBAL_' + ''.join(char if char.isalnum() else '_' for char in master.category_name.upper())[:64]
    category = session.scalar(select(Category).where(
        Category.tenant_id == user.tenant_id, Category.name == master.category_name
    ))
    if category is None:
        category = Category(
            id=str(uuid4()), tenant_id=user.tenant_id, code=category_code,
            name=master.category_name, image_path=master.image_path, display_order=999, is_active=True,
        )
        session.add(category)
        session.flush()
    legacy = session.scalar(select(Product).where(
        Product.tenant_id == user.tenant_id, Product.code == master.code
    ))
    if legacy is None:
        legacy = Product(
            id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=None,
            category_id=category.id, code=master.code, name=master.name,
            selling_price=body.selling_price, purchase_price=Decimal('0.00'),
            gst_percent=body.tax_override if body.tax_override is not None else master.default_gst,
            description=master.description, image_path=master.image_path, unit=master.base_unit,
            stock_quantity=Decimal('0.000'), low_stock_limit=Decimal('0.000'),
            is_favourite=body.favourite, kot_required=body.kot_required,
            is_available=body.is_available, is_active=body.is_active,
        )
        session.add(legacy)
        session.flush()
    mapping = OutletProductMapping(
        id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=outlet_id,
        global_product_id=master.id, legacy_product_id=legacy.id,
        **body.model_dump(exclude={'opening_stock', 'low_stock_limit'}),
    )
    session.add(mapping)
    inventory = inventory_for(session, user.tenant_id, outlet_id, legacy)
    inventory.opening_quantity = body.opening_stock
    inventory.available_quantity = body.opening_stock
    inventory.low_stock_limit = body.low_stock_limit
    session.commit()
    mapping = session.scalar(select(OutletProductMapping).options(
        selectinload(OutletProductMapping.global_product), selectinload(OutletProductMapping.legacy_product)
    ).where(OutletProductMapping.id == mapping.id))
    return mapping_view(session, mapping)


@router.patch('/catalogue/{mapping_id}', response_model=OutletProductMappingRead)
def update_outlet_mapping(
    mapping_id: str,
    body: OutletProductMappingUpdate,
    user: User = Depends(require_role('ADMIN', 'TENANT_ADMIN')),
    session: Session = Depends(get_session),
) -> OutletProductMappingRead:
    mapping = session.scalar(select(OutletProductMapping).options(
        selectinload(OutletProductMapping.global_product), selectinload(OutletProductMapping.legacy_product)
    ).where(
        OutletProductMapping.id == mapping_id,
        OutletProductMapping.tenant_id == user.tenant_id,
        OutletProductMapping.outlet_id == user.outlet_id,
    ))
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Outlet product mapping not found.')
    changes = body.model_dump(exclude_unset=True)
    if 'stock_quantity' in changes:
        requested = changes.pop('stock_quantity')
        expected = changes.pop('expected_stock_quantity', None)
        if requested is None or expected is None:
            raise HTTPException(status_code=422, detail='Stock and its previous value are required.')
        # Lock the same outlet ledger used by sales, purchases and void reversals.
        inventory = session.scalar(select(Inventory).where(
            Inventory.tenant_id == user.tenant_id,
            Inventory.outlet_id == user.outlet_id,
            Inventory.product_id == mapping.legacy_product_id,
        ).with_for_update())
        if inventory is None:
            raise HTTPException(status_code=409, detail='Stock ledger unavailable. Refresh the catalogue first.')
        if inventory.available_quantity != expected:
            raise HTTPException(status_code=409, detail='Stock changed since you opened it. Refresh and retry.')
        delta = requested - inventory.available_quantity
        if delta:
            adjust_stock(session, user=user, outlet_id=mapping.outlet_id,
                         product=mapping.legacy_product, quantity_delta=delta,
                         transaction_type='CORRECTION', reference_type='OUTLET_CATALOGUE',
                         reference_id=mapping.id,
                         notes=f'Catalogue stock correction: {expected} -> {requested}')
    elif 'expected_stock_quantity' in changes:
        raise HTTPException(status_code=422, detail='Stock quantity is required.')
    if 'low_stock_limit' in changes:
        low_stock_limit = changes.pop('low_stock_limit')
        if low_stock_limit is None:
            raise HTTPException(status_code=422, detail='Low stock limit cannot be empty.')
        inventory_for(session, user.tenant_id, mapping.outlet_id, mapping.legacy_product).low_stock_limit = low_stock_limit
    for field, value in changes.items():
        setattr(mapping, field, value)
    session.commit()
    return mapping_view(session, mapping)


@router.delete('/catalogue/{mapping_id}', status_code=status.HTTP_204_NO_CONTENT)
def unmap_outlet_product(
    mapping_id: str,
    user: User = Depends(require_role('ADMIN', 'TENANT_ADMIN')),
    session: Session = Depends(get_session),
) -> Response:
    mapping = session.scalar(select(OutletProductMapping).where(
        OutletProductMapping.id == mapping_id,
        OutletProductMapping.tenant_id == user.tenant_id,
        OutletProductMapping.outlet_id == user.outlet_id,
    ))
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Outlet product mapping not found.')
    session.delete(mapping)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def resolve_outlet(session: Session, user: User, requested_outlet_id: str | None = None) -> str:
    if requested_outlet_id and requested_outlet_id != user.outlet_id and user.role_code != 'ADMIN':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Cashiers can access only their assigned outlet.')
    outlet_id = requested_outlet_id or user.outlet_id
    if not outlet_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Select an outlet before managing products.')
    outlet = session.scalar(select(Outlet).where(Outlet.id == outlet_id, Outlet.tenant_id == user.tenant_id))
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Outlet not found for this tenant.')
    return outlet.id


def inventory_for(session: Session, tenant_id: str, outlet_id: str, product: Product) -> Inventory:
    inventory = session.scalar(select(Inventory).where(
        Inventory.tenant_id == tenant_id,
        Inventory.outlet_id == outlet_id,
        Inventory.product_id == product.id,
    ))
    if inventory is None:
        inventory = Inventory(
            id=str(uuid4()), tenant_id=tenant_id, outlet_id=outlet_id, product_id=product.id,
            opening_quantity=Decimal('0.000'), stock_added=Decimal('0.000'), stock_sold=Decimal('0.000'),
            available_quantity=Decimal('0.000'), low_stock_limit=product.low_stock_limit,
        )
        session.add(inventory)
        session.flush()
    return inventory


def inventories_for_products(session: Session, tenant_id: str, outlet_id: str,
                             products: list[Product]) -> dict[str, Inventory]:
    """Read one outlet ledger in a batch instead of a SELECT per product."""
    if not products:
        return {}
    product_ids = {product.id for product in products}
    inventories = {row.product_id: row for row in session.scalars(select(Inventory).where(
        Inventory.tenant_id == tenant_id, Inventory.outlet_id == outlet_id,
    )).all() if row.product_id in product_ids}
    missing = []
    for product in products:
        if product.id not in inventories:
            row = Inventory(id=str(uuid4()), tenant_id=tenant_id, outlet_id=outlet_id,
                            product_id=product.id, opening_quantity=Decimal('0.000'),
                            stock_added=Decimal('0.000'), stock_sold=Decimal('0.000'),
                            available_quantity=Decimal('0.000'), low_stock_limit=product.low_stock_limit)
            inventories[product.id] = row
            missing.append(row)
    if missing:
        session.add_all(missing)
        session.flush()
    return inventories

def product_view(
    product: Product, inventory: Inventory, mapping: OutletProductMapping | None = None
) -> ProductRead:
    return ProductRead(
        id=product.id, code=product.code,
        name=(mapping.outlet_specific_name or (mapping.global_product.name if mapping.global_product else product.name)) if mapping else product.name,
        selling_price=mapping.selling_price if mapping else product.selling_price,
        purchase_price=product.purchase_price,
        gst_percent=(mapping.tax_override if mapping.tax_override is not None else (mapping.global_product.default_gst if mapping.global_product else product.gst_percent)) if mapping else product.gst_percent,
        outlet_id=product.outlet_id,
        category_id=product.category_id, category_name=(mapping.global_product.category_name if mapping.global_product else product.category_name) if mapping else product.category_name,
        description=(mapping.global_product.description if mapping.global_product else product.description) if mapping else product.description,
        image_path=(mapping.global_product.image_path if mapping.global_product else product.image_path) if mapping else product.image_path,
        unit=(mapping.global_product.base_unit if mapping.global_product else product.unit) if mapping else product.unit,
        stock_quantity=inventory.available_quantity, low_stock_limit=inventory.low_stock_limit,
        is_favourite=mapping.favourite if mapping else product.is_favourite,
        kot_required=mapping.kot_required if mapping else product.kot_required,
        is_available=mapping.is_available if mapping else product.is_available,
        is_active=(mapping.is_active and (mapping.global_product is None or mapping.global_product.status == 'ACTIVE')) if mapping else product.is_active,
        shared_across_outlets=product.outlet_id is None,
        variants=[ProductVariantRead.model_validate(row) for row in product.variants],
    )


@router.get('', response_model=list[ProductRead])
def list_products(
    outlet_id: str | None = Query(default=None, max_length=36),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[ProductRead]:
    selected_outlet = resolve_outlet(session, user, outlet_id)
    products = session.scalars(
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.variants))
        .where(Product.tenant_id == user.tenant_id, or_(Product.outlet_id.is_(None), Product.outlet_id == selected_outlet))
        .order_by(Product.name)
    ).all()
    mappings = session.scalars(select(OutletProductMapping).options(
        selectinload(OutletProductMapping.global_product),
    ).where(
        OutletProductMapping.tenant_id == user.tenant_id,
        OutletProductMapping.outlet_id == selected_outlet,
    )).all()
    mapping_by_product = {mapping.legacy_product_id: mapping for mapping in mappings}
    if mappings:
        products = [product for product in products if product.id in mapping_by_product]
    inventories = inventories_for_products(session, user.tenant_id, selected_outlet, products)
    rows = [product_view(
        product, inventories[product.id],
        mapping_by_product.get(product.id),
    ) for product in products]
    session.commit()
    return rows


@router.post('', response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductCreate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> ProductRead:
    selected_outlet = resolve_outlet(session, user)
    if body.category_id:
        category = session.scalar(select(Category).where(Category.id == body.category_id, Category.tenant_id == user.tenant_id))
        if category is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Category is not available for this tenant.')
    values = body.model_dump(exclude={'shared_across_outlets', 'stock_quantity', 'low_stock_limit', 'outlet_id'})
    product = Product(
        id=str(uuid4()), tenant_id=user.tenant_id,
        outlet_id=None if body.shared_across_outlets else selected_outlet,
        stock_quantity=Decimal('0.000'), low_stock_limit=Decimal('0.000'), **values,
    )
    session.add(product)
    selected_inventory: Inventory | None = None
    try:
        session.flush()
        master = session.scalar(select(GlobalProduct).where(GlobalProduct.code == product.code.upper()))
        if master is None:
            master = GlobalProduct(
                id=str(uuid4()), code=product.code.upper(), name=product.name,
                description=product.description,
                category_name=product.category_name or 'Uncategorised', base_unit=product.unit,
                default_gst=product.gst_percent, image_path=product.image_path, status='ACTIVE',
            )
            session.add(master)
            session.flush()
        target_outlets = session.scalars(select(Outlet).where(Outlet.tenant_id == user.tenant_id)).all() if body.shared_across_outlets else [session.get(Outlet, selected_outlet)]
        for outlet in target_outlets:
            if outlet is None:
                continue
            inventory = Inventory(
                id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=outlet.id, product_id=product.id,
                opening_quantity=body.stock_quantity, stock_added=Decimal('0.000'), stock_sold=Decimal('0.000'),
                available_quantity=body.stock_quantity, low_stock_limit=body.low_stock_limit,
            )
            session.add(inventory)
            session.add(OutletProductMapping(
                id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=outlet.id,
                global_product_id=master.id, legacy_product_id=product.id,
                selling_price=product.selling_price, favourite=product.is_favourite,
                kot_required=product.kot_required, is_available=product.is_available,
                is_active=product.is_active, display_order=0,
            ))
            if outlet.id == selected_outlet:
                selected_inventory = inventory
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Product code already exists.') from error
    product = session.scalar(select(Product).options(selectinload(Product.category), selectinload(Product.variants)).where(Product.id == product.id))
    if product is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Product could not be reloaded.')
    if selected_inventory is None:
        selected_inventory = inventory_for(session, user.tenant_id, selected_outlet, product)
        session.commit()
    mapping = session.scalar(select(OutletProductMapping).where(
        OutletProductMapping.outlet_id == selected_outlet,
        OutletProductMapping.legacy_product_id == product.id,
    ))
    return product_view(product, selected_inventory, mapping)


@router.post('/{product_id}/variants', response_model=ProductVariantRead, status_code=status.HTTP_201_CREATED)
def create_variant(
    product_id: str,
    body: ProductVariantCreate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> ProductVariant:
    product = session.scalar(select(Product).where(
        Product.id == product_id, Product.tenant_id == user.tenant_id,
        or_(Product.outlet_id.is_(None), Product.outlet_id == user.outlet_id),
    ))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
    variant = ProductVariant(id=str(uuid4()), tenant_id=user.tenant_id, product_id=product.id, is_active=True, **body.model_dump())
    session.add(variant)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This variant name already exists for the product.') from error
    session.refresh(variant)
    return variant


@router.patch('/{product_id}/favourite', response_model=ProductRead)
def update_product_favourite(
    product_id: str,
    body: ProductFavouriteUpdate,
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> ProductRead:
    outlet_id = resolve_outlet(session, user)
    mapping = session.scalar(select(OutletProductMapping).options(
        selectinload(OutletProductMapping.global_product),
        selectinload(OutletProductMapping.legacy_product),
    ).where(
        OutletProductMapping.tenant_id == user.tenant_id,
        OutletProductMapping.outlet_id == outlet_id,
        OutletProductMapping.legacy_product_id == product_id,
    ))
    if mapping is None:
        raise HTTPException(status_code=404, detail='Product is not mapped to this outlet.')
    mapping.favourite = body.is_favourite
    inventory = inventory_for(session, user.tenant_id, outlet_id, mapping.legacy_product)
    session.commit()
    return product_view(mapping.legacy_product, inventory, mapping)


@router.patch('/{product_id}', response_model=ProductRead)
def update_product(
    product_id: str,
    body: ProductUpdate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> ProductRead:
    selected_outlet = resolve_outlet(session, user)
    product = session.scalar(
        select(Product).options(selectinload(Product.category), selectinload(Product.variants)).where(
            Product.id == product_id, Product.tenant_id == user.tenant_id,
            or_(Product.outlet_id.is_(None), Product.outlet_id == selected_outlet),
        )
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Product not found.')
    if body.category_id:
        category = session.scalar(select(Category).where(Category.id == body.category_id, Category.tenant_id == user.tenant_id))
        if category is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Category is not available for this tenant.')
        product.category = category
    supplied = body.model_dump(exclude_unset=True)
    requested_stock = supplied.pop('stock_quantity', None)
    requested_limit = supplied.pop('low_stock_limit', None)
    shared = supplied.pop('shared_across_outlets', None)
    supplied.pop('outlet_id', None)
    mapping = session.scalar(select(OutletProductMapping).where(
        OutletProductMapping.tenant_id == user.tenant_id,
        OutletProductMapping.outlet_id == selected_outlet,
        OutletProductMapping.legacy_product_id == product.id,
    ))
    outlet_fields = {
        'selling_price': 'selling_price', 'is_favourite': 'favourite',
        'kot_required': 'kot_required', 'is_available': 'is_available',
        'is_active': 'is_active',
    }
    if mapping is not None:
        for source, target in outlet_fields.items():
            if source in supplied:
                setattr(mapping, target, supplied.pop(source))
    for field, value in supplied.items():
        setattr(product, field, value)
    if shared is not None:
        product.outlet_id = None if shared else selected_outlet
    inventory = inventory_for(session, user.tenant_id, selected_outlet, product)
    if requested_stock is not None:
        inventory.available_quantity = requested_stock
    if requested_limit is not None:
        inventory.low_stock_limit = requested_limit
    if shared is True:
        for outlet in session.scalars(select(Outlet).where(Outlet.tenant_id == user.tenant_id)).all():
            inventory_for(session, user.tenant_id, outlet.id, product)
    session.commit()
    return product_view(product, inventory, mapping)
