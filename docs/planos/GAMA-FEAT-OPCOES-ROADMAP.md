# GAMA-FEAT-OPCOES-ROADMAP — Opções de features e decisões tecnológicas

| | |
|---|---|
| Projeto | gamatermic-dash |
| Versão | 0.1 |
| Data | 02/11/2026 |
| Estado | **Proposta** — catálogo de candidatas para decisão de roadmap; nenhuma implementada |
| Fontes | Revisão do repositório em 02/11/2026: módulos, ADRs 0002/0006/0008/0010/0012, `docs/planos/GAMA-FEAT-IA-DASHBOARDS.md`, `GAMA-FEAT-PAINEL-ANALITICO.md` (§13–14), `POC-CHAT-ANALISE.md`, `docs/adr/0000-desvios-do-plano.md`, `.claude/CLAUDE.md`, `README.md` |

Legenda: **[Código]** confirmado no repositório · **[ADR]/[Plano]** decisão registrada em documento interno · **[Proposta]** recomendação deste documento · **[Pendente]** depende de evidência/fonte externa

---

## 1. Resumo executivo

O sistema tem o núcleo maduro: ingestão idempotente, query engine sem SQL livre, dashboards publicáveis, TV com pareamento, painel analítico completo e chat "Perguntar à IA". A carência atual não está no núcleo, e sim no **operacional e proativo**:

- Dados só entram por **carga manual** (`schedule_cron` existe no modelo mas nenhum código agenda) — o badge de "dado velho" existe mas nada age sobre ele.
- Nada **acorda o gestor**: sem alertas, sem relatórios agendados, sem insights.
- O **chat recusa legitimamente** perguntas com medidas derivadas (ex.: margem %) porque não existem campos calculados.
- O **adendo Ploomes** (ADR 0008) está definido mas parado no spike de documentação.
- Carências operacionais: Docker de produção nunca executado, TV nunca validada em hardware real, qualidade da IA nunca medida com chave real.

**Recomendação deste documento:** priorizar (1) agendamento de cargas, (2) campos calculados e métricas nomeadas, (3) spike do conector Ploomes — executando em paralelo a POC do chat (30 perguntas reais). Ficam para a fase seguinte alertas por limiar e relatórios agendados; insights narrativos e joins entre datasets ficam condicionados a evidência.

Toda candidata que fere o anti-escopo do plano técnico (alertas, campos calculados, relatórios, insights, compartilhar visões) **exige ADR novo** antes de implementar — regra registrada no `.claude/CLAUDE.md`: "escopo que antecipe fase ou viole princípio → parar e dizer o conflito, em vez de codar em volta".

## 2. Tabela comparativa das candidatas

| # | Candidata | Problema que resolve | Valor | Esforço | Incerteza maior | Decisão tecnológica central | Requer ADR |
|---|---|---|---|---|---|---|---|
| A | Agendamento de cargas | Dados desatualizados por carga manual | Alto | M | Pouca (já há fila e worker) | Scheduler dentro do worker atual, enfileirando na fila Postgres existente | Leve |
| B | Conector Ploomes (pull incremental) | Fim do processo manual de exportar XLSX | Alto | L | **Alta** — API Ploomes não verificada | Pull incremental com cursor (`ingestion_runs.cursor_state`), contrato do ADR 0008 | ✓ (0008 existe, falta spike) |
| C | Alertas por limiar | Gestor não é avisado quando KPI sai do normal | Médio-alto | M | Quais limiares; canal de entrega | Avaliação reaproveitando o query executor; eventos append-only; canal in-app primeiro | ✓ (anti-escopo) |
| D | Relatórios agendados por e-mail | Gestor precisa abrir o painel para ver números | Médio | M | Formato entrega; SMTP | Entrega CSV/HTML via fila + worker; **PDF fica de fora** (anti-escopo) | ✓ (anti-escopo) |
| E | Campos calculados e métricas nomeadas | Chat e análise recusam "margem %" / "ticket médio" | Alto | L | Ordem de cálculo e performance em JSONB | Expressões declarativas validadas no servidor, executadas no compilador — sem SQL livre | ✓ (anti-escopo) |
| F | Insights narrativos (IA → texto) | Painel mostra número, não conta a história | Médio | S | **D1** — autorizar enviar agregados ao provedor | Reusa chat/cache Groq; decisão de produto sobre dados enviados (§4.1) | ✓ (política de dados) |
| G | Compartilhar visões salvas | Visão útil de um gestor não alcança os outros | Médio | S | Pouca (RBAC já existe) | Grants existentes (`ResourceGrant`) sobre `AnalysisView` | Leve |
| H | Comparação com período arbitrário | Só há "período anterior" e "ano anterior" fixos | Médio | S | Pouca | Estender `QuerySpec`/`periods.py` com período livre | Não (evolução ADR 0012) |
| I | Joins entre datasets | Análises cruzam fontes (vendas × propostas) | Alto | XL | **Alta** — impacta o query engine inteiro | Adiar; construir após evidência de volume (typed table, ADR 0002) | ✓ |

Esforço: S (1–2 semanas) · M (2–4 semanas) · L (4–8 semanas) · XL (8+ semanas) — intervalos com premissa de 1 dev full-time; sem promessa de data.

## 3. Fichas por candidata

### A. Agendamento de cargas

- **Problema [Código]:** `DataSource.schedule_cron` existe no modelo (`datasets/models.py:30`) mas nenhum código agenda; a carga é manual (upload ou `make import`). O sistema sabe quando o dado está velho (`freshness_sla_seconds` → badge "stale" em `datasets/service.py:37` e na TV em `display/router.py:87`) mas não faz nada a respeito.
- **Valor:** dados sempre frescos para painéis e TV; elimina o processo manual recorrente; base para alertas (C) e SLAs de frescor visíveis.
- **O que entra:** definição de recorrência por fonte (cron) na tela de dataset; tick de agendamento no worker que enfileira jobs de `run_ingestion` existentes; estado de "próxima carga" e histórico de execuções no UI.
- **Decisão tecnológica [Proposta]:** **sem nova dependência de infraestrutura** — o worker (`workers/runner.py`) já roda um loop com ticks de 60 s (`housekeeping`) e 6 h (`purge`); adicionar um tick de scheduler que avalia os `schedule_cron` e enfileira. Parse do cron com biblioteca `croniter` (dependência leve de Python) ou expressões simples de intervalo (a cada N dias/horas) no MVP.
  - Alternativas: processo APScheduler separado (mais um processo para operar), Celery/Redis (fora — anti-escopo explícito). Consequência de não fazer: dados continuam manuais.
- **Concorrência:** já resolvida pela fila (`claim_next` com `FOR UPDATE SKIP LOCKED`) e pela idempotência por `row_key` — cargas simultâneas do mesmo dataset são inofensivas, mas o MVP deve evitar disparos duplicados (checar `IngestionRun` em execução).
- **Maior incerteza [Proposta]:** nenhuma técnica real — é adicionar um tick a código que já existe. Validação: agendar carga diária em ambiente dev e observar 3 execuções sem intervenção.
- **Referências:** `datasets/models.py:30`, `workers/runner.py`, `workers/tasks.py:run_ingestion`, `ingestion/router.py`.

### B. Conector Ploomes (pull incremental)

- **Problema [ADR]:** o relatório de vendas é exportado do Ploomes em XLSX e carregado manualmente; o adendo (ADR 0008) definiu o contrato do conector mas está **pendente de spike** de documentação.
- **Valor:** fim do processo manual; dados mais atuais entre cargas; desbloqueia alertas com baixa latência.
- **O que entra (já definido no ADR):** pull incremental de Negócios/Propostas com cursor em `ingestion_runs.cursor_state`, segredos cifrados (`crypto.py`), proteção SSRF (allowlist, bloqueio de IPs privados, sem redirect para rede interna), backoff com `Retry-After`.
- **Decisões tecnológicas a verificar na documentação oficial [Pendente]:** autenticação (token vs OAuth), paginação, limites de requisição, campos de negócio, disponibilidade de webhooks. **Webhook fica fora do MVP** (anti-escopo): pull é a primeira entrega.
- **Maior incerteza:** a API em si — por isso o ADR manda fazer o spike **antes** de codar. Critério de saída do spike: tabela com autenticação, paginação, limites, campos e custo estimado por sincronização, com data de consulta e versão da doc.
- **Consequência de atrasar:** a carga manual continua; a Fase 2 fica estacionada.
- **Referências:** `docs/adr/0008-conectores-ploomes-omie.md`, `modules/connectors/base.py`, `modules/connectors/csv_upload.py`.

### C. Alertas por limiar

- **Problema [Plano §13]:** o gestor só percebe um KPI fora do controle quando abre o painel.
- **Valor:** médio-alto — vira o "vigia" do negócio; depende de dados frescos (A) para ser útil.
- **O que entra:** regra de alerta = consulta existente (`QuerySpec`) + limiar/operador + janela; avaliação periódica pelo worker reutilizando o executor; eventos em tabela append-only (`alert_events`); **canal in-app primeiro** (badge/feed), e-mail fica para D; WhatsApp é anti-escopo e não entra.
- **Decisão tecnológica [Proposta]:** reutilizar `compiler.py`/`executor.py` para avaliar a regra — a agregação é exatamente a mesma do painel, não há lógica nova de métricas; persistência `alert_rules` + `alert_events` (append-only, coerente com a auditoria); avaliação com intensidade configurável (ex.: a cada 15 min para vendedores críticos).
- **Maior incerteza [Proposta]:** definição de limiares (depende dos gestores) — não bloquear: começar com regras de exemplo e deixar a criação na UI.
- **Referências:** `query/{spec,compiler,executor}.py`, roadmap §13 do plano do painel analítico, anti-escopo em `.claude/CLAUDE.md`.

### D. Relatórios agendados por e-mail

- **Problema [Plano §13]:** quem dirige não abre o painel todo dia — receber periodicamente o resumo agrega valor.
- **Valor:** médio; baixo custo incremental se houver filtro de agendamento e destinos por grupo (RBAC).
- **O que entra:** agendamento de envio de uma visão salva (ou dashboard) por e-mail; geração do conteúdo no worker; destinos por grupo/permissão.
- **Decisão tecnológica [Proposta]:** **entrega em CSV/HTML, não PDF** — PDF exigiria headless browser/impressão no backend (dependência pesada, fora do estilo do projeto; e "export PDF/PNG" é anti-escopo do MVP). HTML já é renderizável por qualquer cliente e reutiliza o layout do painel. Se houver pedido real de PDF, abrir ADR específico; não antecipar.
- **Maior incerteza:** SMTP do cliente (provedor, limites, SPF/DKIM) — validar em spike curto antes de construir.
- **Referências:** roadmap §13, `modules/settings`, `modules/query`.
- **Nota:** candidata D e C compartilham infra (agendamento, fila, worker) — se ambas forem aprovadas, planejar juntas para não duplicar mecanismo de recorrência.

### E. Campos calculados e métricas nomeadas

- **Problema [Código/Plano]:** o chat inimiza recusas legítimas: "margem %", "ticket médio" não existem como campos nem medidas derivadas (`POC-CHAT-ANALISE.md` sinaliza; `Gallery`/`chat.py` recusa sem inventar). O gestor não pode expressar a métrica que o negócio usa.
- **Valor:** alto — desbloqueia o chat e o painel analítico para a linguagem do negócio; beneficia todos os consumidores (dashboard, análise, TV, exportações).
- **O que entra:** definição de campos calculados no schema do dataset (`DatasetField` com `computed_from` + expressão), validação no servidor, execução no compilador sem SQL livre; medidas nomeadas = calculadas sobre agregações existentes (ex.: `sum(vendas)/count(propostas)`).
- **Decisão tecnológica [Proposta]:** expressões **declarativas** (não código arbitrário): grammar pequena (operadores aritméticos, referência a campos, funções `sum/avg/count`, divisão segura por zero), validadas com a mesma lista branca de `dataset_fields`; **não materializar** no MVP — calcular na consulta; reavaliar materialização se a typed table (Fase 3, ADR 0002) for acionada por p95.
  - Alternativa: materializar colunas em tabela tipada agora — antecipa a Fase 3 sem evidência de volume; não recomendado.
  - Consequência de não fazer: chat continua recusando as perguntas financeiras mais comuns; gestores fazem a conta na calculadora.
- **Maior incerteza [Proposta]:** performance de cálculo sobre JSONB em datasets grandes (mitigar com ordem de cálculo e limites; medir) e semântica de divisão por zero / campos nulos (definir regras no aceite).
- **Referências:** `POC-CHAT-ANALISE.md`, `query/compiler.py`, `datasets/models.py:24-30`, `.claude/CLAUDE.md` princípios 2 (sem SQL livre) e 9 (tempo/valores).

### F. Insights narrativos (IA → texto)

- **Problema [Plano §14-D1]:** o painel mostra os números; a história do "porquê" fica com o analista.
- **Valor:** médio — depende da qualidade da IA com dados agregados e da aceitação do negócio.
- **O que entra:** opção B do plano (enviar **agregados** ao provedor, nunca linhas/PII) + renderização de texto no painel com os números calculados localmente.
- **Decisões tecnológicas [Proposta]:** **D1 é decisão de produto e política de dados, não técnica** — recomenda-se autorizar apenas agregados (nunca linhas nem campos `pii`), e registrar no ADR a finalidade e a retenção; reusar o cache de respostas de 30 min do chat (já existe) e a flag `analysis_chat`.
- **Maior incerteza:** qualidade real — só mede com chave Groq real (Etapa 0 pendente em `GAMA-FEAT-IA-DASHBOARDS.md` §15) e com as 30 perguntas da POC (D2).
- **Referências:** `GAMA-FEAT-PAINEL-ANALITICO.md` §13–14 (D1), `POC-CHAT-ANALISE.md`, `analysis/chat.py`.

### G. Compartilhar visões salvas

- **Problema [Plano §13]:** a visão analítica que um gestor montou (filtros, drill, agrupamento) é pessoal (`AnalysisView`); colegas do mesmo setor repetem o trabalho.
- **Valor:** médio; custo baixo — RBAC e grants já existem para outros recursos.
- **Decisão tecnológica [Proposta]:** `ResourceGrant` existente (tipo de recurso novo `analysis_view`) com escopo `sector`; exibir "visões compartilhadas" no menu de visões; leitura não altera o modelo de autorização atual.
- **Referências:** `iam/{models,service}.py` (grants), `analysis/views` (`AnalysisView`), sistema de setores (commit "troca de setor").

### H. Comparação com período arbitrário

- **Problema [Plano §13]:** hoje só existem presets "período anterior" e "ano anterior" (`compare_previous_period`/`compare_to`).
- **Valor:** médio — responde "como foi vs. mesmo período do ano passado" e outros recortes que o gestor pedir.
- **Decisão tecnológica [Proposta]:** estender `QuerySpec` com período livre de comparação (datas explícitas), reutilizando `periods.py` e o cálculo de delta já existente; UI no controle de período do painel analítico. Sem mudança de arquitetura.
- **Referências:** `query/spec.py`, `query/periods.py`, `GAMA-FEAT-PAINEL-ANALITICO.md` §13.

### I. Joins entre datasets

- **Problema [Plano §13]:** análises cruzadas (vendas × propostas ganhas) exigem dois painéis.
- **Valor:** alto a longo prazo; **esforço e risco também altos** — muda o coração do query engine (single-dataset) e o modelo de dados (JSONB).
- **Decisão tecnológica [Proposta]:** **adiar.** Construir sobre a typed table (Fase 3, ADR 0002) ou sobre evidência de volume/perf real; antes disso, os conflitos de granularidade e chaves são indefensáveis de projetar no escuro. Se o negócio comprovar a necessidade, planejar como feature própria (GAMA-FEAT) após um spike de modelagem de relações.
- **Referências:** `docs/adr/0002-armazenamento-hibrido-jsonb.md`, `query/executor.py`, roadmap §13.

## 4. Decisões tecnológicas pendentes que independem de feature

Estas decisões não são features, mas bloqueiam ou informam várias candidatas acima. Algumas já estão registradas como pendentes em documentos internos.

### 4.1 D1 — Enviar agregados ao provedor de IA para insights
**Fonte:** `GAMA-FEAT-PAINEL-ANALITICO.md` §14-D1 · **Recomendação [Proposta]:** autorizar apenas agregados, nunca linhas nem PII — registrando em ADR finalidade, retenção e modelo. Impacta F (insights) e qualquer evolução do chat. Sem ela, insights não saem do papel.

### 4.2 D2/D3 — POC do chat com perguntas reais; persistir conversas
**Fonte:** plano §14-D2/D3 · **Recomendação [Proposta]:** coletar 30 perguntas de 3–5 gestores (D2) e medir taxa de sucesso com Groq real antes de investir em refinamento; manter conversas em sessão (D3 = não persistir) até haver pedido real de auditoria/continuidade.

### 4.3 Trigger da typed table (ADR 0002, Fase 3)
**Fonte:** ADR 0002 · Gatilho: p95 > 300 ms (ou plano de execução lento) em produção no dataset de referência. **Ação [Proposta]:** instrumentar a medição no ambiente real (cota paga / dados reais) e registrar baseline; essa medição decide se E (campos calculados) deve considerar materialização.

### 4.4 Deploy de produção nunca validado
**Fonte:** README/runbooks · `docker-compose.prod.yml` nunca foi executado. **Ação [Proposta]:** antes de empilhar features novas, executar o runbook em VPS de teste (deploy, backup, restore, rotação de segredos) e registrar evidência — qualquer feature nova herda o risco operacional de base.

### 4.5 Spike TV em hardware real (24 h)
**Fonte:** `docs/runbooks/tv-kiosk.md` (Spike B) · **Ação [Proposta]:** validar estabilidade, memória e reconexão em TV real por 24 h — independente de features, mas informa A (frescor na TV já exibe badge).

## 5. Faseamento recomendado

| Fase | Itens | Lógica |
|---|---|---|
| **0 — custo baixo, certeza alta** | H (período arbitrário) → G (compartilhar visões) → A (agendamento de cargas) | Latência curta de entrega; A é pré-requisito de valor para C/D |
| **1 — depende de spikes/evidência, rodar em paralelo** | B (spike Ploomes → conector) · E (campos calculados, após POC de recusas) · D2 (POC chat 30 perguntas) | B e E destravam o valor "frescor + linguagem do negócio"; D2 mede a IA real |
| **2 — depende da Fase 1** | C (alertas) · D (relatórios) · F (insights, após D1) · I (joins, após evidência de volume) | C/D dependem de dados frescos (A) e podem compartilhar infra; F depende de D1; I fica condicionado à typed table |

**Critério de entrada por candidata [Proposta]:** pedido real de gestor OU evidência em logs/recusas (chat) OU redução comprovada de trabalho manual. Candidata sem um desses sinais fica no roadmap, não no sprint.

**Regra de encaminhamento:** a candidata aprovada gera o plano completo no formato do planejador (documento `GAMA-FEAT-<NOME>.md` com requisitos, etapas, testes e aceite). Este catálogo é o índice de decisão, não o substituto do plano da feature.

## 6. O que fica de fora (deliberadamente)

- **Joins entre datasets** — até evidência de volume (I, acima).
- **PDF/PNG para exportação e relatórios** — requer ADR e pedido real; CSV/HTML cobrem o caso no MVP.
- **WhatsApp como canal de alerta** — anti-escopo; começar in-app e e-mail.
- **Conectores Omie** — Ploomes primeiro (já é a origem do relatório); Omie após o primeiro pull rodar.
- **Webhooks do Ploomes** — contra-spike: pull primeiro (anti-escopo explícito).
- **Rollups, multi-tenant, SSO/MFA, edição colaborativa, app nativo** — anti-escopo do plano técnico; reavaliar só com pedido explícito e ADR.

## 7. Referências

Internas (consultadas em 02/11/2026): `docs/adr/0002-armazenamento-hibrido-jsonb.md`, `docs/adr/0008-conectores-ploomes-omie.md`, `docs/adr/0010-ia-geracao-de-dashboards.md`, `docs/adr/0012-painel-analitico.md`, `docs/planos/GAMA-FEAT-IA-DASHBOARDS.md`, `docs/planos/GAMA-FEAT-PAINEL-ANALITICO.md` (§13–14), `docs/planos/POC-CHAT-ANALISE.md`, `docs/runbooks/tv-kiosk.md`, `.claude/CLAUDE.md`, `backend/app/modules/{datasets,query,analysis,connectors,workers}`.

Externas: nenhuma consultada neste catálogo. **Antes de codar o conector Ploomes**, consultar a documentação oficial (autenticação, paginação, limites, campos, webhooks) e registrar data de consulta e versão — [Pendente].
