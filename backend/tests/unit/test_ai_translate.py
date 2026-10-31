import pytest

from app.core.errors import Unprocessable
from app.modules.ai.prompt import RESPONSE_SCHEMA
from app.modules.ai.translate import to_widget
from app.modules.query.compiler import FieldMeta

FIELDS = {
    "data": FieldMeta("data", "date", "time"), "valor": FieldMeta("valor", "decimal", "measure"),
    "cliente": FieldMeta("cliente", "string", "dimension"),
}
LABELS = {"data": "Data", "valor": "Valor", "cliente": "Cliente do Negócio"}


def raw(**kw):
    return {"type": "bar", "title": "T", "rationale": "", "measures": [{"agg": "sum", "field": "valor", "label": "Valor total"}],
            "dimensions": ["cliente"], "columns": [], "time_granularity": None, "period_preset": None, "filters": [],
            "sort_by": None, "sort_dir": "desc", "limit": None, "format": "currency", "horizontal": None, "target": None} | kw


def test_bar_defaults_sort_limit_and_drill():
    w = to_widget(raw(), FIELDS, LABELS, "data")
    assert w["query_config"] == {"measures": [{"agg": "sum", "alias": "valor_total", "field": "valor"}], "dimensions": ["cliente"],
                                 "limit": 10, "sort": [{"by": "valor_total", "dir": "desc"}]}
    assert w["viz_config"]["drill_field"] == "cliente" and (w["w"], w["h"]) == (6, 4)


def test_label_is_resolved_and_unknown_field_rejected():
    assert to_widget(raw(dimensions=["cliente do negócio"]), FIELDS, LABELS, "data")["query_config"]["dimensions"] == ["cliente"]
    with pytest.raises(Unprocessable):
        to_widget(raw(dimensions=["contato"]), FIELDS, LABELS, "data")


def test_gauge_without_target_becomes_kpi_and_line_needs_time():
    assert to_widget(raw(type="gauge", dimensions=[]), FIELDS, LABELS, "data")["type"] == "kpi"
    g = to_widget(raw(type="gauge", dimensions=[], target=4_000_000), FIELDS, LABELS, "data")
    assert g["viz_config"]["target"] == 4_000_000.0
    with pytest.raises(Unprocessable):
        to_widget(raw(type="line", dimensions=[]), FIELDS, LABELS, None)
    with pytest.raises(Unprocessable):
        to_widget(raw(type="pie", dimensions=[]), FIELDS, LABELS, "data")


def test_duplicate_aliases_and_count_ignores_field():
    w = to_widget(raw(type="table", measures=[{"agg": "count", "field": "cliente", "label": "Qtd"}, {"agg": "sum", "field": "valor", "label": "Qtd"}]),
                  FIELDS, LABELS, "data")
    ms = w["query_config"]["measures"]
    assert ms[0] == {"agg": "count", "alias": "qtd"} and ms[1]["alias"] == "qtd_2"
    assert [c["field"] for c in w["viz_config"]["columns"]] == ["cliente", "qtd", "qtd_2"]


def test_schema_is_strict_compatible():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False and set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(RESPONSE_SCHEMA)
