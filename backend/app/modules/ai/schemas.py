import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.modules.dashboards.widget_types import WidgetType
from app.modules.query.spec import Preset


class AiStatusOut(BaseModel):
    available: bool
    model: str | None = None


class ProposalsIn(BaseModel):
    dataset_id: uuid.UUID
    prompt: str = Field(min_length=3, max_length=1000)
    max_proposals: int = Field(default=6, ge=1, le=8)
    default_period: Preset = "last_12_months"  # periodo da pre-visualizacao (e do painel criado)
    # gerar graficos para um painel existente: a IA ve o que ja existe e nao repete (exige dashboard:edit)
    dashboard_id: uuid.UUID | None = None


class Proposal(BaseModel):
    id: str  # local a resposta; propostas nao sao persistidas
    type: WidgetType
    title: str
    rationale: str
    dataset_id: uuid.UUID
    query_config: dict[str, Any]
    viz_config: dict[str, Any]
    follows_global_period: bool
    x: int | None = None  # posicao sugerida pela IA (None = encaixar abaixo)
    y: int | None = None
    w: int
    h: int
    preview: dict[str, Any] | None = None


class Discarded(BaseModel):
    title: str
    reason: str


class Box(BaseModel):
    x: int
    y: int
    w: int
    h: int


class LayoutChange(BaseModel):
    """Mudanca sugerida num grafico que ja esta no painel, para abrir espaco ou melhorar a leitura."""

    widget_id: uuid.UUID
    title: str
    type: str
    before: Box
    after: Box
    reason: str
    compact: bool  # depois da mudanca o grafico fica abaixo do tamanho completo (visao compacta)


class Usage(BaseModel):
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ProposalsOut(BaseModel):
    explanation: str
    proposals: list[Proposal]
    discarded: list[Discarded]
    layout_changes: list[LayoutChange] = []
    usage: Usage
