import uuid
from collections.abc import AsyncIterator, Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal, load_user_principal
from app.core.db import get_sessionmaker
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_jwt
from app.modules.iam.models import User


def policy(fn: Callable) -> Callable:
    """Marca dependencias que declaram politica de seguranca (varridas por teste)."""
    fn.__gama_policy__ = True  # type: ignore[attr-defined]
    return fn


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as s:
        yield s


def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        raise Unauthorized("Credenciais ausentes.", code="not_authenticated")
    return h[7:].strip()


async def _user_principal(request: Request, session: AsyncSession, allow_must_change: bool) -> Principal:
    payload = decode_jwt(_bearer(request), expected_typ="user")  # rejeita typ=device
    user = await session.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.status in ("disabled",) or user.anonymized_at:
        raise Unauthorized("Usuário inválido.", code="invalid_token")
    p = await load_user_principal(session, user)
    p.session_id = payload.get("sid")
    if user.must_change_password and not allow_must_change:
        raise Forbidden("Troca de senha obrigatória.", code="password_change_required")
    request.state.principal = p
    return p


@policy
async def require_user(request: Request, session: AsyncSession = Depends(get_session)) -> Principal:
    """Qualquer usuario autenticado (precisa ter trocado a senha temporaria)."""
    return await _user_principal(request, session, allow_must_change=False)


@policy
async def require_user_allow_pwchange(request: Request, session: AsyncSession = Depends(get_session)) -> Principal:
    return await _user_principal(request, session, allow_must_change=True)


def require_permission(*perms: str, any_of: bool = False) -> Callable:
    """Exige permissao global (qualquer escopo). Escopo por recurso e checado no service."""

    @policy
    async def dep(principal: Principal = Depends(require_user)) -> Principal:
        ok = any(principal.has(x) for x in perms) if any_of else all(principal.has(x) for x in perms)
        if not ok:
            raise Forbidden("Sem permissão.", code="forbidden")
        return principal

    return dep


@policy
async def public() -> None:
    """Rota publica por design (login, pareamento)."""
    return None


@policy
async def require_device(request: Request, session: AsyncSession = Depends(get_session)) -> Principal:
    from app.modules.devices.service import device_principal_from_payload

    payload = decode_jwt(_bearer(request), expected_typ="device")  # rejeita typ=user
    p = await device_principal_from_payload(session, payload)
    request.state.principal = p
    return p


@policy
async def require_display(request: Request, session: AsyncSession = Depends(get_session)) -> Principal:
    """/display/*: dispositivo (token typ=device) ou usuario com dashboard:view (modo preview)."""
    token = _bearer(request)
    payload = decode_jwt(token)
    if payload.get("typ") == "device":
        from app.modules.devices.service import device_principal_from_payload

        p = await device_principal_from_payload(session, payload)
    else:
        p = await _user_principal(request, session, allow_must_change=False)
        if not p.has("dashboard:view"):
            raise Forbidden("Sem permissão.")
    request.state.principal = p
    return p
