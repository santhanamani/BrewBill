"""Copy legacy/bundled images into BREWBILL_DATA_PATH and normalise DB paths."""

from pathlib import Path
import re
import shutil

from app.database import SessionLocal
from app.media_storage import data_root
from app.models import Category, GlobalProduct, Ingredient, Product, Tenant


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


def copy_tree(source: Path, destination: Path) -> int:
    if not source.is_dir():
        return 0
    copied = 0
    for source_file in source.rglob('*'):
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or source_file.stat().st_mtime_ns > target.stat().st_mtime_ns:
            shutil.copy2(source_file, target)
            copied += 1
    return copied


def normalise_static_path(value: str | None) -> str | None:
    if not value:
        return value
    return re.sub(r'^/?assets/images/', '', value.replace('\\', '/'))


def product_upload_path(value: str | None) -> str | None:
    value = normalise_static_path(value)
    if not value:
        return value
    match = re.fullmatch(r'/api/products/media/([^/]+)/([^/]+)/(product-[0-9a-f]{32}\.webp)', value)
    return f'products/tenant-uploads/{match.group(1)}/{match.group(2)}/{match.group(3)}' if match else value


def branding_path(tenant_id: str, value: str | None) -> str | None:
    value = normalise_static_path(value)
    if not value:
        return value
    match = re.fullmatch(rf'/api/platform/tenants/{re.escape(tenant_id)}/media/((?:logo|cover)-[0-9a-f]{{32}}\.webp)', value)
    return f'tenant-branding/{tenant_id}/{match.group(1)}' if match else value


def migrate_database() -> int:
    changed = 0
    with SessionLocal() as session:
        for model in (GlobalProduct, Product, Category, Ingredient):
            for row in session.query(model).all():
                updated = product_upload_path(row.image_path)
                if updated != row.image_path:
                    row.image_path = updated
                    changed += 1
        for tenant in session.query(Tenant).all():
            for field in ('logo_url', 'cover_image_url'):
                current = getattr(tenant, field)
                updated = branding_path(tenant.id, current)
                if updated != current:
                    setattr(tenant, field, updated)
                    changed += 1
        session.commit()
    return changed


def main() -> None:
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    copied = copy_tree(PROJECT_ROOT / 'public' / 'assets' / 'images', root)
    copied += copy_tree(
        BACKEND_ROOT / 'storage' / 'tenant-products',
        root / 'products' / 'tenant-uploads',
    )
    copied += copy_tree(
        BACKEND_ROOT / 'storage' / 'tenant-branding',
        root / 'tenant-branding',
    )
    changed = migrate_database()
    print(f'BREWBILL_DATA_PATH={root}')
    print(f'Copied/updated files: {copied}')
    print(f'Normalised database paths: {changed}')


if __name__ == '__main__':
    main()
