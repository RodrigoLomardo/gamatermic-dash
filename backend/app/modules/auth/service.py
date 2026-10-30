import uuid
from datetime import timedelta

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal, load_user_principal
from app.core.config import get_settings
from app.core.db import utcnow
from app.core.errors import Forbidden, TooManyRequests, Unauthorized
from app.core.rate_limit import client_ip, hit
from app.core.security import (
    hash_password,
    hash_token,
    issue_jwt,
    needs_rehash,
    new_opaque_token,
    validate_password_policy,
    verify_password,
)
from app.modules.audit import service as audit
from app.modules.auth import repository as repo
from app.modules.auth.schemas import MeOut, TokenOut
from app.modules.iam.models import RefreshToken, User


def me_out(user: User, p: Principal) -> MeOut:
    return MeOut(
        id=user.id, email=user.email, full_name=user.full_name, must_change_password=user.must_change_password,
        roles=p.role_names, permissions=p.perms,
    )


async def _issue(session: AsyncSession, user: User, request: Request, *, family_id=None, parent_id=None,
                 absolute=None) -> tuple[str, RefreshToken]:
    s = get_settings()
    now = utcnow()
    raw = new_opaque_token()
    absolute = absolute or now + timedelta(days=s.refresh_absolute_days)
    row = RefreshToken(
        user_id=user.id, family_id=family_id or uuid.uuid4(), parent_id=parent_id, token_hash=hash_token(raw),
        expires_at=min(now + timedelta(days=s.refresh_idle_days), absolute), absolute_expires_at=absolute,
        ip=client_ip(request), user_agent=request.headers.get("user-agent", "")[:300],
    )
    session.add(row)
    await session.flush()
    return raw, row


async def _access(session: AsyncSession, user: User, family_id: uuid.UUID) -> TokenOut:
    s = get_settings()
    p = await load_user_principal(session, user)
    token, _ = issue_jwt(sub=str(user.id), typ="user", ttl_seconds=s.access_ttl_seconds, extra={"sid": str(family_id)})
    return TokenOut(access_token=token, expires_in=s.access_ttl_seconds, user=me_out(user, p))


async def login(session: AsyncSession, request: Request, email: str, password: str) -> tuple[TokenOut, str]:
    s = get_settings()
    ip = client_ip(request)
    hit(f"login:ip:{ip}", 10, 60)
    hit(f"login:acct:{email.lower()}", 20, 60)
    now = utcnow()
    user = await repo.user_by_email(session, email)
    ok = verify_password(password, user.password_hash if user else None)

    if user is not None and user.locked_until and user.locked_until > now:
        await audit.record(session, "auth.login.failed", request=request, actor_type="user", actor_id=user.id,
                           actor_label=user.email, outcome="denied", metadata={"reason": "locked"})
        await session.commit()
        raise TooManyRequests("Conta temporariamente bloqueada. Tente mais tarde.", code="account_locked",
                              extra={"retry_after": int((user.locked_until - now).total_seconds())})

    if not ok or user is None or user.status in ("disabled", "invited") or user.anonymized_at:
        if user is not None:
            user.failed_login_count += 1
            reason = "bad_password"
            if user.failed_login_count >= s.login_max_failures:
                # progressivo: 15, 30, 45... min
                mult = user.failed_login_count // s.login_max_failures
                user.locked_until = now + timedelta(minutes=s.login_lock_minutes * mult)
                reason = "locked"
                await audit.record(session, "auth.login.locked", request=request, actor_type="user", actor_id=user.id,
                                   actor_label=user.email, outcome="denied")
            await audit.record(session, "auth.login.failed", request=request, actor_type="user", actor_id=user.id,
                               actor_label=user.email, outcome="denied", metadata={"reason": reason})
        else:
            await audit.record(session, "auth.login.failed", request=request, actor_type="user", actor_label=email.lower(),
                               outcome="denied", metadata={"reason": "unknown_user"})
        await session.commit()
        raise Unauthorized("E-mail ou senha incorretos.", code="invalid_credentials")

    if needs_rehash(user.password_hash or ""):
        user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    raw, row = await _issue(session, user, request)
    out = await _access(session, user, row.family_id)
    await audit.record(session, "auth.login.success", request=request, actor_type="user", actor_id=user.id,
                       actor_label=user.email)
    await session.commit()
    return out, raw


async def refresh(session: AsyncSession, request: Request, raw: str | None) -> tuple[TokenOut, str]:
    s = get_settings()
    if not raw:
        raise Unauthorized("Sessão ausente.", code="no_session")
    hit(f"refresh:ip:{client_ip(request)}", 60, 60)
    now = utcnow()
    tok = await repo.token_by_hash(session, hash_token(raw))
    if tok is None:
        raise Unauthorized("Sessão inválida.", code="invalid_session")
    if tok.revoked_at is not None:
        raise Unauthorized("Sessão encerrada.", code="invalid_session")
    if tok.expires_at <= now or tok.absolute_expires_at <= now:
        raise Unauthorized("Sessão expirada.", code="session_expired")
    if tok.used_at is not None:
        # reuso: dentro da janela de tolerancia (abas concorrentes) emite irmao; fora dela, revoga a familia
        if (now - tok.used_at).total_seconds() > s.refresh_reuse_window_seconds:
            await repo.revoke_family(session, tok.family_id, "reuse_detected", now)
            await audit.record(session, "auth.refresh.reuse_detected", request=request, actor_type="user",
                               actor_id=tok.user_id, outcome="denied", metadata={"family_id": str(tok.family_id)})
            await session.commit()
            raise Unauthorized("Sessão inválida.", code="reuse_detected")
    user = await session.get(User, tok.user_id)
    if user is None or user.status == "disabled" or user.anonymized_at:
        raise Unauthorized("Usuário inválido.", code="invalid_session")
    if tok.used_at is None:
        tok.used_at = now
    new_raw, new_row = await _issue(session, user, request, family_id=tok.family_id, parent_id=tok.id,
                                    absolute=tok.absolute_expires_at)
    tok.successor_id = tok.successor_id or new_row.id
    out = await _access(session, user, tok.family_id)
    await session.commit()
    return out, new_raw


async def logout(session: AsyncSession, request: Request, raw: str | None, principal: Principal | None) -> None:
    if raw:
        tok = await repo.token_by_hash(session, hash_token(raw))
        if tok and tok.revoked_at is None:
            await repo.revoke_family(session, tok.family_id, "logout", utcnow())
            await audit.record(session, "auth.logout", request=request, actor_type="user", actor_id=tok.user_id)
    await session.commit()


async def logout_all(session: AsyncSession, request: Request, principal: Principal) -> None:
    await repo.revoke_all_for_user(session, principal.id, "logout_all", utcnow())
    await audit.record(session, "auth.logout_all", request=request, principal=principal)
    await session.commit()


async def change_password(session: AsyncSession, request: Request, principal: Principal, current: str, new: str) -> None:
    user = await session.get(User, principal.id)
    assert user is not None
    hit(f"chpw:{user.id}", 10, 60)
    if not verify_password(current, user.password_hash):
        await audit.record(session, "auth.password.change_failed", request=request, principal=principal, outcome="denied")
        await session.commit()
        raise Forbidden("Senha atual incorreta.", code="invalid_credentials")
    validate_password_policy(new, email=user.email)
    if verify_password(new, user.password_hash):
        from app.core.errors import Unprocessable

        raise Unprocessable("A nova senha deve ser diferente da atual.", code="weak_password")
    now = utcnow()
    user.password_hash = hash_password(new)
    user.password_changed_at = now
    user.must_change_password = False
    await repo.revoke_all_for_user(session, user.id, "password_changed", now)
    await audit.record(session, "auth.password.changed", request=request, principal=principal)
    await session.commit()
