from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, detail: str = "", *, code: str | None = None, extra: dict | None = None):
        super().__init__(detail)
        self.detail = detail or self.code
        if code:
            self.code = code
        self.extra = extra or {}


class NotFound(DomainError):
    status = 404
    code = "not_found"


class Forbidden(DomainError):
    status = 403
    code = "forbidden"


class Unauthorized(DomainError):
    status = 401
    code = "unauthorized"


class Conflict(DomainError):
    status = 409
    code = "conflict"


class Unprocessable(DomainError):
    status = 422
    code = "unprocessable"


class TooManyRequests(DomainError):
    status = 429
    code = "too_many_requests"


class PayloadTooLarge(DomainError):
    status = 413
    code = "payload_too_large"


def problem(status: int, code: str, detail: str, request: Request | None = None, **extra) -> JSONResponse:
    body = {"type": f"about:blank#{code}", "title": code, "status": status, "detail": detail, "code": code, **extra}
    if request is not None:
        body["instance"] = request.url.path
        rid = getattr(request.state, "request_id", None)
        if rid:
            body["request_id"] = rid
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError):
        resp = problem(exc.status, exc.code, exc.detail, request, **exc.extra)
        if isinstance(exc, TooManyRequests) and "retry_after" in exc.extra:
            resp.headers["Retry-After"] = str(exc.extra["retry_after"])
        if isinstance(exc, Unauthorized):
            resp.headers["WWW-Authenticate"] = "Bearer"
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errs = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return problem(422, "validation_error", "Dados inválidos", request, errors=errs)
