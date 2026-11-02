# GAMA-FEAT-PAINEL-ANALITICO — Painel analítico (desktop) com drill-down, filtros, busca/chat por IA e recursos de BI

| | |
|---|---|
| Projeto | gamatermic-dash |
| Versão | 0.1 (rascunho para decisão) |
| Data | 02/11/2026 |
| Estado | **Etapas 2, 3 e 4 implementadas em 01/11/2026** ([ADR 0012](../adr/0012-painel-analitico.md)). **Etapas 1 (POC de IA) e 5 (chat) não iniciadas**: dependem de chave Groq real e perguntas reais. Decisões pendentes em §14 |
| Fontes | Pedido do usuário; leitura do repositório em 02/11/2026 (`frontend/src/features/{dashboards,widgets,tv-player}`, `backend/app/modules/{query,dashboards,ai}`, `docs/planos/GAMA-FEAT-IA-DASHBOARDS.md`) |

Legenda: **[Dado]** informado pelo usuário · **[Código]** confirmado no repositório · **[Proposta]** decisão sugerida · **[Hipótese]** a validar · **[Pendente]** depende de resposta.

---

## 1. Resumo executivo

- **Problema [Dado]:** hoje o foco do produto é exibir painéis na TV. Quem está no PC só tem a tela `/dashboards/:id` (mesmos widgets da TV, período + clique para filtrar). Falta uma experiência de análise: explorar, cruzar, buscar e perguntar.
- **Proposta:** uma **visão analítica** em rota própria (`/dashboards/:id/analise`), aberta a partir do painel, com layout de desktop: barra de filtros, drill-down hierárquico, widget em tela cheia com tabela de detalhe, busca e **chat por IA** que responde com gráficos/tabelas calculados pelo backend.
- **Princípio-chave [Proposta]:** a IA **nunca calcula nem gera SQL**. Ela traduz a pergunta em `QuerySpec` (contrato fechado já existente), o backend valida e executa. Os números vêm sempre do banco, nunca do texto do modelo.
- **Maior incerteza:** qualidade da IA ao traduzir perguntas livres em `QuerySpec` sobre os datasets reais (e o que pode ser enviado ao provedor). É testada primeiro (Etapa 1, POC), antes de construir a UI do chat.
- **A TV não muda [Código]:** `TvPage` e `/display/*` continuam independentes de IA e dos novos recursos (princípio de IA fora do caminho crítico, já adotado no ADR 0010).

## 2. Situação atual (o que já existe)

| Capacidade | Estado | Evidência |
|---|---|---|
| Drill por clique em barra/pizza/tabela/lista compacta | Existe, **básico** | `DashboardPages.tsx:50` (`drill`), `renderers.tsx:134,154,173`, `compact.tsx:53`, `viz_config.drill_field` |
| Filtros ativos como "chips" removíveis | Existe | `DashboardPages.tsx` (bloco "Filtros ativos") |
| Filtro só `eq`, 1 valor por campo; clicar de novo troca o valor | Limitação | `drill()` substitui o filtro do mesmo campo |
| Filtros globais valem só em widgets que **têm o campo** | Regra existente | `service.py:252` (`compatible`) |
| Drill só nos campos configurados em `drill_field` (1 por widget) | Limitação | `viz_config.drill_field` |
| Linha/KPI/Medidor sem drill | Limitação | só Bar/Pie/Table/compacto chamam `onDrill` |
| Estado de filtro/período só em `useState` (perde ao recarregar, não compartilha link) | Limitação | `DashboardViewPage` |
| `QuerySpec`: medidas, até 3 dimensões, tempo, 20 filtros (`eq,neq,in,gt,gte,lt,lte,between,contains`), `limit` ≤ 5000, período, comparação com período anterior | Base sólida | `query/spec.py` |
| Mascaramento de PII por permissão (`dataset:manage`) | Existe | `service.py:272,304`, `executor.py` |
| IA Groq com saída JSON estrita, validação por lista branca, rate limit 10/min, chave cifrada | Existe | `ai/{groq_client,service,translate}.py`, ADR 0010 |
| IA recebe **só metadados**, nunca linhas | Regra existente | `GAMA-FEAT-IA-DASHBOARDS.md` §2 |
| Chat, histórico, múltiplos turnos, busca textual | **Não existe** | — |
| Exportar dados, salvar visões, favoritos | **Não existe** | — |

## 3. Usuários e casos de uso

| Usuário | Caso de uso | Exemplo concreto |
|---|---|---|
| Gestor/analista no PC | Investigar uma variação vista na TV | "Faturamento caiu em outubro" → clica na barra do mês → vê por cliente → por vendedor → abre as linhas do pedido |
| Gestor | Perguntar em linguagem natural | "Top 10 clientes por faturamento em setembro vs agosto" → recebe gráfico+tabela com os números |
| Gestor | Reaproveitar uma análise | Salva a visão filtrada e manda o link a um colega (que tenha acesso) |
| Editor | Transformar achado em painel | Pelo chat, "adicionar ao painel" leva a proposta ao editor existente |
| Administrador | Controlar IA e custo | Liga/desliga o chat, vê consumo de tokens |

## 4. Escopo

**Entra (MVP em fases, §10):**
1. Rota de análise para desktop com layout próprio (não é a grade da TV).
2. **Filtros ricos:** múltiplos valores (`in`), exclusão (`neq`), intervalo de datas absoluto, comparação com período anterior, filtros por campo do dataset (não só os de `drill_field`), chips editáveis, e estado persistido na URL.
3. **Drill-down aprofundado:** hierarquias de dimensões (ex.: ano → mês → dia; segmento → cliente → pedido), breadcrumb navegável, "voltar um nível", drill em linha/KPI (por ponto da série), e **drill-through** para as linhas de origem (tabela paginada).
4. **Widget em tela cheia** ("expandir") com troca de tipo de visual (barra/linha/pizza/tabela) e de dimensão/medida (agrupar por…), sem alterar o painel salvo.
5. **Busca:** por campo/valor dentro do painel e dataset (ex.: achar cliente "ACME" e aplicar como filtro).
6. **Chat por IA integrado** (painel lateral): pergunta → proposta de visual calculado; ações "aplicar como filtro", "abrir em tela cheia", "adicionar ao painel".
7. **Exportar** a visão atual (CSV do que está na tela) respeitando permissão e PII.
8. **Visões salvas** pessoais (filtros + período + drill) com link.

**Não entra agora (não objetivos):**
- Editor de dataset/ETL, joins entre datasets, campos calculados definidos pelo usuário (futuro, §13).
- Alertas, agendamento de relatórios por e-mail, embed externo.
- SQL livre ou "pergunte ao banco" sem `QuerySpec`.
- Narrativa/insights automáticos escritos pela IA com dados reais (decisão em §14; MVP não envia dados ao provedor).
- Alterar a TV, playlists ou o modelo de publicação.
- App mobile dedicado (a rota deve ser utilizável em tablet, sem garantia de otimização).

## 5. Requisitos

### Funcionais

| ID | Requisito (comportamento observável) | Prio |
|---|---|---|
| RF-01 | No painel, botão "Análise" abre `/dashboards/:id/analise`. Sem `dashboard:view`, retorna acesso negado como hoje. | Alta |
| RF-02 | Filtros e período da análise ficam na URL (query string). Recarregar a página ou abrir o link reproduz a mesma visão. | Alta |
| RF-03 | Usuário adiciona filtro por qualquer campo do dataset (dimensão ou tempo) com operadores `in`, `neq`, `between`, `contains`; os chips mostram campo, operador e valores e são editáveis/removíveis. | Alta |
| RF-04 | Clicar em elemento de gráfico aplica drill: mostra breadcrumb "Visão geral › Sudeste › ACME" e cada migalha volta àquele nível. | Alta |
| RF-05 | Hierarquia de drill configurável por widget (`viz_config.drill_path: [campo1, campo2, ...]`); sem ela, usa `drill_field` atual (compatível). | Alta |
| RF-06 | Em linha/KPI, clicar em um ponto da série aplica filtro de tempo daquele ponto (ex.: mês) e desce a granularidade (mês → dia). | Média |
| RF-07 | Drill-through: ação "Ver registros" abre tabela paginada das linhas do dataset sob os filtros atuais, com ordenação, e colunas `pii` mascaradas conforme permissão. | Alta |
| RF-08 | Widget pode ser expandido em tela cheia; nele o usuário troca tipo de visual e "agrupar por" entre dimensões do dataset. Nada disso grava no painel. | Média |
| RF-09 | Filtro que não se aplica a um widget (dataset sem o campo) é indicado visualmente no widget ("filtro X não se aplica"), em vez de silencioso. | Média |
| RF-10 | Busca global: digitar texto lista campos e valores correspondentes (valores via consulta `contains` limitada); escolher um valor adiciona o filtro. | Média |
| RF-11 | Chat: o usuário escreve uma pergunta; a resposta mostra (a) visual/tabela computados pelo backend, (b) o filtro/período/medidas interpretados em texto legível, (c) ações "aplicar à visão", "adicionar ao painel". | Alta |
| RF-12 | Chat mantém contexto de turnos recentes (ex.: "e só do Sul?") e conhece a visão atual (filtros/período/widget em foco). | Alta |
| RF-13 | Pergunta fora do escopo ou impossível (campo inexistente, dado ausente) recebe recusa explicativa e sugestões de campos reais, sem inventar números. | Alta |
| RF-14 | Exportar CSV da tabela/visual atual, limitado a N linhas (proposta: 50 000) e com PII mascarada igual à tela. | Média |
| RF-15 | Visões salvas: nomear, listar, abrir, excluir; pertencem ao usuário; abrir exige acesso ao painel. | Média |
| RF-16 | Admin pode desligar o chat sem afetar o resto da análise. | Alta |

### Não funcionais

| ID | Requisito | Verificação |
|---|---|---|
| RNF-01 | Interação de drill/filtro atualiza widgets em até 2 s (p95) em dataset de referência (**[Hipótese]** volume a medir; hoje não há baseline). | Experimento na Etapa 2 com dataset real do cliente |
| RNF-02 | Nenhuma consulta fora de `QuerySpec`: todo caminho novo passa por `validate_spec`/lista branca de `dataset_fields`. | Teste de integração com campo inexistente → 422 |
| RNF-03 | Campos `pii` nunca vão ao provedor de IA e seguem mascarados na tela/exportação conforme `dataset:manage`. | Teste automatizado; revisão do prompt |
| RNF-04 | Chat com rate limit por usuário e orçamento de tokens configurável. | Teste de integração |
| RNF-05 | Acessibilidade: navegação por teclado nos chips, breadcrumb, painel de chat; foco gerenciado ao abrir/fechar tela cheia. | Testes de componente + checagem manual |
| RNF-06 | Tema claro/escuro e tokens existentes; sem estilos novos fora do Tailwind/CSS vars atuais. | Revisão |
| RNF-07 | TV inalterada: testes de `TvPage` e `/display/*` continuam passando; bundle da TV não carrega código do chat (lazy-load da rota de análise). | Suíte existente + inspeção do bundle |

## 6. Jornada e experiência

**Fluxo principal:** Painel → "Análise" → tela com (topo) período + comparação + chips de filtro + busca; (centro) grade responsiva dos widgets em tamanho de desktop; (direita, recolhível) chat. Clicar em barra → drill + breadcrumb; menu do widget → "Expandir", "Ver registros", "Exportar", "Perguntar à IA sobre este gráfico".

**Estados a cobrir:** carregando (mantém dado anterior, como `placeholderData` atual); vazio ("nenhum registro para estes filtros" + botão limpar); parcial (alguns widgets com erro, `result.error` já existe); erro de IA (chave inválida, timeout, limite — erros `ai_*` já mapeados); IA desligada (chat oculto com aviso ao admin); acesso negado; filtro inaplicável (RF-09).

**Regras de UX:** desfazer = breadcrumb + botão "voltar"; "Limpar tudo" restaura a visão salva do painel; trabalho do chat não se perde ao navegar entre níveis de drill (histórico na sessão).

## 7. Arquitetura

### 7.1 Frontend **[Proposta]**
- Nova feature `frontend/src/features/analysis/` (rota lazy `/dashboards/:id/analise`), reutilizando `WidgetCard`, `renderers.tsx`, `Chart.tsx`, `useDashboard`, `useDashboardData`.
- Estado de visão (`period`, `filters[]`, `drillStack[]`, `focusWidgetId`) em um hook `useAnalysisState` sincronizado com a URL (React Router `useSearchParams`); Zustand só para o que não vai na URL (chat aberto/fechado).
- Estender `Filter` do front para `op` completo e `value` lista.
- `onDrill` passa a receber contexto (`{field, value, widgetId}`) em vez de só `(field, value)`; manter assinatura antiga funcionando para TV/painel atual.

### 7.2 Backend **[Proposta]**
Novos endpoints sob `/api/v1`, todos com `Principal` e `view` do painel; nenhum exige alterar `/display/*`.

| Endpoint (proposto) | Função | Observação |
|---|---|---|
| `POST /dashboards/{id}/analysis/query` | Executa um `QuerySpec` derivado de um widget com `group_by`/tipo/filtros trocados (RF-06/08) | Reusa `_apply_overrides`; só campos do dataset do widget |
| `POST /dashboards/{id}/analysis/records` | Drill-through paginado (RF-07) | Cursor/offset, `limit` ≤ 200 por página, PII mascarada |
| `GET /datasets/{id}/fields/{campo}/values?q=` | Valores distintos p/ filtros e busca (RF-03/10) | Limite 50, `contains`, sem PII, cache curto |
| `POST /dashboards/{id}/analysis/export` | CSV (RF-14) | Streaming; auditar quem exportou, sem conteúdo |
| `POST /ai/analysis-chat` | Chat (RF-11..13) | Ver §7.3 |
| `GET/POST/DELETE /dashboards/{id}/views` | Visões salvas (RF-15) | Tabela nova (§8) |

Mudanças em código existente: `viz_config` ganha `drill_path` (validar em `widget_types.py`); `Filter` aceita lista em `in`/`between` (já suportado pelo schema, falta UI); novo parâmetro opcional `comparison` em `DataRequest` se for preciso comparar com período arbitrário (hoje só "período anterior").

### 7.3 Chat por IA — desenho **[Proposta]**

Fluxo por turno:
1. Front envia `{dashboard_id, message, history[últimos N turnos], view_state{period, filters, focus_widget_id}}`.
2. Backend monta o prompt com **metadados** (campos, rótulos, tipos, papéis, exceto `pii`; os `widgets` do painel e suas medidas) + histórico + estado da visão — como no ADR 0010.
3. Groq responde em JSON estrito com uma **ação** (união fechada): `show_chart {type, query_spec}` · `apply_filters {filters, period}` · `explain_unsupported {reason, suggestions}` · `clarify {question}`.
4. `translate.py`/`validate_spec` valida (lista branca, limites). Inválido → uma tentativa de reparo com o erro de validação; persistindo, devolve `explain_unsupported`.
5. Backend **executa** o `QuerySpec` validado com `executor.execute(..., mask_pii=...)` e devolve `{interpretation_text, widget_preview{type, query_spec, result}}`.

Alternativas relevantes:

| Opção | Prós | Contras | Recomendação |
|---|---|---|---|
| **A. IA → `QuerySpec` (sem dados no prompt)** | Mantém regra de privacidade atual; números sempre do banco; barato | Não "explica" resultados; depende da tradução | **MVP** |
| B. A + IA resume os resultados agregados (mascarados, truncados) | Insights em texto | Envia dados de negócio a terceiro; custo; risco de texto divergir dos números | Fase posterior, atrás de flag e decisão explícita (§14-D1) |
| C. IA gera SQL | Flexível | Viola princípio "sem SQL livre"; risco de segurança | **Rejeitada** |

**Segurança específica do chat:** valores vindos de dados (nomes de cliente etc.) não entram no prompt no MVP, então injeção via dados não se aplica; o texto do usuário é tratado como entrada e só pode resultar em ações da união fechada; prompts não são persistidos (mantém regra atual), só tokens/modelo/painel são auditados; host do provedor fixo (sem SSRF).

**Histórico:** MVP guarda em memória do cliente (sessionStorage) e envia só os N últimos turnos; sem tabela de conversa (alinhado ao anti-escopo "sem rascunhos"). Persistência é decisão pendente (§14-D3).

## 8. Modelo de dados

Única tabela nova no MVP completo **[Proposta]**:

`analysis_view` — `id (uuid)`, `dashboard_id (FK, ON DELETE CASCADE)`, `owner_user_id (FK)`, `name`, `state (JSONB: period, filters, drill_stack, focus_widget_id)`, `created_at/updated_at` (`TimestampMixin`).
- Validação do `state` com o mesmo `Filter`/`Period` do `QuerySpec` (não aceitar JSON arbitrário).
- Unicidade `(dashboard_id, owner_user_id, name)`.
- Migração Alembic nova; reversível (drop da tabela). Sem alteração em tabelas existentes (`drill_path` vive no JSONB `viz_config`, sem migração; dados antigos continuam válidos).
- Fonte de verdade dos dados continua `DatasetRow`; nada é cacheado como autoritativo.

## 9. Segurança e privacidade

| Tema | Regra proposta |
|---|---|
| Autorização | Todos os endpoints novos checam `view` do painel e do dataset (`ResourceGrant`/RBAC existentes). Visão salva só abre se o usuário ainda tem acesso. |
| PII | `mask_pii=not p.has("dataset:manage")` em consulta, registros, exportação e valores distintos; campos `pii` excluídos do prompt e da busca de valores. |
| Exportação | Permissão explícita nova `analysis:export` **[Proposta]**; auditoria (usuário, painel, nº linhas, hora; sem conteúdo). |
| IA | Chave Groq já cifrada; rate limit próprio; limite de tokens por turno; prompt não persistido; erros do provedor não viram 401. |
| Abuso/custo | `limit` ≤ 5000 do `QuerySpec`; paginação em registros; limite de tamanho do histórico enviado. |
| Valores distintos | Sem PII, com limite e `contains` parametrizado (lista branca de campo) — sem concatenar SQL. |

## 10. Execução incremental

Ordem por risco: primeiro a incerteza da IA e a base de filtros/URL, depois UI pesada.

### Etapa 1 — POC: tradução pergunta → `QuerySpec` (maior incerteza)

| Campo | Conteúdo |
|---|---|
| Objetivo | Medir se Groq (modelos já na allowlist) traduz perguntas reais para `QuerySpec` válidos e corretos, com o contexto do painel |
| Pré-requisitos | Chave Groq real em ambiente de teste; dataset real (ou fiel) do cliente; lista de ~30 perguntas reais fornecida por usuários (**[Pendente]**) |
| Ações | - [ ] Redigir 30 perguntas (simples, com período, comparação, ranking, follow-up, impossíveis) com resultado esperado definido por pessoa<br>- [ ] Criar script de avaliação (fora do produto) que chama o prompt proposto e valida via `validate_spec`<br>- [ ] Medir: % válido, % correto (confere com resposta esperada), recusas corretas, latência, tokens |
| Entregáveis | Relatório curto com métricas, prompt/schema candidatos, decisão |
| Validação | Rodar o conjunto 3 vezes e verificar variação entre rodadas |
| Critério de saída | **Continuar** se ≥ 80 % válidas e ≥ 70 % corretas e p95 de latência ≤ 8 s (**metas propostas**, sem baseline); **adaptar** (ex.: menos liberdade na união de ações) entre 50–80 %; **interromper o chat** (manter o resto da feature) abaixo disso |
| Dependências | Conta Groq real e perguntas reais (usuário/negócio) |

### Etapa 2 — Fundações de filtro e URL (valor imediato, sem IA)

| Campo | Conteúdo |
|---|---|
| Objetivo | Estado de visão na URL e filtros ricos, no painel atual e na nova rota |
| Pré-requisitos | Nenhum |
| Ações | - [ ] Estender tipo `Filter` no front (`in`, `neq`, `between`, `contains`)<br>- [ ] Hook `useAnalysisState` + serialização na URL<br>- [ ] Componente de barra de filtros com chips editáveis e seletor de campo/valor<br>- [ ] Endpoint de valores distintos (RF-03)<br>- [ ] Indicação de filtro inaplicável (RF-09)<br>- [ ] Medir latência de `/dashboards/{id}/data` com 3 filtros em dataset real (baseline p/ RNF-01) |
| Entregáveis | Rota `/dashboards/:id/analise` (lazy) com filtros funcionando; endpoint; testes |
| Validação | Aplicar 3 filtros, copiar URL, abrir em outra aba logada → mesma visão e mesmos números; filtro em campo inexistente → 422 tratado |
| Critério de saída | RF-02, RF-03, RF-09 aceitos; baseline de RNF-01 registrado |
| Dependências | — |

### Etapa 3 — Drill-down aprofundado e drill-through

| Campo | Conteúdo |
|---|---|
| Objetivo | Navegar por hierarquias e chegar às linhas de origem |
| Pré-requisitos | Etapa 2 |
| Ações | - [ ] `viz_config.drill_path` no backend (validação) e no front; retrocompatível com `drill_field`<br>- [ ] `drillStack` + breadcrumb + voltar<br>- [ ] Drill em linha/KPI (RF-06) com descida de granularidade<br>- [ ] Endpoint e tabela de registros paginada (RF-07)<br>- [ ] Seed/definições dos painéis padrão com `drill_path` (`bootstrap/definitions.py`) |
| Entregáveis | Drill multinível, drill-through, testes |
| Validação | Drill 3 níveis e voltar por breadcrumb restaura filtros exatos; registros respeitam PII (usuário sem `dataset:manage` vê "•••"); painel antigo com só `drill_field` segue funcionando |
| Critério de saída | RF-04..RF-07 aceitos; TV sem regressão (RNF-07) |
| Dependências | Definir hierarquias reais por painel com o negócio (**[Pendente]**) |

### Etapa 4 — Tela cheia, busca, exportação e visões salvas

| Campo | Conteúdo |
|---|---|
| Objetivo | Completar os recursos de BI sem IA |
| Pré-requisitos | Etapa 3 |
| Ações | - [ ] Modo expandir com troca de visual e "agrupar por" (RF-08)<br>- [ ] Busca global (RF-10)<br>- [ ] Exportação CSV + permissão + auditoria (RF-14)<br>- [ ] Tabela `analysis_view`, migração, API e UI (RF-15) |
| Entregáveis | Funcionalidades + migração + testes |
| Validação | Exportar com PII mascarada confere com a tela; visão salva reabre idêntica; excluir painel remove as visões (cascade) |
| Critério de saída | RF-08, RF-10, RF-14, RF-15 aceitos |
| Dependências | Decisão de limite/permissão de exportação (§14-D4) |

### Etapa 5 — Chat por IA integrado (condicional ao resultado da Etapa 1)

| Campo | Conteúdo |
|---|---|
| Objetivo | Chat lateral que responde com visuais calculados |
| Pré-requisitos | Etapa 1 com "continuar/adaptar"; Etapa 2 (estado de visão) |
| Ações | - [ ] Endpoint `/ai/analysis-chat` com união de ações, reparo de 1 tentativa, rate limit e tokens<br>- [ ] Painel de chat (histórico em sessão, estados de erro/IA desligada)<br>- [ ] Ações "aplicar à visão", "abrir em tela cheia", "adicionar ao painel" (reusa fluxo do `AiEditPage`/editor)<br>- [ ] Contexto da visão atual e do widget em foco (RF-12)<br>- [ ] Flag de configuração (RF-16) em `/configuracoes` |
| Entregáveis | Chat funcional com Groq falsa nos testes e Groq real na validação manual |
| Validação | Conjunto de perguntas da Etapa 1 rodado pela UI; pergunta impossível → recusa com sugestões; follow-up usa contexto; chave inválida → erro tratado sem 401 |
| Critério de saída | RF-11..RF-13, RF-16 aceitos; RNF-03/04 verificados |
| Dependências | Etapa 1; ADR da IA conversacional (§12) |

### Etapa 6 — Endurecimento e lançamento
- [ ] Acessibilidade (RNF-05), temas, responsividade em tablet
- [ ] Runbook/README atualizados; ADR registrado
- [ ] Lançamento gradual (§12)

**Estimativa [Hipótese, a refinar após a Etapa 1]:** Etapa 1: 2–3 dias; 2: 4–6; 3: 5–8; 4: 5–8; 5: 6–10; 6: 2–4 (dias úteis de 1 pessoa full-stack, sem espera de aprovações). Premissa: equipe de 1–2 pessoas já familiar com o código.

## 11. Testes e validação

| Requisito | Teste | Nível |
|---|---|---|
| RF-02 | Abrir URL com filtros e conferir chips e resultado | Componente + E2E (Playwright) |
| RF-03, RNF-02 | Filtro em campo inexistente/PII → 422/ignorado | Integração backend |
| RF-04..06 | Drill 3 níveis, voltar, drill em série temporal | Componente (Vitest + MSW) |
| RF-07, RNF-03 | Registros paginados com PII mascarada para usuário sem `dataset:manage` | Integração backend |
| RF-09 | Widget de dataset sem o campo mostra aviso | Componente |
| RF-11..13 | Chat com Groq falsa (padrão de `test_ai.py`): ação válida, inválida→reparo, impossível→recusa | Integração backend |
| RF-14 | CSV tem N linhas esperadas e PII mascarada; auditoria criada | Integração |
| RF-15 | CRUD e isolamento por usuário | Integração |
| RNF-01 | Medição de latência com dataset de referência | Experimento manual |
| RNF-07 | Suíte atual da TV/display inalterada | Regressão (`make test`) |

Dados: massa sintética para unitário; dataset real autorizado só para a POC e medição de desempenho.

## 12. Operação e lançamento

- **Feature flag** em Configurações (liga/desliga chat, RF-16); a rota de análise pode ser liberada por permissão (`dashboard:view`) e o botão "Análise" por flag de ambiente inicialmente.
- **ADR novo (0012) [Proposta]:** "Análise interativa e IA conversacional" — registra: IA → `QuerySpec`, sem dados ao provedor no MVP, sem persistência de conversa, TV independente.
- **Migração:** só `analysis_view`; rollback = downgrade Alembic. Desligar a UI não apaga dados das visões.
- **Observabilidade:** reutilizar auditoria (tokens/modelo/painel por turno; exportações); métricas: latência de `/analysis/*`, taxa de ação inválida no chat, uso de drill-through.
- **Compatibilidade:** `drill_field` continua válido; `DashboardViewPage` não é removida.
- **Suporte:** atualizar `docs/runbooks` (troubleshoot: chat sem resposta, chave Groq, limites).

## 13. Riscos

| Risco | Impacto | Mitigação | Sinal |
|---|---|---|---|
| IA traduz mal perguntas livres | Chat inútil/enganoso | POC antecipada; união fechada de ações; sempre mostrar a interpretação em texto; recusa explícita | % válido/correto < meta na Etapa 1 |
| Consultas pesadas ao filtrar/drill | Lentidão, carga no Postgres | Baseline na Etapa 2; limites de `limit`/páginas; índice em campos de filtro frequentes se necessário (a avaliar) | p95 > 2 s |
| JSONB em `DatasetRow` limita agregações por campos arbitrários | Desempenho ruim em datasets grandes | Medir; avaliar índices/expressões; manter volume como premissa | Plano de execução lento |
| Vazamento de PII (tela, CSV, prompt) | Alto | `mask_pii` em todos os caminhos, testes dedicados, revisão do prompt | Teste RNF-03 falhando |
| Custo de tokens | Orçamento | Rate limit, histórico curto, modelo `20b` como opção | Consumo/dia |
| Escopo "BI" crescer sem fim | Atraso | Não objetivos explícitos (§4); roadmap separado | Pedidos de joins/campos calculados |
| Hierarquias de drill não refletem o negócio | Baixo valor | Validar com gestores antes da Etapa 3 | Feedback no piloto |

### Roadmap (não é compromisso)
Campos calculados e métricas nomeadas · insights narrativos (opção B) com dados agregados · alertas por limiar · agendamento/envio de relatórios · comparação com período arbitrário · joins entre datasets · compartilhar visões com outros usuários/grupos.

## 14. Decisões pendentes

| # | Decisão | Recomendação | Quem decide | Evidência necessária |
|---|---|---|---|---|
| D1 | Enviar dados agregados ao provedor de IA para gerar insights em texto? | Não no MVP (opção A) | Dono do produto + responsável por privacidade | Política de dados do cliente; termos do provedor (consultar fonte oficial antes) |
| D2 | Perguntas reais e dataset de referência para a POC | Coletar 30 perguntas de 3–5 gestores | Negócio | Lista fornecida |
| D3 | Persistir conversas do chat? | Não (sessão); revisar se pedirem auditoria/continuidade | Dono do produto | Pedido real de usuários |
| D4 | Quem pode exportar e qual limite de linhas? | Permissão `analysis:export`, 50 000 linhas | Dono do produto/segurança | Regra interna |
| D5 | Hierarquias de drill por painel padrão | Definir com gestores | Negócio | Lista campo→campo por painel |
| D6 | Mesma rota para PC e TV ou rotas separadas? | **Separadas** (TV intacta) | Confirmado pelo pedido ("abertura de painel para PC") — [Dado] com interpretação | — |

## 15. Rastreabilidade (requisito → etapa → teste → aceite)

| Requisito | Etapa | Teste | Aceite (resumo) |
|---|---|---|---|
| RF-01, RF-02 | 2 | E2E URL | Link reabre a mesma visão |
| RF-03, RF-09, RF-10 | 2, 4 | Integração + componente | Filtro por qualquer campo permitido; aviso quando inaplicável |
| RF-04..RF-07 | 3 | Componente + integração | Breadcrumb restaura estado; registros mascarados |
| RF-08, RF-14, RF-15 | 4 | Componente + integração | Tela cheia sem alterar painel; CSV = tela; visão reabre igual |
| RF-11..RF-13, RF-16 | 1, 5 | Integração com Groq falsa + validação manual | Resposta calculada pelo backend; recusa sem inventar |
| RNF-01 | 2 | Experimento | p95 ≤ 2 s no dataset de referência |
| RNF-02, RNF-03 | 2–5 | Integração | 422 em campo inválido; PII nunca no prompt/CSV sem permissão |
| RNF-07 | todas | Regressão | TV sem mudanças |

## 16. Definição de pronto

- [ ] Requisitos da etapa aceitos com evidência (teste/manual registrada)
- [ ] `make test` backend e frontend verdes; sem regressão em TV/display
- [ ] ADR 0012 e README/runbooks atualizados
- [ ] Revisão de segurança dos endpoints novos (PII, autorização, rate limit)
- [ ] Migração testada (upgrade e downgrade)

## 17. Referências

- Internas (confirmadas em 02/11/2026): `docs/adr/0010-ia-geracao-de-dashboards.md`, `docs/adr/0011-graficos-adaptaveis-e-autosave-do-layout.md`, `docs/planos/GAMA-FEAT-IA-DASHBOARDS.md`.
- Externas: nenhuma consultada neste rascunho. Antes da Etapa 5, consultar a documentação oficial da Groq (structured outputs, limites, preços, política de dados) e registrar data/versão **[Pendente]**.
