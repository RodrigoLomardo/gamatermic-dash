# ADR 0012 — Painel analítico (desktop): drill, filtros, registros, exportação e visões

Status: aceito (Etapas 1–5 do plano: análise interativa + POC + chat por IA) · Data: 01/11/2026 · Plano: [`docs/planos/GAMA-FEAT-PAINEL-ANALITICO.md`](../planos/GAMA-FEAT-PAINEL-ANALITICO.md)

## Contexto

A TV mostra; quem está no PC precisa explorar. O plano propôs uma rota própria de análise, com filtros ricos, drill em hierarquia, drill-through, tela cheia, busca, exportação e visões salvas, e depois um chat por IA.

## Decisão

1. **Rota separada** `/dashboards/:id/analise` (lazy). `TvPage`, `/display/*` e playlists não mudam (RNF-07).
2. **Estado da visão na URL** (`p`/`from`+`to`, `f`, `w`). Cada passo de drill entra no histórico do navegador: voltar desfaz. A URL é interpretada com tolerância: valor adulterado vira "sem filtro", nunca erro.
3. **Drill sem SQL novo.** Hierarquia em `viz_config.drill_path` (validada contra `dataset_fields`; campo `pii` recusado); sem ela vale `drill_field`. O front só **pede** outro agrupamento por widget (`DataRequest.overrides`: `group_by`, `granularity`, `limit`) e o backend remonta o `QuerySpec` (`apply_group`), que passa pela mesma validação de sempre. O override nunca grava no painel.
4. **Drill de tempo** (linha): clique no eixo aplica `between` no campo de tempo do dataset e desce a granularidade (ano → trimestre → mês → dia).
5. **Registros e exportação reutilizam a mesma `effective_spec` do gráfico**, trocando medidas/dimensões por `columns`: o total de registros bate com o número do gráfico. Paginação por `offset` com desempate por `row_key`.
6. **PII:** campo `pii` é mascarado em registros/CSV (`mask_pii`), **não aparece** na lista de campos, busca ou valores distintos, e **não pode ser filtro** para quem não tem `dataset:manage` (filtrar por valor sondaria o dado mascarado). Violação → 422 `pii_filter`.
7. **Exportação CSV:** permissão nova `analysis:export` (Administrador e Editor de Dashboards), limite de 50 000 linhas, neutralização de fórmulas (`csvsafe`), auditoria `analysis.export` (painel, dataset, nº de linhas; sem conteúdo), 10/min por usuário.
8. **Filtros inaplicáveis são visíveis:** o resultado de cada widget traz `ignored_filters` e o card mostra o aviso (RF-09).
9. **Visões salvas** (`analysis_views`, migração 0003): pessoais, estado validado pelo mesmo `Filter`/`Period` do `QuerySpec`, 50 por painel, `ON DELETE CASCADE` com o painel e o usuário.
10. **Movimento com propósito:** indicador deslizante no período, chips que entram/saem, breadcrumb, FLIP do card para a tela cheia, folha lateral, contagem animada, barra de progresso só durante consulta. Tudo respeita `prefers-reduced-motion` (regra global já existente).

## Chat por IA ("Perguntar à IA")

11. **A IA escolhe a consulta; o backend calcula.** `POST /dashboards/{id}/analysis/chat` envia ao modelo só metadados (campos não-`pii` com nome/rótulo/tipo/papel, títulos e conteúdo dos gráficos do painel, período e filtros da tela, data de hoje) e as últimas 8 mensagens. A saída é JSON estrito com uma ação fechada: `show_chart` | `apply_view` | `explain_unsupported` | `clarify`. O backend traduz para `QuerySpec`, valida pela lista branca (`validate_widget`), faz **1 rodada de reparo** com o erro da validação e só então executa. O texto do modelo não carrega números (o prompt proíbe e a UI mostra o gráfico calculado).
12. **Valores de filtro são conferidos no banco, nunca enviados ao modelo.** "parke" → "Parker" é resolvido por busca local nos valores distintos; o ajuste vira nota ao usuário (só quando houve adivinhação; diferença de caixa é silenciosa).
13. **Comparação "mesmo período do ano anterior"** (`QuerySpec.compare_to = "last_year"`, `periods.previous_year`): período aberto compara só o trecho decorrido; períodos fechados deslocam 12 meses (ano bissexto correto).
14. **Autorização:** exige `dashboard:view` + `dataset:view` no dataset (o chat não é atalho para dados de quem só vê painel). Ações do resultado: "Aplicar à tela" (filtros viram chips manuais editáveis) e "Adicionar ao painel" (só com `dashboard:edit`, pelo endpoint de widgets com `If-Match`).
15. **Operação:** 12 perguntas/min por usuário; auditoria `ai.analysis_chat` (modelo, ação, tokens, hash do texto; **o texto não é gravado**); histórico do chat só em `sessionStorage` do navegador (D3). Liga/desliga próprio em Configurações (`analysis_chat`, RF-16) sem afetar a geração de dashboards.
16. **Limites declarados ao usuário (não calcula):** razões entre medidas (margem %, média ponderada), churn/novos×recorrentes, vendidos em conjunto, projeção, causas, cruzar datasets. O modelo deve mostrar a parte calculável (`show_chart`) e dizer o que ficou de fora; recusa só quando não há parte útil.

POC (Etapa 1) e resultados: [`docs/planos/POC-CHAT-ANALISE.md`](../planos/POC-CHAT-ANALISE.md). Reprodutível com `scripts/poc_chat_analise.py`.

## Adiado

- Comparação com período arbitrário (hoje: período anterior ou mesmo período do ano anterior, só em KPI).
- Insights narrativos com dados agregados (opção B do plano): exige decisão D1; o MVP não envia dados ao provedor.
- Painéis já criados em bancos existentes não ganham `drill_path` sozinhos (o seed só cria painéis ausentes): edite o widget ou recrie; sem `drill_path` o drill usa `drill_field`, como antes.

## Consequências

- Contrato OpenAPI: rotas novas sob `/dashboards/{id}/analysis/*` (inclui `chat` e `chat/status`), `DataRequest.overrides/force_period`, `QuerySpec.compare_to`, `analysis_chat` em `/settings/ai` e `ignored_filters` no resultado do widget (aditivos).
- A VPS precisa de saída HTTPS para a Groq (já exigida pelo ADR 0010). Em conta gratuita da Groq o limite de tokens/min é baixo (a POC encontrou 429 a cada poucas perguntas): para uso real, conta paga ou `gpt-oss-20b`.
- Rodar `make migrate` (migração 0003) e `make bootstrap` (permissão `analysis:export` e papel Editor).
- Medição de RNF-01 (p95 ≤ 2 s) **não foi feita** em dataset de referência; só validado manualmente com o relatório real (≈10 mil linhas), sem lentidão perceptível.
