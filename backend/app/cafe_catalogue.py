"""Opt-in, idempotent global café catalogue and product-image repair.

Run from backend: python -m app.cafe_catalogue (preview), then --apply.
Never changes outlet mappings, prices, taxes, stock or favourites.
"""
import argparse
from datetime import datetime, UTC
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import unicodedata
from uuid import uuid4

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .media_storage import data_root, media_file_path
from .models import GlobalProduct, Product

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = PROJECT_ROOT / 'backend/seed_data/catalogues/cafe.json'
ASSETS = PROJECT_ROOT / 'public/assets/images'


def name_key(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if c.isalnum())


def load_catalogue(path: Path = MANIFEST) -> list[dict]:
    rows = json.loads(path.read_text(encoding='utf-8'))
    codes, names, images = set(), set(), set()
    for row in rows:
        if not re.fullmatch(r'[A-Z][A-Z0-9_]+', row['code']):
            raise ValueError('Invalid catalogue code')
        expected = f"products/cafe/{row['code'].lower().replace('_', '-')}.png"
        if row['image_path'] != expected:
            raise ValueError(f"Unexpected product image path: {row['code']}")
        key = name_key(row['name'])
        if row['code'] in codes or key in names or expected in images:
            raise ValueError(f"Duplicate catalogue definition: {row['code']}")
        codes.add(row['code']); names.add(key); images.add(expected)
    return rows


def is_default_image(value: str | None, row: dict) -> bool:
    path = (value or '').replace('\\', '/').removeprefix('/').removeprefix('assets/images/')
    allowed = {'', 'products/placeholder.svg'}
    if row['legacy']:
        allowed.update(f"products/photos/{row['legacy']}.{ext}" for ext in ('jpg', 'jpeg', 'png'))
    return path in allowed


def sync_catalogue(session: Session, rows: list[dict], ready_codes: set[str]) -> dict:
    """Stage changes only. Caller owns transaction and backup/commit policy."""
    masters = list(session.scalars(select(GlobalProduct)))
    by_code = {p.code.upper(): p for p in masters}
    by_name = {name_key(p.name): p for p in masters}
    report = {'created': [], 'images_updated': [], 'custom_images_preserved': [], 'name_conflicts': [],
              'pending_images': [r['code'] for r in rows if r['code'] not in ready_codes]}
    row_by_code = {row['code']: row for row in rows}
    for row in rows:
        product = by_code.get(row['code'])
        if product is None:
            if name_key(row['name']) in by_name:
                report['name_conflicts'].append(row['code'])
                continue
            product = GlobalProduct(
                id=str(uuid4()), code=row['code'], name=row['name'],
                category_name=row['category'], base_unit='pcs',
                default_gst=Decimal('5.00'),
                image_path=row['image_path'] if row['code'] in ready_codes else None, status='ACTIVE',
            )
            session.add(product)
            by_code[row['code']] = product
            by_name[name_key(row['name'])] = product
            report['created'].append({'id': product.id, 'code': product.code})
        elif row['code'] in ready_codes and product.image_path != row['image_path']:
            if is_default_image(product.image_path, row):
                report['images_updated'].append({'table': 'global_products', 'id': product.id,
                    'code': product.code, 'before': product.image_path, 'after': row['image_path']})
                product.image_path = row['image_path']
            else:
                report['custom_images_preserved'].append(product.code)
    # Repair legacy demo images too (unmapped catalogue/held-order consumers).
    # Only exact known bundled paths are touched; tenant uploads stay intact.
    for product in session.scalars(select(Product)):
        row = row_by_code.get(product.code.upper())
        if row and row['code'] in ready_codes and product.image_path != row['image_path'] and is_default_image(product.image_path, row):
            report['images_updated'].append({'table': 'products', 'id': product.id,
                'code': product.code, 'before': product.image_path, 'after': row['image_path']})
            product.image_path = row['image_path']
    return report


def validate_assets(rows: list[dict], source_root: Path = ASSETS) -> dict:
    missing, invalid, hashes = [], [], {}
    for row in rows:
        source = source_root / row['image_path']
        if not source.is_file():
            missing.append(row['code']); continue
        try:
            with Image.open(source) as image:
                image.load()
                if image.format != 'PNG' or 'A' not in image.getbands() or not (0 <= image.getchannel('A').getextrema()[0] < image.getchannel('A').getextrema()[1]):
                    invalid.append(row['code'])
        except (OSError, ValueError):
            invalid.append(row['code'])
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest in hashes:
            invalid.append(f"Duplicate image: {row['code']} / {hashes[digest]}")
        hashes[digest] = row['code']
    return {'missing': missing, 'invalid': invalid, 'unique_images': len(hashes)}


def install_assets(rows: list[dict]) -> None:
    for row in rows:
        source = ASSETS / row['image_path']
        target = media_file_path(row['image_path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise ValueError(f'Refusing to overwrite an existing custom asset: {target}')
        else:
            shutil.copy2(source, target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Install validated images and commit global definitions')
    parser.add_argument('--allow-pending-images', action='store_true',
                        help='Keep existing images; new products without a ready photo use the standard placeholder')
    args = parser.parse_args()
    rows = load_catalogue()
    validation = validate_assets(rows)
    if validation['invalid'] or (validation['missing'] and not args.allow_pending_images):
        print(json.dumps(validation, indent=2))
        raise RuntimeError('Missing/invalid product images. Explicit --allow-pending-images permits missing images only.')
    ready_codes = {r['code'] for r in rows} - set(validation['missing'])
    with SessionLocal() as session:
        report = sync_catalogue(session, rows, ready_codes)
        print(json.dumps({'apply': args.apply, 'catalogue_size': len(rows), 'media_root': str(data_root()),
            'assets': validation, **report}, indent=2))
        if not args.apply:
            session.rollback(); return
        install_assets([r for r in rows if r['code'] in ready_codes])
        backup_dir = PROJECT_ROOT / '.codex-runtime/catalogue-backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"cafe-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.json"
        backup.write_text(json.dumps(report, indent=2), encoding='utf-8')
        session.commit()
        print(f'Committed. Change manifest: {backup}')


if __name__ == '__main__':
    main()
