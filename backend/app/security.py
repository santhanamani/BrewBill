from datetime import UTC, datetime, timedelta
from uuid import uuid4
import base64
import hashlib
import hmac
import secrets
import struct
import time
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from passlib.context import CryptContext
from .database import settings

passwords = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(value: str) -> str:
    return passwords.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    return passwords.verify(value, hashed)


def create_token(subject: str, tenant_id: str, kind: str, expires: timedelta) -> tuple[str, str]:
    token_id = uuid4().hex
    payload = {"sub": subject, "tenant_id": tenant_id, "type": kind, "jti": token_id, "exp": datetime.now(UTC) + expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), token_id


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unexpected token type")
    return payload


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def _mfa_cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode('utf-8')).digest())
    return Fernet(key)


def encrypt_mfa_secret(secret: str) -> str:
    return _mfa_cipher().encrypt(secret.encode('ascii')).decode('ascii')


def decrypt_mfa_secret(value: str) -> str:
    try:
        return _mfa_cipher().decrypt(value.encode('ascii')).decode('ascii')
    except InvalidToken as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='MFA configuration is invalid.') from error


def verify_totp(secret: str, code: str, at_time: int | None = None) -> bool:
    if len(code) != 6 or not code.isdigit():
        return False
    now = at_time if at_time is not None else int(time.time())
    padded = secret + '=' * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    for offset in (-1, 0, 1):
        digest = hmac.new(key, struct.pack('>Q', (now // 30) + offset), hashlib.sha1).digest()
        start = digest[-1] & 0x0F
        number = (struct.unpack('>I', digest[start:start + 4])[0] & 0x7FFFFFFF) % 1_000_000
        if hmac.compare_digest(f'{number:06d}', code):
            return True
    return False
