"""Traduz a saida reduzida do modelo para QuerySpec + viz_config. Nada daqui confia no modelo: tudo passa por validate_widget."""
import re
import unicodedata
from typing import Any

from app.core.errors import Unprocessable
from app.modules.dashboards.widget_types import full_min
from app.modules.query.compiler import FieldMeta

GRID_COLS, MAX_H, MAX_Y = 12, 20, 400
SIZES = {"kpi": (3, 3), "gauge": (3, 3), "line": (8, 4), "bar": (6, 4), "pie": (4, 4), "table": (6, 4)}
LIMITS = {"bar": (10, 15), "pie": (6, 8), "table": (15, 50)}  # (padrao, maximo)
NUMERIC = {"integer", "decimal"}
# regra de negocio (CLAUDE.md): propostas tem revisoes; so a ultima conta
LAST_REVISION_FIELD = "ultima_revisao"


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s or not s[0].isalpha():
        s = "m_" + s
    return s[:40].rstrip("_") or "m"


class Resolver:
    """Aceita o nome do campo ou, por tolerancia, o rotulo exato. Campo pii nao existe aqui."""

    def __init__(self, fields: dict[str, FieldMeta], labels: dict[str, str]):
        self.fields = fields
        self.by_label = {v.casefold(): k for k, v in labels.items() if k in fields}
        self.labels = labels

    def __call__(self, name: str | None) -> str | None:
        if name is None or name == "":
            return None
        if name in self.fields:
            return name
        hit = self.by_label.get(name.casefold())
        if hit:
            return hit
        raise Unprocessable(f"Campo inexistente: '{name}'.", code="unknown_field")


def _fmt_for(meta: FieldMeta | None, default: str) -> str | None:
    if meta is None:
        return default
    if meta.data_type in ("date", "datetime"):
        return "date"
    return default if meta.data_type in NUMERIC else None


def to_widget(raw: dict, fields: dict[str, FieldMeta], labels: dict[str, str], time_field: str | None) -> dict[str, Any]:
    """Saida do modelo -> {type,title,rationale,query_config,viz_config,follows_global_period,w,h}. Levanta Unprocessable."""
    r = Resolver(fields, labels)
    wtype: str = raw.get("type") or ""
    if wtype not in SIZES:
        raise Unprocessable(f"Tipo de widget inválido: {wtype}", code="invalid_widget")
    fmt: str = raw["format"] if raw.get("format") in ("number", "currency", "percent", "integer") else "number"
    target = raw.get("target")
    if wtype == "gauge" and not isinstance(target, (int, float)):
        wtype = "kpi"  # medidor sem meta nao faz sentido

    measures: list[dict] = []
    aliases: set[str] = set()
    measure_labels: dict[str, str] = {}
    for m in raw.get("measures") or []:
        agg = m.get("agg")
        field = r(m.get("field"))
        if agg == "count":
            field = None
        alias = _slug(m.get("label") or f"{agg}_{field or 'linhas'}")
        while alias in aliases:
            alias = f"{alias}_2"[:60]
        aliases.add(alias)
        measure_labels[alias] = (m.get("label") or alias).strip()[:80]
        measures.append({"agg": agg, "alias": alias, **({"field": field} if field else {})})

    dims = [d for d in (r(x) for x in raw.get("dimensions") or []) if d]
    cols = [c for c in (r(x) for x in raw.get("columns") or []) if c]
    gran = raw.get("time_granularity")
    qc: dict[str, Any] = {}

    if wtype in ("kpi", "gauge"):
        if not measures:
            raise Unprocessable("KPI sem medida.", code="invalid_query")
        qc["measures"] = measures[:1]
        if time_field:
            qc["compare_previous_period"] = wtype == "kpi"
    elif wtype == "line":
        if not time_field:
            raise Unprocessable("Dataset sem campo de tempo para gráfico de linha.", code="invalid_query")
        qc["measures"] = measures[:3]
        qc["time"] = {"granularity": gran or "month"}
        if dims:
            qc["dimensions"] = dims[:1]
    elif wtype in ("bar", "pie"):
        if not dims:
            raise Unprocessable(f"Gráfico '{wtype}' precisa de uma dimensão.", code="invalid_query")
        qc["measures"] = measures[:1 if wtype == "pie" else 3]
        qc["dimensions"] = dims[:1]
    else:  # table
        if cols and not measures:
            qc["columns"] = cols[:12]
        else:
            qc["measures"] = measures[:6]
            qc["dimensions"] = dims[:3]

    if wtype in LIMITS:
        default, cap = LIMITS[wtype]
        lim = raw.get("limit")
        qc["limit"] = max(1, min(int(lim), cap)) if isinstance(lim, int) else default

    sort_by, sort_dir = raw.get("sort_by"), raw.get("sort_dir") if raw.get("sort_dir") in ("asc", "desc") else "desc"
    if qc.get("columns"):
        tf = time_field if time_field in qc["columns"] else None
        if tf:
            qc["sort"] = [{"by": tf, "dir": "desc"}]
    elif sort_by == "measure" and qc.get("measures"):
        qc["sort"] = [{"by": qc["measures"][0]["alias"], "dir": sort_dir}]
    elif sort_by == "dimension" and qc.get("dimensions"):
        qc["sort"] = [{"by": qc["dimensions"][0], "dir": sort_dir}]
    elif sort_by == "time" and qc.get("time"):
        qc["sort"] = [{"by": "time", "dir": sort_dir}]
    elif wtype in ("bar", "pie", "table") and qc.get("measures") and qc.get("dimensions"):
        qc["sort"] = [{"by": qc["measures"][0]["alias"], "dir": "desc"}]

    filters = []
    for f in raw.get("filters") or []:
        name = r(f.get("field"))
        if name and name != LAST_REVISION_FIELD:
            filters.append({"field": name, "op": f.get("op"), "value": f.get("value")})
    if LAST_REVISION_FIELD in fields and fields[LAST_REVISION_FIELD].data_type == "boolean":
        filters.append({"field": LAST_REVISION_FIELD, "op": "eq", "value": True})
    if filters:
        qc["filters"] = filters[:20]

    preset = raw.get("period_preset")
    follows = True
    if preset and time_field:
        qc["period"] = {"mode": "relative", "preset": preset}
        follows = False

    vc: dict[str, Any] = {"format": fmt}
    if wtype == "gauge":
        vc |= {"target": float(target), "min": 0}  # type: ignore[arg-type]
    if wtype == "bar" and raw.get("horizontal"):
        vc["horizontal"] = True
    if wtype in ("bar", "pie", "table") and qc.get("dimensions"):
        vc["drill_field"] = qc["dimensions"][0]
    if wtype == "table":
        if qc.get("columns"):
            vc["columns"] = [{"field": c, "label": labels.get(c, c), **({"format": f} if (f := _fmt_for(fields.get(c), fmt)) else {})}
                             for c in qc["columns"]]
        else:
            vc["columns"] = [{"field": d, "label": labels.get(d, d)} for d in qc["dimensions"]] + [
                {"field": m["alias"], "label": measure_labels[m["alias"]], "format": "integer" if m["agg"] in ("count", "count_distinct") else fmt} for m in qc["measures"]]

    x, y, w, h = placement(wtype, raw)
    title = (raw.get("title") or "Sem título").strip()[:160]
    return {"type": wtype, "title": title, "rationale": (raw.get("rationale") or "").strip()[:300], "query_config": qc,
            "viz_config": vc, "follows_global_period": follows, "x": x, "y": y, "w": w, "h": h}


def _int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def placement(wtype: str, raw: dict) -> tuple[int | None, int | None, int, int]:
    """Posicao sugerida pelo modelo, saneada. Grafico novo nasce na visao completa (>= minimo do tipo)."""
    dw, dh = SIZES[wtype]
    mw, mh = full_min(wtype)
    w = min(max(_int(raw.get("w")) or dw, mw), GRID_COLS)
    h = min(max(_int(raw.get("h")) or dh, mh), MAX_H)
    x, y = _int(raw.get("x")), _int(raw.get("y"))
    if x is None or y is None:
        return None, None, w, h
    return min(max(x, 0), GRID_COLS - w), min(max(y, 0), MAX_Y), w, h
