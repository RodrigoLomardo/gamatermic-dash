"""Catalogo de widgets (MVP: 6 tipos) e validacao da config."""
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.errors import Unprocessable
from app.modules.query.compiler import FieldMeta, validate_spec
from app.modules.query.spec import QuerySpec

WidgetType = Literal["kpi", "line", "bar", "pie", "table", "gauge"]


class VizConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    format: Literal["number", "currency", "percent", "integer"] = "number"
    color: str | None = None
    target: float | None = None  # gauge: meta
    min: float | None = None
    max: float | None = None
    thresholds: list[dict] | None = None
    horizontal: bool | None = None
    stacked: bool | None = None
    columns: list[dict] | None = None  # table: [{field,label,format}]
    drill_field: str | None = None  # campo filtrado no drill-down


# min_w/min_h: menor tamanho da visao completa. Abaixo disso (ate COMPACT_MIN) o frontend troca
# para a visao compacta do tipo (linha -> valor + tendencia, barras/pizza -> ranking, tabela -> lista curta).
WIDGET_TYPES = {
    "kpi": {"label": "Indicador (KPI)", "min_w": 2, "min_h": 2, "needs": "1 medida; comparação com período anterior opcional"},
    "line": {"label": "Linha / evolução", "min_w": 4, "min_h": 3, "needs": "tempo + medidas (+1 dimensão para séries)"},
    "bar": {"label": "Barras", "min_w": 3, "min_h": 3, "needs": "1 dimensão + 1 medida"},
    "pie": {"label": "Pizza / rosca", "min_w": 3, "min_h": 3, "needs": "1 dimensão + 1 medida"},
    "table": {"label": "Tabela", "min_w": 4, "min_h": 3, "needs": "colunas (linhas) ou dimensões + medidas"},
    "gauge": {"label": "Medidor (meta)", "min_w": 2, "min_h": 3, "needs": "1 medida e meta em viz_config.target"},
}
COMPACT_MIN = (2, 2)  # nenhum grafico fica menor que isto (nem na visao compacta)


def full_min(wtype: str) -> tuple[int, int]:
    """Menor tamanho (w, h) da visao completa do tipo."""
    t = WIDGET_TYPES.get(wtype)
    return (int(t["min_w"]), int(t["min_h"])) if t else COMPACT_MIN  # type: ignore[call-overload]


def check_size(wtype: str, w: int, h: int) -> None:
    if w < COMPACT_MIN[0] or h < COMPACT_MIN[1]:
        label = WIDGET_TYPES.get(wtype, {}).get("label", wtype)
        raise Unprocessable(f"'{label}' precisa de pelo menos {COMPACT_MIN[0]}×{COMPACT_MIN[1]} na grade.", code="widget_too_small")


def catalog() -> list[dict]:
    return [{"type": k, **v, "compact_min_w": COMPACT_MIN[0], "compact_min_h": COMPACT_MIN[1], "viz_schema": VizConfig.model_json_schema(), "query_schema": QuerySpec.model_json_schema()}
            for k, v in WIDGET_TYPES.items()]


def validate_widget(wtype: str, query_config: dict, viz_config: dict, fields: dict[str, FieldMeta], time_field: str | None) -> QuerySpec:
    if wtype not in WIDGET_TYPES:
        raise Unprocessable(f"Tipo de widget inválido: {wtype}", code="invalid_widget")
    try:
        spec = QuerySpec.model_validate(query_config)
        VizConfig.model_validate(viz_config)
    except Exception as e:  # noqa: BLE001
        raise Unprocessable(f"Configuração inválida: {e}", code="invalid_widget") from e
    validate_spec(spec, fields, time_field, raw_mode_ok=(wtype == "table"))
    if wtype in ("kpi", "gauge") and (len(spec.measures) != 1 or spec.dimensions or spec.time or spec.columns):
        raise Unprocessable("KPI/medidor usam exatamente 1 medida, sem dimensões ou tempo.", code="invalid_widget")
    if wtype in ("bar", "pie") and (len(spec.dimensions) != 1 or len(spec.measures) < 1 or spec.time):
        raise Unprocessable("Barras/pizza usam 1 dimensão e ao menos 1 medida.", code="invalid_widget")
    if wtype == "line" and (spec.time is None or not spec.measures or spec.columns or len(spec.dimensions) > 1):
        raise Unprocessable("Linha usa tempo, medidas e no máximo 1 dimensão.", code="invalid_widget")
    if wtype == "table" and not spec.columns and not spec.measures:
        raise Unprocessable("Tabela exige colunas ou medidas.", code="invalid_widget")
    return spec
