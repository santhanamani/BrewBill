import base64
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .database import settings


def _private_key() -> Ed25519PrivateKey:
    if not settings.license_private_key:
        raise RuntimeError('LICENSE_PRIVATE_KEY is not configured.')
    pem = base64.b64decode(settings.license_private_key)
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError('LICENSE_PRIVATE_KEY must be an Ed25519 private key.')
    return key


def public_key_pem() -> str:
    if not settings.license_public_key:
        raise RuntimeError('LICENSE_PUBLIC_KEY is not configured.')
    return base64.b64decode(settings.license_public_key).decode('ascii')


def sign_payload(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, separators=(',', ':'), ensure_ascii=True, sort_keys=True).encode('utf-8')
    return base64.b64encode(_private_key().sign(serialized)).decode('ascii')
