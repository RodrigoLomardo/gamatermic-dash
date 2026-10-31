from datetime import datetime

from pydantic import BaseModel, Field


class AiModelOption(BaseModel):
    id: str
    label: str


class ApiKeyState(BaseModel):
    configured: bool
    last4: str | None = None


class AiSettingsOut(BaseModel):
    enabled: bool
    model: str
    api_key: ApiKeyState
    models: list[AiModelOption]
    updated_at: datetime | None = None


class AiSettingsIn(BaseModel):
    enabled: bool
    model: str
    # None = mantem a chave atual; "" = remove; texto = substitui. Nunca e devolvida.
    api_key: str | None = Field(default=None, max_length=300)


class AiTestOut(BaseModel):
    ok: bool
    model: str
    model_available: bool = False
    latency_ms: int | None = None
    error: str | None = None
