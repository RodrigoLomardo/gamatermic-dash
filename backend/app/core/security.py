import hashlib
import hmac
import re
import secrets
import uuid
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.errors import Unauthorized, Unprocessable

_ph = PasswordHasher()  # argon2id (defaults >= OWASP minimo)
_DUMMY_HASH = _ph.hash("dummy-password-for-timing")

COMMON_PASSWORDS = {
    "123456789012", "password1234", "senha1234567", "qwertyuiop12", "administrador", "gamatermic123",
    "gamatermic2025", "gamatermic2026", "mudar123456", "123456123456", "abcdefghijkl", "changeme1234",
}


def _pw(raw: str) -> str:
    return raw + get_settings().password_pepper


def hash_password(raw: str) -> str:
    return _ph.hash(_pw(raw))


def verify_password(raw: str, hashed: str | None) -> bool:
    """Tempo similar para usuario inexistente (hash dummy)."""
    try:
        return _ph.verify(hashed or _DUMMY_HASH, _pw(raw)) and hashed is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


@lru_cache
def _blocklist() -> set[str]:
    p = Path(__file__).parent / "common_passwords.txt"
    base = set(COMMON_PASSWORDS)
    if p.exists():
        base |= {ln.strip().lower() for ln in p.read_text().splitlines() if ln.strip()}
    return base


def validate_password_policy(pw: str, *, email: str | None = None) -> None:
    """NIST 800-63B: tamanho minimo 12, sem regras de composicao, bloqueio de senhas comuns."""
    if len(pw) < 12:
        raise Unprocessable("A senha deve ter ao menos 12 caracteres.", code="weak_password")
    if len(pw) > 128:
        raise Unprocessable("A senha é longa demais.", code="weak_password")
    low = pw.lower()
    if low in _blocklist() or len(set(low)) < 5 or re.fullmatch(r"(.)\1+", low):
        raise Unprocessable("Senha muito comum ou previsível.", code="weak_password")
    if email and email.split("@")[0].lower() in low and len(email.split("@")[0]) >= 4:
        raise Unprocessable("A senha não pode conter o seu e-mail.", code="weak_password")


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def issue_jwt(*, sub: str, typ: str, ttl_seconds: int, extra: dict | None = None) -> tuple[str, str]:
    s = get_settings()
    now = utcnow()
    jti = str(uuid.uuid4())
    payload = {
        "sub": sub, "typ": typ, "jti": jti, "iss": s.jwt_issuer, "aud": "gamatermic-dash",
        "iat": int(now.timestamp()), "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        **(extra or {}),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256", headers={"kid": s.jwt_kid}), jti


def decode_jwt(token: str, *, expected_typ: str | None = None) -> dict:
    s = get_settings()
    try:
        payload = jwt.decode(
            token, s.jwt_secret, algorithms=["HS256"], audience="gamatermic-dash", issuer=s.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.PyJWTError as e:
        raise Unauthorized("Token inválido ou expirado.", code="invalid_token") from e
    if expected_typ and payload.get("typ") != expected_typ:
        raise Unauthorized("Tipo de token incorreto.", code="invalid_token")
    return payload


def user_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O/1/I
    c = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{c[:4]}-{c[4:]}"
