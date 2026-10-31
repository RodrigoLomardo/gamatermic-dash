"""Cliente minimo da API Groq (compativel com OpenAI). Host fixo por configuracao: nunca vem do usuario (sem SSRF).

Erros da Groq nunca viram 401 para o navegador: o frontend trataria como sessao perdida (ADR 0010).
"""
import json
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import DomainError, TooManyRequests
from app.core.logging import get_logger

log = get_logger("ai.groq")

# testes injetam um transporte falso (httpx.MockTransport); producao usa o padrao
_transport: httpx.AsyncBaseTransport | None = None


def set_transport(t: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = t


class AiUpstreamError(DomainError):
    status = 502
    code = "ai_unavailable"


class AiTimeout(DomainError):
    status = 504
    code = "ai_timeout"


class AiBadOutput(DomainError):
    """O modelo devolveu algo fora do schema (a Groq responde 400 nesse caso)."""

    status = 502
    code = "ai_bad_output"


def _client() -> httpx.AsyncClient:
    s = get_settings()
    return httpx.AsyncClient(base_url=s.groq_base_url, timeout=s.ai_timeout_seconds, transport=_transport, follow_redirects=False)


def _raise_for(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    if r.status_code in (401, 403):
        raise AiUpstreamError("A Groq recusou a chave de API. Confira em Configurações.", code="ai_invalid_key")
    if r.status_code == 429:
        try:
            wait = max(1, int(float(r.headers.get("retry-after", "30"))))
        except ValueError:
            wait = 30
        raise TooManyRequests(f"Limite de uso da Groq atingido. Tente em {wait} s.", code="ai_rate_limited", extra={"retry_after": wait})
    if r.status_code == 400 and "schema" in r.text.lower():
        raise AiBadOutput("O modelo devolveu uma resposta fora do formato esperado.")
    if r.status_code == 404:
        raise AiUpstreamError("Modelo não encontrado na Groq. Escolha outro em Configurações.", code="ai_model_not_found")
    # corpo da Groq nao vai para o log (pode ecoar o prompt); so status
    log.warning("groq_error", status=r.status_code)
    raise AiUpstreamError(f"A Groq respondeu com erro ({r.status_code}). Tente novamente.")


async def list_models(api_key: str) -> tuple[list[str], int]:
    """IDs de modelos ativos na conta e latencia em ms."""
    t0 = time.perf_counter()
    try:
        async with _client() as c:
            r = await c.get("/models", headers={"Authorization": f"Bearer {api_key}"})
    except httpx.TimeoutException:
        raise AiTimeout("A Groq não respondeu a tempo.")
    except httpx.HTTPError:
        raise AiUpstreamError("Não foi possível conectar à Groq.")
    _raise_for(r)
    ids = [m.get("id") for m in r.json().get("data", []) if isinstance(m, dict)]
    return [i for i in ids if isinstance(i, str)], int((time.perf_counter() - t0) * 1000)


async def chat_json(api_key: str, model: str, messages: list[dict], schema: dict, *, name: str, max_tokens: int = 6000) -> tuple[dict, dict]:
    """Chamada com saida estrita (json_schema). Retorna (objeto, usage)."""
    body: dict[str, Any] = {
        "model": model, "messages": messages, "temperature": 0.2, "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    }
    if model.startswith("openai/gpt-oss"):
        body |= {"reasoning_effort": "low", "include_reasoning": False}
    try:
        async with _client() as c:
            r = await c.post("/chat/completions", json=body, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.TimeoutException:
        raise AiTimeout("A Groq não respondeu a tempo. Tente um pedido mais curto.")
    except httpx.HTTPError:
        raise AiUpstreamError("Não foi possível conectar à Groq.")
    _raise_for(r)
    data = r.json()
    try:
        content = data["choices"][0]["message"]["content"]
        out = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise AiBadOutput("O modelo devolveu uma resposta ilegível.")
    if not isinstance(out, dict):
        raise AiBadOutput("O modelo devolveu uma resposta ilegível.")
    return out, data.get("usage") or {}
