"""Configuracoes do sistema. A chave da Groq e somente escrita: nunca sai da API, do log ou da auditoria."""
from dataclasses import dataclass

from cryptography.fernet import InvalidToken
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import Principal
from app.core.crypto import decrypt, encrypt
from app.core.errors import DomainError, Unprocessable
from app.core.logging import get_logger
from app.modules.ai import groq_client
from app.modules.audit import service as audit
from app.modules.settings import repository as repo
from app.modules.settings import schemas as sc

log = get_logger("settings")

AI_KEY = "ai"
AI_SECRET_KEY = "ai.groq_api_key"
# allowlist (ADR 0010): modelos de producao da Groq com saida estrita. Preview fica fora.
AI_MODELS: dict[str, str] = {
    "openai/gpt-oss-120b": "GPT-OSS 120B — padrão, melhor qualidade",
    "openai/gpt-oss-20b": "GPT-OSS 20B — mais rápido e econômico",
}
DEFAULT_MODEL = "openai/gpt-oss-120b"


@dataclass
class AiRuntime:
    enabled: bool
    model: str
    api_key: str | None

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.api_key)


def _decrypt(blob: bytes | None) -> str | None:
    if not blob:
        return None
    try:
        return decrypt(blob)
    except InvalidToken:
        # chave Fernet trocada sem recifrar: trata como nao configurada (runbook de rotacao)
        log.warning("ai_key_undecryptable")
        return None


async def ai_runtime(session: AsyncSession) -> AiRuntime:
    row = await repo.get(session, AI_KEY)
    sec = await repo.get(session, AI_SECRET_KEY)
    v = row.value if row else {}
    model = str(v["model"]) if v.get("model") in AI_MODELS else DEFAULT_MODEL
    return AiRuntime(enabled=bool(v.get("enabled")), model=model, api_key=_decrypt(sec.secret_ciphertext if sec else None))


async def chat_enabled(session: AsyncSession) -> bool:
    """Liga/desliga so o chat de analise (RF-16); o resto da IA segue o flag geral. Padrao: ligado."""
    row = await repo.get(session, AI_KEY)
    return bool((row.value if row else {}).get("analysis_chat", True))


async def get_ai(session: AsyncSession) -> sc.AiSettingsOut:
    row = await repo.get(session, AI_KEY)
    sec = await repo.get(session, AI_SECRET_KEY)
    rt = await ai_runtime(session)
    stamps = [r.updated_at for r in (row, sec) if r is not None]
    return sc.AiSettingsOut(
        enabled=rt.enabled, model=rt.model, analysis_chat=await chat_enabled(session),
        api_key=sc.ApiKeyState(configured=bool(rt.api_key), last4=rt.api_key[-4:] if rt.api_key else None),
        models=[sc.AiModelOption(id=k, label=v) for k, v in AI_MODELS.items()],
        updated_at=max(stamps) if stamps else None,
    )


async def update_ai(session: AsyncSession, request: Request, p: Principal, body: sc.AiSettingsIn) -> sc.AiSettingsOut:
    if body.model not in AI_MODELS:
        raise Unprocessable("Modelo não permitido.", code="invalid_model")
    meta: dict = {"enabled": body.enabled, "model": body.model, "analysis_chat": body.analysis_chat}
    if body.api_key is not None:
        key = body.api_key.strip()
        if key and (len(key) < 20 or any(ch.isspace() for ch in key)):
            raise Unprocessable("Chave de API em formato inválido.", code="invalid_api_key")
        await repo.set_secret(session, AI_SECRET_KEY, encrypt(key) if key else None, p.id)
        meta["api_key_changed"] = "replaced" if key else "removed"  # nunca o valor
    current = await ai_runtime(session) if body.api_key is None else None
    has_key = bool(body.api_key.strip()) if body.api_key is not None else bool(current and current.api_key)
    if body.enabled and not has_key:
        raise Unprocessable("Informe a chave de API da Groq antes de ativar a IA.", code="api_key_required")
    await repo.upsert(session, AI_KEY, {"enabled": body.enabled, "model": body.model, "analysis_chat": body.analysis_chat}, p.id)
    await audit.record(session, "settings.ai.update", request=request, principal=p, resource_type="settings", resource_id=AI_KEY, metadata=meta)
    await session.commit()
    return await get_ai(session)


async def test_ai(session: AsyncSession, request: Request, p: Principal) -> sc.AiTestOut:
    rt = await ai_runtime(session)
    if not rt.api_key:
        return sc.AiTestOut(ok=False, model=rt.model, error="Nenhuma chave de API configurada.")
    try:
        ids, ms = await groq_client.list_models(rt.api_key)
    except DomainError as e:
        out = sc.AiTestOut(ok=False, model=rt.model, error=e.detail)
    else:
        available = rt.model in ids
        out = sc.AiTestOut(ok=available, model=rt.model, model_available=available, latency_ms=ms,
                           error=None if available else "A chave funciona, mas o modelo escolhido não está disponível na conta.")
    await audit.record(session, "settings.ai.test", request=request, principal=p, resource_type="settings", resource_id=AI_KEY,
                       outcome="success" if out.ok else "failure", metadata={"model": rt.model})
    await session.commit()
    return out
