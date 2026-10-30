import base64

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().fernet_key.encode()
    try:
        return Fernet(key)
    except ValueError:
        return Fernet(base64.urlsafe_b64encode(base64.b64decode(key)[:32].ljust(32, b"0")))


def encrypt(plain: str) -> bytes:
    return _fernet().encrypt(plain.encode())


def decrypt(blob: bytes) -> str:
    return _fernet().decrypt(blob).decode()
