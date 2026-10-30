from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal, load_user_principal
from app.core.config import get_settings
from app.core.deps import get_session, public, require_user_allow_pwchange
from app.core.errors import Forbidden
from app.modules.auth import service
from app.modules.auth.schemas import ChangePasswordIn, LoginIn, MeOut, TokenOut
from app.modules.iam.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "gd_refresh"
COOKIE_PATH = "/api/v1/auth"


def _set_cookie(resp: Response, raw: str) -> None:
    s = get_settings()
    resp.set_cookie(COOKIE, raw, max_age=s.refresh_absolute_days * 86400, httponly=True, secure=s.cookie_secure,
                    samesite="strict", path=COOKIE_PATH)


def _csrf(request: Request) -> None:
    """SameSite=Strict + Origin conferido + header customizado."""
    if request.headers.get("x-requested-with") != "gamatermic":
        raise Forbidden("Requisição inválida.", code="csrf")
    origin = request.headers.get("origin")
    if origin:
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        allowed = {o.rstrip("/") for o in get_settings().cors_origins}
        if origin.split("://", 1)[-1] != host and origin.rstrip("/") not in allowed:
            raise Forbidden("Origem não permitida.", code="csrf")


@router.post("/login", response_model=TokenOut, dependencies=[Depends(public)])
async def login(body: LoginIn, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    _csrf(request)
    out, raw = await service.login(session, request, body.email, body.password)
    _set_cookie(response, raw)
    response.headers["Cache-Control"] = "no-store"
    return out


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(public)])
async def refresh(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    _csrf(request)
    out, raw = await service.refresh(session, request, request.cookies.get(COOKIE))
    _set_cookie(response, raw)
    response.headers["Cache-Control"] = "no-store"
    return out


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session),
                 principal: Principal = Depends(require_user_allow_pwchange)):
    _csrf(request)
    await service.logout(session, request, request.cookies.get(COOKIE), principal)
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    response.status_code = 204
    return response


@router.post("/logout-all", status_code=204)
async def logout_all(request: Request, response: Response, session: AsyncSession = Depends(get_session),
                     principal: Principal = Depends(require_user_allow_pwchange)):
    _csrf(request)
    await service.logout_all(session, request, principal)
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
async def me(session: AsyncSession = Depends(get_session), principal: Principal = Depends(require_user_allow_pwchange)):
    user = await session.get(User, principal.id)
    p = await load_user_principal(session, user)  # type: ignore[arg-type]
    return service.me_out(user, p)  # type: ignore[arg-type]


@router.post("/change-password", status_code=204)
async def change_password(body: ChangePasswordIn, request: Request, response: Response,
                          session: AsyncSession = Depends(get_session),
                          principal: Principal = Depends(require_user_allow_pwchange)):
    _csrf(request)
    await service.change_password(session, request, principal, body.current_password, body.new_password)
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    response.status_code = 204
    return response
