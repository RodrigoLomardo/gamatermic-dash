"""Datasets e dashboards iniciais do setor Comercial (baseados no relatorio 'Vendas Ploomes 2025/2026')."""

from typing import Any


def F(name, label, dtype, role="dimension", *, key=False, nullable=True, source=None, pii=False):
    return {"name": name, "label": label, "data_type": dtype, "role": role, "is_key": key, "nullable": nullable,
            "source_column": source or label, "sensitivity": "pii" if pii else "none"}


DATASETS: list[dict[str, Any]] = [
    {
        "slug": "vendas", "name": "Vendas (pedidos)", "time_field": "data_pedido", "sheet": "Vendas", "load_mode": "upsert",
        "freshness_sla_seconds": 7 * 86400,
        "description": "Pedidos ganhos exportados do Ploomes. Chave: Número do pedido.",
        "fields": [
            F("numero", "Número", "integer", key=True), F("empresa_faturar", "Empresa que irá Faturar", "string"),
            F("data_pedido", "Data do Pedido", "date", "time", nullable=False), F("cliente", "Cliente", "string"),
            F("segmento", "Segmento do Cliente", "string"), F("projeto", "Projeto", "string"),
            F("valor", "Valor", "decimal", "measure", nullable=False), F("responsavel", "Responsável", "string"),
            F("colaboradores", "Usuários colaboradores do Negócio", "string"),
            F("condicao_pagamento", "Condição de Pagamento", "string"), F("produtos", "Produtos", "string"),
            F("prazo_dias", "Prazo de Pagamento_Nº Dias", "integer", "measure"),
        ],
    },
    {
        "slug": "propostas_ganhas", "name": "Propostas ganhas", "time_field": "data", "sheet": "Propostas Ganhas", "load_mode": "upsert",
        "freshness_sla_seconds": 7 * 86400, "description": "Propostas ganhas (todas as revisões). Chave: Código + Revisão.",
        "fields": [
            F("codigo", "Código", "integer", key=True), F("revisao", "Número da revisão", "integer", key=True),
            F("ultima_revisao", "Última revisão", "boolean"), F("empresa_faturar", "Empresa que irá Faturar", "string"),
            F("cliente", "Cliente do Negócio", "string"), F("valor", "Valor", "decimal", "measure", nullable=False),
            F("data", "Data", "date", "time", nullable=False), F("responsavel", "Responsável", "string"),
            F("criador", "Criador", "string"), F("previsao_faturamento", "Previsão de Faturamento", "date"),
        ],
    },
    {
        "slug": "propostas_perdidas", "name": "Propostas perdidas", "time_field": "data", "sheet": "Propostas Perdidas", "load_mode": "upsert",
        "freshness_sla_seconds": 7 * 86400, "description": "Propostas perdidas com motivo. Chave: Código + Revisão.",
        "fields": [
            F("codigo", "Código", "integer", key=True), F("revisao", "Número da revisão", "integer", key=True),
            F("ultima_revisao", "Última revisão", "boolean"), F("empresa_faturar", "Empresa que irá Faturar", "string"),
            F("cliente", "Cliente do Negócio", "string"), F("valor", "Valor", "decimal", "measure", nullable=False),
            F("data", "Data", "date", "time", nullable=False), F("termino_negocio", "Término do Negócio", "datetime"),
            F("motivo_perda", "Motivo de perda do Negócio", "string"), F("responsavel", "Responsável", "string"),
        ],
    },
    {
        "slug": "propostas_abertas", "name": "Propostas abertas (pipeline)", "time_field": "data", "sheet": "Propostas Abertas",
        "load_mode": "replace_snapshot", "freshness_sla_seconds": 7 * 86400,
        "description": "Retrato do pipeline em aberto: cada arquivo substitui o anterior (replace_snapshot).",
        "fields": [
            F("codigo", "Código", "integer", key=True), F("revisao", "Número da revisão", "integer", key=True),
            F("ultima_revisao", "Última revisão", "boolean"), F("empresa_faturar", "Empresa que irá Faturar", "string"),
            F("cliente", "Cliente do Negócio", "string"), F("valor", "Valor", "decimal", "measure", nullable=False),
            F("data", "Data", "date", "time", nullable=False), F("negocio", "Negócio", "string"),
            F("contato", "Contato", "string", pii=True), F("produtos", "Produtos da proposta", "string"),
            F("responsavel", "Responsável", "string"), F("condicao_pagamento", "Condição de Pagamento", "string"),
            F("previsao_faturamento", "Previsão de Faturamento", "date"),
        ],
    },
]

ALL_PERIOD = {"mode": "relative", "preset": "all"}
LAST12 = {"mode": "relative", "preset": "last_12_months"}
LAST_REV = {"field": "ultima_revisao", "op": "eq", "value": True}


def W(type_, title, ds, x, y, w, h, query, viz=None, follows=True):
    return {"type": type_, "title": title, "dataset": ds, "x": x, "y": y, "w": w, "h": h, "query_config": query,
            "viz_config": viz or {}, "follows_global_period": follows}


def M(agg, alias, field=None):
    return {"agg": agg, "alias": alias, **({"field": field} if field else {})}


DASHBOARDS: list[dict[str, Any]] = [
    {
        "slug": "vendas-visao-geral", "name": "Vendas - Visão Geral", "default_period": "this_month",
        "description": "Faturamento, pedidos e ticket médio do mês, com evolução e rankings.",
        "widgets": [
            W("kpi", "Faturamento no mês", "vendas", 0, 0, 3, 3, {"measures": [M("sum", "total", "valor")], "compare_previous_period": True},
              {"format": "currency", "color": "primary"}),
            W("kpi", "Pedidos ganhos", "vendas", 3, 0, 3, 3, {"measures": [M("count", "pedidos")], "compare_previous_period": True},
              {"format": "integer"}),
            W("kpi", "Ticket médio", "vendas", 6, 0, 3, 3, {"measures": [M("avg", "ticket", "valor")], "compare_previous_period": True},
              {"format": "currency"}),
            W("gauge", "Meta do mês (editável)", "vendas", 9, 0, 3, 3, {"measures": [M("sum", "total", "valor")]},
              {"format": "currency", "target": 4000000, "min": 0}),
            W("line", "Faturamento - últimos 12 meses", "vendas", 0, 3, 8, 4,
              {"measures": [M("sum", "total", "valor")], "time": {"granularity": "month"}, "period": LAST12}, {"format": "currency"}, False),
            W("pie", "Faturamento por empresa", "vendas", 8, 3, 4, 4,
              {"measures": [M("sum", "total", "valor")], "dimensions": ["empresa_faturar"], "sort": [{"by": "total", "dir": "desc"}], "limit": 6},
              {"format": "currency", "drill_field": "empresa_faturar", "drill_path": ["empresa_faturar", "cliente", "responsavel"]}),
            W("bar", "Top 10 clientes", "vendas", 0, 7, 6, 4,
              {"measures": [M("sum", "total", "valor")], "dimensions": ["cliente"], "sort": [{"by": "total", "dir": "desc"}], "limit": 10},
              {"format": "currency", "horizontal": True, "drill_field": "cliente", "drill_path": ["cliente", "responsavel", "empresa_faturar"]}),
            W("bar", "Faturamento por segmento", "vendas", 6, 7, 6, 4,
              {"measures": [M("sum", "total", "valor")], "dimensions": ["segmento"], "sort": [{"by": "total", "dir": "desc"}], "limit": 8},
              {"format": "currency", "horizontal": True, "drill_field": "segmento", "drill_path": ["segmento", "cliente", "responsavel"]}),
            W("table", "Faturamento por responsável", "vendas", 0, 11, 5, 4,
              {"measures": [M("sum", "total", "valor"), M("count", "pedidos")], "dimensions": ["responsavel"],
               "sort": [{"by": "total", "dir": "desc"}], "limit": 10},
              {"columns": [{"field": "responsavel", "label": "Responsável"}, {"field": "total", "label": "Faturamento", "format": "currency"},
                           {"field": "pedidos", "label": "Pedidos", "format": "integer"}], "drill_field": "responsavel", "drill_path": ["responsavel", "cliente", "segmento"]}),
            W("table", "Últimos pedidos", "vendas", 5, 11, 7, 4,
              {"columns": ["data_pedido", "cliente", "empresa_faturar", "responsavel", "valor"], "sort": [{"by": "data_pedido", "dir": "desc"}], "limit": 15},
              {"columns": [{"field": "data_pedido", "label": "Data", "format": "date"}, {"field": "cliente", "label": "Cliente"},
                           {"field": "empresa_faturar", "label": "Empresa"}, {"field": "responsavel", "label": "Responsável"},
                           {"field": "valor", "label": "Valor", "format": "currency"}]}),
        ],
    },
    {
        "slug": "propostas-funil-comercial", "name": "Propostas - Funil Comercial", "default_period": "this_month",
        "description": "Propostas ganhas, perdidas e pipeline em aberto.",
        "widgets": [
            W("kpi", "Propostas ganhas (qtd)", "propostas_ganhas", 0, 0, 3, 3,
              {"measures": [M("count", "qtd")], "filters": [LAST_REV], "compare_previous_period": True}, {"format": "integer"}),
            W("kpi", "Valor ganho", "propostas_ganhas", 3, 0, 3, 3,
              {"measures": [M("sum", "total", "valor")], "filters": [LAST_REV], "compare_previous_period": True}, {"format": "currency"}),
            W("kpi", "Valor perdido", "propostas_perdidas", 6, 0, 3, 3,
              {"measures": [M("sum", "total", "valor")], "filters": [LAST_REV], "compare_previous_period": True}, {"format": "currency", "color": "danger"}),
            W("kpi", "Pipeline em aberto", "propostas_abertas", 9, 0, 3, 3,
              {"measures": [M("sum", "total", "valor")], "filters": [LAST_REV], "period": ALL_PERIOD}, {"format": "currency", "color": "accent"}, False),
            W("line", "Valor ganho - 12 meses", "propostas_ganhas", 0, 3, 6, 4,
              {"measures": [M("sum", "total", "valor")], "time": {"granularity": "month"}, "filters": [LAST_REV], "period": LAST12},
              {"format": "currency"}, False),
            W("line", "Valor perdido - 12 meses", "propostas_perdidas", 6, 3, 6, 4,
              {"measures": [M("sum", "total", "valor")], "time": {"granularity": "month"}, "filters": [LAST_REV], "period": LAST12},
              {"format": "currency", "color": "danger"}, False),
            W("bar", "Motivos de perda (qtd)", "propostas_perdidas", 0, 7, 6, 4,
              {"measures": [M("count", "qtd")], "dimensions": ["motivo_perda"], "filters": [LAST_REV], "sort": [{"by": "qtd", "dir": "desc"}], "limit": 8},
              {"format": "integer", "horizontal": True, "drill_field": "motivo_perda", "drill_path": ["motivo_perda", "cliente", "responsavel"]}),
            W("pie", "Pipeline por empresa", "propostas_abertas", 6, 7, 3, 4,
              {"measures": [M("sum", "total", "valor")], "dimensions": ["empresa_faturar"], "filters": [LAST_REV], "period": ALL_PERIOD,
               "sort": [{"by": "total", "dir": "desc"}], "limit": 6}, {"format": "currency", "drill_field": "empresa_faturar"}, False),
            W("bar", "Pipeline por responsável", "propostas_abertas", 9, 7, 3, 4,
              {"measures": [M("sum", "total", "valor")], "dimensions": ["responsavel"], "filters": [LAST_REV], "period": ALL_PERIOD,
               "sort": [{"by": "total", "dir": "desc"}], "limit": 8}, {"format": "currency", "horizontal": True}, False),
            W("table", "Maiores propostas em aberto", "propostas_abertas", 0, 11, 12, 4,
              {"columns": ["data", "cliente", "negocio", "responsavel", "valor", "previsao_faturamento"], "filters": [LAST_REV],
               "period": ALL_PERIOD, "sort": [{"by": "valor", "dir": "desc"}], "limit": 15},
              {"columns": [{"field": "data", "label": "Data", "format": "date"}, {"field": "cliente", "label": "Cliente"},
                           {"field": "negocio", "label": "Negócio"}, {"field": "responsavel", "label": "Responsável"},
                           {"field": "valor", "label": "Valor", "format": "currency"},
                           {"field": "previsao_faturamento", "label": "Prev. faturamento", "format": "date"}]}, False),
        ],
    },
]
