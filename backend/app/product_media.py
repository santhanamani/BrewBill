"""Validated tenant/outlet-scoped product image storage."""

from io import BytesIO
from pathlib import Path
import re
import warnings
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from .media_storage import data_root


MEDIA_ROOT = data_root() / 'products' / 'tenant-uploads'
MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
PREFIX = '/api/products/media/'


def product_directory(tenant_id: str, outlet_id: str) -> Path:
    return MEDIA_ROOT / str(UUID(tenant_id)) / str(UUID(outlet_id))


def save_product_image(tenant_id: str, outlet_id: str, content: bytes) -> dict:
    if not content or len(content) > MAX_PRODUCT_IMAGE_BYTES:
        raise HTTPException(413, 'Product image must be between 1 byte and 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as original:
                if original.format not in {'PNG', 'JPEG', 'WEBP'}:
                    raise ValueError('Unsupported image format')
                if original.width * original.height > 20_000_000 or max(original.size) > 8000:
                    raise ValueError('Image dimensions are too large')
                if min(original.size) < 64 or getattr(original, 'n_frames', 1) != 1:
                    raise ValueError('Image is too small or animated')
                original.load()
                oriented = ImageOps.exif_transpose(original)
                oriented.thumbnail((1600, 1600))
                clean = Image.new('RGB', oriented.size, '#ffffff')
                if 'A' in oriented.getbands():
                    clean.paste(oriented.convert('RGBA'), mask=oriented.convert('RGBA').getchannel('A'))
                else:
                    clean.paste(oriented.convert('RGB'))
                encoded = BytesIO()
                clean.save(encoded, format='WEBP', quality=88, method=6)
                width, height = clean.size
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise HTTPException(
            422,
            'Choose a valid still PNG, JPG or WebP image (64-8000 px, at most 20 megapixels).',
        ) from exc

    directory = product_directory(tenant_id, outlet_id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f'product-{uuid4().hex}.webp'
    with (directory / filename).open('xb') as target:
        target.write(encoded.getvalue())
    return {
        'path': f'products/tenant-uploads/{tenant_id}/{outlet_id}/{filename}',
        'url': f'{PREFIX}{tenant_id}/{outlet_id}/{filename}',
        'width': width,
        'height': height,
    }


def product_media_path(tenant_id: str, outlet_id: str, filename: str) -> Path:
    if not re.fullmatch(r'product-[0-9a-f]{32}\.webp', filename):
        raise HTTPException(404, 'Product image not found.')
    return product_directory(tenant_id, outlet_id) / filename


def validate_product_image_path(tenant_id: str, outlet_id: str, value: str | None) -> None:
    if not value:
        return
    expected = f'{PREFIX}{tenant_id}/{outlet_id}/'
    if value.startswith(PREFIX):
        if not value.startswith(expected):
            raise HTTPException(422, 'Choose an image uploaded for this tenant and outlet.')
        path = product_media_path(tenant_id, outlet_id, value[len(expected):])
        if not path.is_file():
            raise HTTPException(422, 'Uploaded product image was not found.')
        return
    relative_prefix = f'products/tenant-uploads/{tenant_id}/{outlet_id}/'
    if value.startswith('products/tenant-uploads/'):
        if not value.startswith(relative_prefix):
            raise HTTPException(422, 'Choose an image uploaded for this tenant and outlet.')
        path = product_media_path(tenant_id, outlet_id, value[len(relative_prefix):])
        if not path.is_file():
            raise HTTPException(422, 'Uploaded product image was not found.')
        return
    if value.startswith('/assets/images/products/'):
        value = value[len('/assets/images/') :]
    if re.fullmatch(r'products/[A-Za-z0-9._/-]+\.(?:svg|png|jpe?g|webp)', value) and '..' not in value:
        return
    parsed = urlsplit(value)
    if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password:
        return
    raise HTTPException(422, 'Use an uploaded product image, bundled product image, or valid HTTPS image URL.')
