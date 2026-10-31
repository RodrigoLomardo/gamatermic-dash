# GAMA-FEAT-IA-DASHBOARDS — Dashboards sugeridos por IA (Groq) + aba Configurações

| | |
|---|---|
| Projeto | gamatermic-dash |
| Versão | 0.5 |
| Data | 30/10/2026 |
| Estado | **Implementado (Etapas 1–3 e parte da 4)** com Groq falsa. Pendente: Etapa 0/4 com a conta Groq real (qualidade, latência, tokens) — ver §15 |
| Fontes | Pedido do usuário; `.claude/CLAUDE.md`; código em `backend/app/modules/{query,dashboards,datasets,ingestion}`; documentação oficial Groq (consultada em 30/10/2026, ver §10) |

Legenda: **[Dado]** informado pelo usuário · **[Código]** confirmado lendo o repositório · **[Fonte]** confirmado em documentação oficial · **[Proposta]** decisão sugerida · **[Hipótese]** a validar · **[Pendente]** depende de resposta.

---

## 1. Problema, usuário e resultado

- **Problema [Dado]:** montar uma dashboard do zero exige conhecer o dataset, escolher tipo de widget e montar o `QuerySpec` no editor. Quem não domina isso começa de uma tela em branco.
- **Usuário:** quem tem `dashboard:create` (gestores/editores). Administrador configura a IA.
- **Resultado [Dado]:** o usuário anexa um arquivo (CSV/XLSX) ou escolhe um dataset, escreve em uma caixa de texto o que quer ver, e um agente propõe um conjunto de gráficos. O usuário **aceita alguns, todos ou nenhum** e parte daí para o editor existente.
- **Segundo entregável [Dado]:** nova aba **Configurações** do sistema, onde fica a credencial do Groq (e demais ajustes da IA). A aba nasce junto, mas deve servir a futuras configurações.
- **Sinal de sucesso [Proposta]:** (a) ≥ 80 % das sugestões passam na validação do backend sem intervenção (medido na POC e em produção); (b) usuário chega a uma dashboard publicável em menos cliques que montando do zero; (c) zero vazamento de segredo ou de campo `pii`.

## 2. Decisões já tomadas e conflitos com o projeto

| Tema | Situação |
|---|---|
| Provedor | Groq **[Dado]**. Chave configurada pela própria plataforma **[Dado]**. |
| Princípio 2 (sem SQL livre) | **Compatível.** A IA nunca gera SQL: gera um `QuerySpec` que passa por `validate_widget`/`validate_spec` (lista branca de `dataset_fields`) **[Código]**. |
| Princípio 7 (segredo) | Chave cifrada com Fernet (`core/crypto.py`), nunca em log, resposta de API, auditoria ou git **[Código/Proposta]**. |
| Princípio 8 (PII) | Prompt leva só metadados (nome, rótulo, tipo, papel). Campos `pii` são excluídos. Nenhuma linha de dados é enviada na versão 1 **[Proposta]**. |
| Princípio 4/5 | IA fica fora do caminho crítico: TV e visualização não dependem do Groq. Falha da IA só afeta a tela de geração. |
| Anti-escopo | "Rascunho/versionamento de dashboards" está fora. **Por isso as sugestões são efêmeras** (não há tabela de rascunho); só o que o usuário aceita vira dashboard real **[Proposta]**. |
| "Não antecipar sem ADR" | **Conflito a resolver:** IA generativa e dependência de terceiro não constam no plano. Resolução: **ADR 0010** (Etapa 0). Também registra que a ausência de "SaaS de terceiros no caminho crítico" continua verdadeira. |
| Segredos e `.env` | A chave do Groq entra pela UI, não por `GAMA_*`. Em contrapartida a `GAMA_FERNET_KEY` passa a proteger um segredo de negócio: o valor padrão de dev (`config.py`) **não** pode ir a produção **[Código]**; atualizar `docs/runbooks/rotacao-de-segredos.md` (rotacionar a Fernet exige recifrar). |

## 3. Escopo

**Entra (MVP):**
1. Tabela e API de configurações do sistema (chave Groq cifrada, modelo, liga/desliga), permissão nova `settings:manage`.
2. Página **Configurações → IA (Groq)** com salvar chave, escolher modelo, "Testar conexão".
3. Endpoint de geração: recebe dataset + pedido em texto, devolve N propostas de widget validadas, já com dados de pré-visualização.
4. Tela "Criar com IA": caixa de texto, seleção de dataset **ou** anexar arquivo, grade de propostas com aceitar/descartar, "Criar painel com os selecionados".
5. Anexar arquivo reaproveita o fluxo existente `infer-schema` + criação de dataset + upload **[Código]**.
6. Auditoria da configuração e do uso, limite de uso por usuário, testes, ADR e documentação.

**Fica fora (agora):** chat conversacional com refinamento iterativo ("troque o gráfico 2 por barras"); enviar amostras de linhas ao modelo; salvar rascunhos; edição de proposta por IA após criada; múltiplos provedores; cache de respostas; cobrança/quotas por usuário em R$; reconhecimento de PDF/imagem; configurações além da IA (a aba é criada com a seção IA e estrutura para outras).
**Roadmap condicionado a evidência:** refinamento iterativo (se a POC mostrar que o 1º disparo acerta pouco); valores categóricos no prompt para filtros (se pedidos como "só o segmento X" falharem muito e a diretoria autorizar); fallback entre modelos.

## 4. Maior incerteza e como ela entra primeiro

**Incerteza [Hipótese]:** um modelo da Groq, vendo só nomes e tipos de campos, produz `QuerySpec`/`viz_config` corretos, úteis e coerentes com o pedido, com regras do sistema (medidas com `alias` válido, `time.field`, períodos, `ultima_revisao = true`, `gauge` com `target`). Se isso falhar, o resto da feature não vale.

**Mitigação [Proposta]:** a **Etapa 0 é uma POC descartável** (script, sem UI, chave por variável de ambiente local), rodada nos 4 datasets reais e em 1 CSV externo, com 10 a 15 pedidos em português. Critério de continuar: ≥ 80 % das propostas válidas após validação + reparo automático (1 retentativa com a mensagem de erro) e ≥ 60 % julgadas "úteis" pelo usuário. Abaixo disso, parar e reavaliar prompt/modelo antes de construir UI.

**Segunda incerteza [Hipótese]:** limites de taxa/tokens da conta Groq. Para `openai/gpt-oss-120b` no plano Developer a página oficial lista 30 RPM, 1 K RPD, **8 K TPM**, 200 K TPD **[Fonte]**; os números do plano gratuito não foram extraídos. Um prompt com schema largo + instruções pode consumir uma fração relevante de 8 K TPM. A POC mede tokens por chamada.

## 5. Solução proposta

### 5.1 Jornada

1. Usuário abre **Dashboards → Nova → Criar com IA** (exige `dashboard:create` + acesso ao dataset).
2. Escolhe um dataset existente **ou** anexa CSV/XLSX. Anexo: `infer-schema` mostra os campos inferidos, usuário confirma nome/slug e o dataset é criado e carregado (exige `dataset:manage` + `ingestion:upload`; sem essas permissões só vê datasets existentes).
3. Escreve o que quer ver (ex.: "faturamento por mês e top 10 clientes").
4. Sistema chama o agente. Mostra "Gerando…", depois uma grade de cartões (título, tipo, gráfico com dados reais do dataset, justificativa curta).
5. Cada cartão tem **Aceitar / Descartar**; há "Selecionar todos" e "Nenhum".
6. **Criar painel**: com ≥ 1 aceito cria a dashboard com esses widgets e abre o editor. Com 0 aceitos, o botão vira "Começar em branco" (dashboard vazia no editor). Nada é gravado antes dessa confirmação.

### 5.2 Estados e falhas (cada um com mensagem e saída)

| Situação | Comportamento |
|---|---|
| IA não configurada / desligada | Tela explica; admin vê link para Configurações, demais veem "peça ao administrador". |
| Chave inválida (401 do Groq) | Erro claro; não revela a chave; sugere testar em Configurações. |
| 429 (limite) | Respeita `retry-after` **[Fonte]**; mostra "tente em N s". No máximo 1 retentativa automática curta. |
| Timeout / Groq fora | Erro recuperável; o resto do sistema segue normal. |
| Resposta fora do schema ou `QuerySpec` inválido | 1 reparo automático (reenvia o erro); proposta que continuar inválida é descartada e contada ("2 sugestões descartadas por inválidas"). |
| Zero propostas válidas | Mensagem + botão "Começar em branco". |
| Dataset sem campos úteis / pedido fora do alcance dos dados | Modelo pode devolver lista vazia com `explicacao`; exibir. |
| Anexo inválido/grande | Reaproveita erros e limites do upload atual (anti zip-bomb, 20 % de rejeição) **[Código]**. |
| Dataset com PII | Campos `pii` omitidos do prompt e da lista de campos permitidos à IA. |

### 5.3 Componentes e responsabilidades

Seguem as camadas do projeto (`router → service → repository → models`, regra do `import-linter`); frontend por feature sem importar entre features **[Código]**.

**Backend** (todos **propostos**):
- `modules/settings/` — `models.py` (`SystemSetting`), `repository.py`, `service.py`, `router.py`, `schemas.py`. Guarda/retorna configurações; valores marcados `secret` são cifrados com `core/crypto.py` e **nunca** devolvidos (a API retorna `configured: true` e últimos 4 caracteres).
- `modules/ai/` — `groq_client.py` (httpx assíncrono, host fixo `api.groq.com`, timeout, mapeamento de erros, leitura de `retry-after`), `prompt.py` (monta contexto só com metadados), `proposal_schema.py` (schema **simplificado** para a saída do modelo), `service.py` (orquestra: autoriza, monta prompt, chama, converte para `QuerySpec`, valida com `validate_widget`, executa preview, reparo), `router.py`.
- Permissão nova `settings:manage` no catálogo (`core/authz/catalog.py`) e concedida só ao Administrador; geração usa permissões já existentes (`dashboard:create`, `dataset:query`).
- Migração Alembic nova (tabela `system_settings`); nunca editar a baseline.
- `audit_logs`: `settings.update` (sem valor do segredo no diff — grava apenas "chave alterada"), `ai.generate` (usuário, dataset, modelo, tokens, nº de propostas; **sem** texto bruto do pedido por padrão **[Hipótese]**, ver §9).

**Frontend:**
- `features/settings/SettingsPage.tsx` + rota `/configuracoes` (guarda `settings:manage`) e item no menu admin. Seções em abas; primeira: "IA (Groq)".
- `features/ai-dashboards/` — `AiCreatePage.tsx`, `ProposalCard.tsx` (reutiliza o renderer de `features/widgets` via `shared`/props, sem importar outra feature; se necessário mover o renderer para `shared`), `useGenerateProposals.ts`.
- Cliente TS regenerado (`npm run gen:api`); snapshot OpenAPI atualizado.

### 5.4 Contratos (propostos, não confirmados)

**Configurações**
```
GET  /api/v1/settings/ai        -> { enabled, model, api_key: { configured, last4 }, updated_at }
PUT  /api/v1/settings/ai        <- { enabled, model, api_key? }   # api_key omitida = mantém; "" = remove
POST /api/v1/settings/ai/test   -> { ok, model, latency_ms, error? }   # chama GET /openai/v1/models com a chave salva
GET  /api/v1/settings/ai/models -> lista de modelos permitidos (allowlist do backend ∩ resposta do Groq)
```
Todas com `settings:manage`. `PUT` valida `model` contra a allowlist (§6).

**Geração**
```
POST /api/v1/ai/dashboard-proposals
  <- { dataset_id, prompt (≤ 1000 chars), max_proposals (1..8, padrão 6) }
  -> { proposals: [ { id, type, title, rationale, query_config, viz_config,
                      w, h, preview: WidgetResult-like | null } ],
       discarded: n, usage: { model, prompt_tokens, completion_tokens } }
```
O `id` é local à resposta (não persiste). Criar o painel reutiliza `POST /dashboards` e a inclusão de widgets já existentes **[Código]**; não há endpoint novo de "aceitar". Dashboard é criada como **`offline`** até o usuário lançar (ADR 0009) **[Proposta; hoje o padrão do modelo é `published` — confirmar a decisão em Etapa 3]**.

**Saída do modelo (schema estrito) [Proposta]:** objeto com `explicacao` (string) e `widgets[]` de `{type (enum dos 6 tipos), title, rationale, measures[{field|null, agg, alias}], dimensions[], time{field|null, granularity}|null, period_preset, sort, limit, format, horizontal|null, target|null}`. Todos os campos em `required`, opcionais como `["tipo","null"]`, `additionalProperties:false`, conforme exigência do modo estrito **[Fonte]**. O backend traduz para `QuerySpec` + `viz_config`. Motivo: o `QuerySpec` real tem muitos opcionais, `Any` em `Filter.value` e aliases; um schema reduzido é mais fácil de obedecer e limita a superfície.

### 5.5 Prompt e segurança do agente

- **Contexto enviado:** nome/rótulo/tipo/papel (`dimension|measure|time`) dos campos **não-pii**; campo de tempo do dataset; catálogo dos 6 tipos de widget com suas exigências (`WIDGET_TYPES.needs`); regras de negócio relevantes que estão em `docs/contracts/datasets.md` (ex.: filtrar `ultima_revisao = true` em propostas, «Faturamento» = soma de `Valor`) — **só quando o dataset for um dos conhecidos** **[Hipótese: simplificar para um campo `ai_hints` opcional no dataset, a decidir na Etapa 0]**.
- **Instruções do usuário** vão na mensagem `user`, delimitadas; regras do sistema na `system`.
- **Injeção de prompt:** nomes de colunas e o texto do pedido são não confiáveis. Defesa estrutural, não textual: o modelo não tem ferramentas, não executa nada, só devolve JSON; toda saída passa pela lista branca de campos e pela validação do backend; limites de tamanho (pedido 1000 chars, ≤ 8 widgets, `limit` ≤ 5000 do `QuerySpec`).
- **Sem streaming:** o modo estrito do Groq não suporta streaming nem tool use **[Fonte]**; a UI usa "Gerando…" com timeout.

## 6. Modelos Groq (hipótese de partida)

**[Fonte, 30/10/2026]** O modo `json_schema` com `strict: true` é suportado por `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b` e `meta-models/muse-spark-open`. Em produção (não preview) estão `openai/gpt-oss-120b` e `openai/gpt-oss-20b`, ambos com contexto de 131 072 tokens. `GET https://api.groq.com/openai/v1/models` lista modelos ativos.

**[Proposta]** Allowlist inicial no backend: `openai/gpt-oss-120b` (padrão, maior qualidade) e `openai/gpt-oss-20b` (rápido/barato). Modelos *preview* não entram no MVP (podem ser descontinuados). A Etapa 0 compara os dois e o resultado define o padrão. O catálogo muda; a allowlist fica em código e o "Testar conexão" avisa se o modelo configurado deixou de existir.

## 7. Dados

Tabela `system_settings` **[Proposta]**:
`key text PK` · `value jsonb` (valor não secreto) · `secret_ciphertext bytea null` (Fernet) · `updated_by uuid` · `updated_at timestamptz`. Chaves iniciais: `ai.enabled`, `ai.model`, `ai.groq_api_key`. Sem `DELETE` de negócio: remover chave = limpar o segredo (grava auditoria). Nenhuma outra tabela nova: propostas são efêmeras.

## 8. Etapas

Esforço em P/M/G relativo (P ≈ 1–2 dias, M ≈ 3–5, G ≈ 1–2 semanas), **[Hipótese]** sem capacidade conhecida; não inclui espera externa (criação da conta Groq pelo usuário).

### Etapa 0 — ADR + POC de qualidade (P/M) · *primeiro, maior risco*
- **Objetivo:** provar que a IA gera propostas válidas e úteis; registrar a decisão.
- **Pré-requisitos:** conta Groq e chave criadas **pelo usuário**, guardadas só em variável de ambiente local (não pedir nem registrar a chave em chat/arquivo).
- **Ações:** [ ] escrever script descartável em `scratchpad`/`scripts/poc_ai/` (não versionar chave) que monta o prompt a partir dos `dataset_fields` e chama o Groq; [ ] definir schema estrito reduzido (§5.4); [ ] rodar 10–15 pedidos nos 4 datasets + 1 CSV externo; [ ] comparar `gpt-oss-120b` × `gpt-oss-20b`; [ ] medir % válidas (via `validate_widget`), % úteis (avaliação do usuário), latência, tokens por chamada vs. limites da conta; [ ] testar 3 pedidos hostis (injeção, campo inexistente, pedido sem relação); [ ] redigir `docs/adr/0010-ia-geracao-de-dashboards.md` (provedor, dados enviados, retenção, fallback, allowlist) e linha em `0000-desvios` se aplicável.
- **Entregáveis:** relatório da POC (tabela de resultados), ADR 0010 em "proposto".
- **Validação / saída:** critério do §4 atingido **e** usuário aprova o ADR. Se não, replanejar (refino iterativo, outro modelo) antes da Etapa 1.
- **Pendências:** política de retenção da Groq (§10) revisada por quem responde por LGPD na empresa.

### Etapa 1 — Aba Configurações + armazenamento de segredo (M)
- **Objetivo:** admin salva a chave do Groq com segurança e testa a conexão.
- **Pré-requisitos:** ADR 0010 aceito.
- **Ações:** [ ] migração `system_settings`; [ ] modelos/repositório/serviço/rotas de `settings` com `settings:manage` (teste do varredor de OpenAPI exige política declarada); [ ] semear a permissão e atribuí-la ao Administrador (verificar como `catalog.py` é sincronizado com o banco); [ ] cifrar/decifrar a chave via `crypto.py`; resposta mascarada; [ ] cliente Groq mínimo (`GET /models`) para "Testar conexão"; [ ] `rate_limit.hit` no teste; [ ] auditoria sem valor do segredo; [ ] frontend `SettingsPage`, rota e menu; [ ] `scripts/update-openapi-snapshot.sh` + `npm run gen:api`.
- **Entregáveis:** página funcional; testes de backend (matriz RBAC, segredo nunca retornado nem logado, auditoria sem valor, round-trip de cifra) e de frontend (vitest + axe).
- **Validação / saída:** com a chave real de teste do usuário, "Testar conexão" retorna OK; com chave errada retorna erro claro; usuário sem `settings:manage` recebe 403 e não vê o menu.
- **Dependência:** conta Groq do usuário.

### Etapa 2 — Serviço de geração (G)
- **Objetivo:** `POST /ai/dashboard-proposals` retorna propostas válidas com preview.
- **Pré-requisitos:** Etapa 1; prompt/schema aprovados na Etapa 0.
- **Ações:** [ ] cliente Groq completo (timeout, 401/429/5xx, `retry-after`); [ ] `prompt.py` e `proposal_schema.py`; [ ] tradução para `QuerySpec`/`viz_config`; [ ] validação com `validate_widget` e exclusão de campos `pii`; [ ] 1 reparo automático; [ ] preview executando o `QueryExecutor` com a autorização do usuário; [ ] limite por usuário (ex.: 10/min, `hit`) e teto de tamanho; [ ] auditoria `ai.generate`; [ ] logs sem prompt nem chave.
- **Entregáveis:** endpoint documentado no OpenAPI; testes com `httpx.MockTransport` (resposta válida, JSON quebrado, campo inventado, campo `pii`, 401, 429 com `retry-after`, timeout); teste de que um dataset fora do alcance do usuário retorna 403/404 sem chamar o Groq.
- **Validação / saída:** resultados da POC reproduzidos pelo endpoint; nenhum teste depende de rede real.

### Etapa 3 — Tela "Criar com IA" (M/G)
- **Objetivo:** o fluxo completo de ponta a ponta, incluindo aceitar parcialmente.
- **Pré-requisitos:** Etapa 2.
- **Ações:** [ ] `AiCreatePage` com caixa de texto, seletor de dataset e anexo (reusa `infer-schema`/criação/upload); [ ] grade de `ProposalCard` com preview real e estados de erro por cartão (um card com erro não derruba os outros, princípio 5); [ ] aceitar/descartar/todos/nenhum; [ ] "Criar painel" cria dashboard + widgets pelos endpoints existentes e navega ao editor; [ ] decidir `offline` por padrão para painéis criados por IA; [ ] estados do §5.2; [ ] acessibilidade e mobile; [ ] testes vitest/MSW e E2E Playwright com **servidor Groq falso** (nada de rede real no CI).
- **Entregáveis:** fluxo navegável; E2E: gerar → aceitar 2 de 4 → painel criado com 2 widgets; gerar → nenhum → editor vazio; sem configuração → mensagem.
- **Validação / saída:** critérios de aceite A1–A8 (§11) passam em ambiente local.

### Etapa 4 — Teste real, endurecimento e documentação (P/M)
- **Objetivo:** validar com a conta Groq real e fechar pendências operacionais.
- **Ações:** [ ] sessão de teste com o usuário e a chave real (dataset Ploomes + um arquivo novo); [ ] ajustar prompt com os casos reais; [ ] medir latência p95 e tokens por geração; [ ] atualizar README, `rotacao-de-segredos.md` (recifrar `system_settings`), novo runbook curto "IA indisponível / chave expirada"; [ ] ADR 0010 → "aceito"; [ ] `make lint` e `make test` limpos; [ ] CI: drift de migração e contrato OpenAPI.
- **Saída:** DoD (§12) cumprido.

## 9. Riscos e decisões de privacidade

| Risco | Mitigação |
|---|---|
| Dados de negócio saindo para terceiro | Só metadados no prompt; ADR 0010; sem linhas na v1. **Os nomes/rótulos de colunas também são enviados**; aceitar isso explicitamente. |
| Retenção na Groq | Páginas oficiais divergem: há indicação de retenção padrão de até 30 dias e de opção de Zero Data Retention nas configurações da organização **[Fonte parcial; confirmar na conta]**. Ação: ativar ZDR se disponível e registrar no ADR. |
| Chave vazada | Cifrada, mascarada, auditada sem valor; `.env` inalterado; rotação documentada. |
| Custo/limite inesperado | Limite por usuário, teto de propostas, `max_tokens` fixo, exibição de erro 429 com tempo. |
| Alucinação de campos/medidas | Lista branca + validação + descarte contado. |
| Prompt injection por nome de coluna/pedido | Saída só JSON validado; sem ferramentas. |
| Modelo descontinuado | Allowlist + "Testar conexão" avisa; troca por configuração, sem deploy de prompt. |
| Auditoria do pedido do usuário | **[Hipótese]** gravar só tamanho + hash do pedido; texto bruto pode conter dado sensível. Decidir no ADR. |

## 10. Fontes consultadas (30/10/2026)

- Structured Outputs — https://console.groq.com/docs/structured-outputs (modelos e restrições do modo estrito).
- Modelos — https://console.groq.com/docs/models (IDs de produção/preview, contexto, endpoint de listagem).
- Rate limits — https://console.groq.com/docs/rate-limits (limites do plano Developer, `retry-after`; **números do plano gratuito não obtidos**).
- Your Data — https://console.groq.com/docs/your-data (retenção e ZDR; leitura parcial via busca, **conferir diretamente**). A página `legal/your-data` retornou 404.
- Observação: o conteúdo foi extraído por ferramenta de resumo; **preços e limites devem ser reconfirmados no console da conta antes de decidir plano**.

## 11. Requisitos críticos → etapa → teste → aceite observável

| # | Aceite da feature (observável) | Etapa | Teste |
|---|---|---|---|
| A1 | Admin salva a chave; a API e a UI nunca a exibem de volta (só `configured`/últimos 4) | 1 | Backend: resposta e logs sem valor; auditoria sem valor |
| A2 | Usuário sem `settings:manage` não vê nem acessa Configurações | 1 | Matriz RBAC + vitest |
| A3 | "Testar conexão" distingue OK / chave inválida / sem rede | 1, 4 | MockTransport + teste manual real |
| A4 | Pedido em texto sobre dataset existente gera ≥ 1 proposta com gráfico real | 2, 3 | E2E com Groq falso + teste manual real |
| A5 | Usuário aceita 0, 1 ou todas e o painel criado contém exatamente os aceitos; 0 aceitas abre editor em branco | 3 | E2E |
| A6 | Anexar CSV/XLSX novo cria o dataset e permite gerar propostas sobre ele | 3 | E2E |
| A7 | Campo `pii` nunca aparece no prompt (inspeção do payload enviado) nem nas propostas | 2 | Teste que captura o corpo da requisição |
| A8 | Proposta inválida é descartada sem quebrar as demais; erros 401/429/timeout têm mensagem própria | 2, 3 | Testes de serviço + E2E |
| A9 | IA desligada ou fora do ar não afeta TV, visualização nem editor | 3 | E2E com IA indisponível |
| A10 | Desempenho **[Hipótese]**: geração de 6 propostas com preview em p95 ≤ 20 s | 4 | Cenário: dataset `vendas` real (~volume atual), `gpt-oss-120b`, 20 execuções, rede da VPS/dev; **baseline medido na Etapa 0**; a meta é revista com o baseline |

## 12. Definição de pronto da entrega (distinta dos aceites)

Migração revisada e `alembic check` limpo · OpenAPI snapshot e cliente TS regenerados · `make lint` e `make test` verdes · nenhum teste usa rede real · ADR 0010 aceito · README e runbooks atualizados · nenhum segredo/chave em git, log ou fixture · revisão de segurança do diff (`/security-review`).

## 13. Pendências e perguntas

1. **[Pendente]** Anexar arquivo **sempre cria um dataset novo** (hipótese adotada), ou existe um modo "análise rápida" sem persistir? Hipótese: sempre cria, pelo princípio 3 (carga atômica) e porque dashboards referenciam `dataset_id`. Muda a Etapa 3 se for diferente.
2. **[Pendente]** Quem pode usar a geração? Hipótese: qualquer um com `dashboard:create` e acesso ao dataset; só Administrador configura a chave.
3. **[Pendente]** A conta Groq será gratuita ou Developer (pago)? Define limites reais de TPM e se vale ativar ZDR. Conferir no console após criar a conta.
4. **[Hipótese a validar na Etapa 0]** Campo `ai_hints` por dataset (descrição de negócio curta) para melhorar as sugestões vs. só metadados.
5. **[Hipótese]** Painéis criados por IA nascem `offline` (ADR 0009). Confirmar.

## 14. Registro de revisões

| Versão | Data | Mudança |
|---|---|---|
| 0.1 | 30/10/2026 | Versão inicial |
| 0.2 | 30/10/2026 | Implementado. Ver §15 para o que mudou em relação ao plano e o que falta |
| 0.3 | 31/10/2026 | Gráficos com IA no editor de um painel existente (§16) e correção do filtro booleano |
| 0.4 | 31/10/2026 | IA entende e sugere mudanças no layout; gráficos adaptáveis com visão compacta e layout salvo ao soltar (§17, ADR 0011) |
| 0.5 | 31/10/2026 | Teste com a Groq real: repetidos passam a ser detectados pelo conteúdo e a prévia do layout foi refeita (§18) |

## 15. Implementação (v0.2) — o que entrou e o que mudou

**Entrou:** ADR 0010; `system_settings` (migração `0002`); `modules/settings` (`GET/PUT /settings/ai`, `POST /settings/ai/test`, permissão `settings:manage`); `modules/ai` (`GET /ai/status`, `POST /ai/dashboard-proposals`, cliente Groq, prompt, tradução); páginas **Configurações** (`/configuracoes`) e **Criar com IA** (`/dashboards/nova/ia`) com anexo de arquivo; Groq falsa para E2E (`frontend/e2e/fake-groq.mjs`); README, runbook de rotação e `.env.example`.

**Decisões tomadas na execução (pendências do §13 resolvidas com as hipóteses):**
1. Anexo **sempre cria dataset novo**, em modo `append` (não exige chave natural; reenviar o mesmo arquivo é barrado pelo controle de duplicidade do upload). Fluxo no frontend: `infer-schema` → `POST /datasets` → upload → espera a carga.
2. Gerar exige `dashboard:create` + `dataset:query` no dataset; configurar exige `settings:manage` (só Administrador).
3. Painéis criados pela IA nascem `offline` (já é o padrão de `POST /dashboards`).
4. Sem campo `ai_hints`: usa a `description` do dataset + regras automáticas (`ultima_revisao = true` imposto no servidor; `valor` como moeda).
5. `/settings/ai/models` virou o campo `models` dentro de `GET /settings/ai`.
6. Auditoria grava tamanho e hash do pedido, **não o texto**.

**Verificado:** 120 testes de backend (13 novos de IA/configurações + 5 unitários de tradução), 26 de frontend (vitest + axe), E2E `ai.spec.ts` contra a Groq falsa, fluxo de anexo CSV no navegador, layout mobile sem rolagem horizontal, `make lint` limpo.

**Não verificado (depende da conta Groq):** qualidade das sugestões (meta A4/§4), latência p95 (A10), consumo de tokens vs limites da conta, comportamento real do modo estrito do `gpt-oss`.

## 16. Gráficos com IA no editor (v0.3)

**Pedido:** além de criar o painel inteiro, gerar mais gráficos para um painel que já existe, com o dataset do painel, em vez de montar widget a widget.

**Jornada:** Editor → **Gráficos com IA** → o dataset mais usado pelos widgets do painel vem selecionado (os do painel aparecem primeiro na lista) → pedido em texto → sugestões com dados reais → marcar alguns/todos → **Adicionar N gráficos ao painel**. Os gráficos entram abaixo dos existentes, empacotados na grade de 12 colunas; o modal fecha e o editor atualiza a versão.

**Contrato:** `POST /ai/dashboard-proposals` ganhou `dashboard_id` opcional. Com ele: exige `dashboard:edit` no painel (403 antes de chamar a Groq), envia ao modelo os títulos já existentes (`graficos_ja_no_painel`) e descarta propostas idênticas (mesmo tipo + `query_config`) a widgets do painel, listando-as em `discarded` como "Já existe um gráfico igual no painel". Auditoria `ai.generate` registra `dashboard_id` e `repeated`. Adicionar usa `POST /dashboards/{id}/widgets` com `If-Match` encadeado; falha parcial mantém o que entrou e avisa o que faltou; 409 abre o aviso de conflito do editor.

**Correção encontrada na verificação:** o compilador montava todas as comparações de um filtro de uma vez, e `> True` quebrava em campo booleano. Isso derrubava **todo widget com `ultima_revisao = true`** (painel *Propostas – Funil Comercial* inteiro e as sugestões de IA sobre propostas). Agora só a comparação pedida é montada; teste de regressão em `test_query.py`.

**Verificado:** 122 testes de backend (novo: painel existente — sem repetidos, 403 sem edição, 404 sem chamar a Groq; regressão do filtro booleano), 28 de frontend (`widgets-panel.test.tsx`), E2E no editor contra a Groq falsa (inclui conferir que um gráfico já adicionado não volta como sugestão), sem rolagem horizontal em 375 px.

## 17. Layout com IA e gráficos adaptáveis (v0.4)

**Pedido:** (a) a IA deve considerar o dimensionamento atual do painel e sugerir alterações para encaixar novos gráficos, não só jogá-los no fim; (b) o usuário redimensiona os gráficos arrastando, sem deixar um gráfico que exige espaço ficar ilegível, e vê visões alternativas ao reduzir.

**(a) IA e layout** — ADR 0010, decisão 12.
- Prompt ganha `layout_atual` (ref, título, tipo, x, y, w, h) e as regras da grade (12 colunas, mínimos por tipo, sem sobreposição).
- Saída estrita ganha `x/y/w/h` por widget e `layout_changes` (ref, novo x/y/w/h, motivo).
- Resposta da API: `Proposal.x/y` e `ProposalsOut.layout_changes[]` com `before`, `after`, `reason`, `compact`.
- Editor → *Gráficos com IA*: lista "Mudanças sugeridas no layout" (cada uma com caixa de seleção e motivo) e minimapa do painel final (novos em laranja, ajustados com contorno, compactos pontilhados), recalculado a cada caixa marcada. Aplicar grava o layout dos existentes e insere os novos nas posições finais.
- Encaixe (`arrange`): existentes com as mudanças aceitas primeiro; novos na posição sugerida; colisão desce, espaço livre acima sobe; novos sem posição vão para o fim. Também usado em *Criar com IA* (painel novo respeita as posições sugeridas).

**(b) Gráficos adaptáveis** — ADR 0011.
- Mínimo completo por tipo e mínimo absoluto 2×2 (validado no backend).
- Visões compactas: linha → valor e tendência; barras → ranking; pizza → % em lista; tabela → lista curta; medidor → % com barra.
- Editor troca a visão ao vivo durante o redimensionamento, mostra a etiqueta "compacta" e salva o layout ao soltar (sem botão *Salvar layout*).

**Verificado:** 126 testes de backend (layout no prompt, saneamento de `layout_changes`, posição de novos, 422 abaixo de 2×2), 36 de frontend (visões compactas, `arrange`, prévia e aplicação PUT→POST), E2E (aceitar mudança de layout no editor; redimensionar até a visão compacta, salvar sozinho e manter após recarregar), capturas no editor e na visualização.

**Não verificado:** como o modelo real da Groq propõe mudanças de layout (a Groq falsa é determinística); comportamento na TV física.

## 18. Ajustes após o primeiro teste com a Groq real (v0.5)

**Relato:** no painel *b2b invoices*, pedindo "mais um KPI", a IA sugeriu "Custo Total" e o usuário entendeu como repetido; a prévia do layout ficou ilegível.

**Diagnóstico (banco e auditoria):** "Custo Total" (soma de `cost`) não existia no painel, mas é dedutível de receita − margem. A detecção de repetidos só pegava configuração idêntica (outro período ou alias passava). A prévia usava cores com opacidade (`bg-line/70`), que não funcionam com as cores do tema: os blocos ficavam sem fundo.

**Correções:**
- Repetido = mesma informação (família do gráfico + medidas + recorte + granularidade + filtros), com o motivo citando o gráfico existente; também pega repetição dentro da própria resposta.
- O prompt recebe, por gráfico existente, o que ele mostra (`mostra`: "soma de revenue por segment") e a regra de não sugerir métrica dedutível.
- Sem nenhuma sugestão nova, os ajustes de layout somem e a tela diz que tudo já está no painel.
- Prévia refeita: título "Como o painel vai ficar", blocos com fundo e borda sólidos, etiqueta "NOVO" e legenda com amostras de cor.

**Verificado:** 128 testes de backend, 36 de frontend, E2E da IA (4/4) e capturas da prévia e do caso "tudo repetido".
