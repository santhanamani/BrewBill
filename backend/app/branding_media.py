"""Validated tenant-scoped branding. Re-encode pixels, never overwrite assets."""
from io import BytesIO
from pathlib import Path
import re
import warnings
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from .media_storage import data_root

MEDIA_ROOT = data_root() / 'tenant-branding'
LIMITS = {'logo': 2 * 1024 * 1024, 'cover': 5 * 1024 * 1024}
PREFIX = '/api/platform/tenants/'


def tenant_directory(tenant_id: str) -> Path:
    return MEDIA_ROOT / str(UUID(tenant_id))


def save_image(tenant_id: str, kind: str, content: bytes) -> dict:
    if not content or len(content) > LIMITS[kind]:
        raise HTTPException(413, f'{kind.title()} must be between 1 byte and {LIMITS[kind] // (1024 * 1024)} MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as original:
                if original.format not in {'PNG', 'JPEG', 'WEBP'}:
                    raise ValueError('Unsupported format')
                if original.width * original.height > 20_000_000 or max(original.size) > 8000:
                    raise ValueError('Image dimensions are too large')
                if min(original.size) < 64 or getattr(original, 'n_frames', 1) != 1:
                    raise ValueError('Use a still image of at least 64 x 64 pixels')
                original.load()
                oriented = ImageOps.exif_transpose(original)
                oriented.thumbnail((1024, 1024) if kind == 'logo' else (2400, 1600))
                clean = Image.new('RGBA', oriented.size)
                clean.paste(oriented.convert('RGBA'))
                encoded = BytesIO()
                clean.save(encoded, format='WEBP', quality=90)
                width, height = clean.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise HTTPException(422, 'Use a valid non-animated PNG, JPG or WebP (64-8000 px, at most 20 megapixels).') from exc
    directory = tenant_directory(tenant_id)
    directory.mkdir(parents=True, exist_ok=True)
    name = f'{kind}-{uuid4().hex}.webp'
    with (directory / name).open('xb') as target:
        target.write(encoded.getvalue())
    return {
        'path': f'tenant-branding/{tenant_id}/{name}',
        'url': f'{PREFIX}{tenant_id}/media/{name}',
        'width': width,
        'height': height,
    }


def media_path(tenant_id: str, filename: str) -> Path:
    if not re.fullmatch(r'(logo|cover)-[0-9a-f]{32}\.webp', filename):
        raise HTTPException(404, 'Brand image not found.')
    return tenant_directory(tenant_id) / filename


def validate_branding_url(tenant_id: str, value: str | None) -> None:
    if not value:
        return
    relative_prefix = f'tenant-branding/{tenant_id}/'
    if value.startswith('tenant-branding/'):
        if not value.startswith(relative_prefix) or not media_path(tenant_id, value[len(relative_prefix):]).is_file():
            raise HTTPException(422, 'Choose an image uploaded for this tenant only.')
    elif value.startswith(PREFIX):
        expected = f'{PREFIX}{tenant_id}/media/'
        if not value.startswith(expected) or not media_path(tenant_id, value[len(expected):]).is_file():
            raise HTTPException(422, 'Choose an image uploaded for this tenant only.')
    elif value.startswith('/'):
        if not value.startswith('/assets/images/'):
            raise HTTPException(422, 'Invalid branding image path.')
    elif value.startswith(('brand/', 'products/', 'categories/', 'inventory/')):
        return
    else:
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(422, 'Use an uploaded image or a valid HTTPS image URL.')
        if '/platform/tenants/' in parsed.path:
            raise HTTPException(422, 'Use the tenant-scoped upload path for uploaded images.')
