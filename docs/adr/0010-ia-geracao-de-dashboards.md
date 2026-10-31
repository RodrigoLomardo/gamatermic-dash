# ADR 0010 — Sugestão de dashboards por IA (Groq) e Configurações do sistema

Status: aceito · Data: 30/10/2026 · Plano: [`docs/planos/GAMA-FEAT-IA-DASHBOARDS.md`](../planos/GAMA-FEAT-IA-DASHBOARDS.md)

## Contexto

Montar uma dashboard do zero exige conhecer o dataset e o `QuerySpec`. Pedido do negócio: o usuário escolhe ou anexa um dataset, descreve em texto o que quer ver e uma IA propõe gráficos; ele aceita alguns, todos ou nenhum. O provedor escolhido é a **Groq** (API compatível com OpenAI). O plano técnico não previa IA nem chamada de saída a terceiros, por isso este ADR.

## Decisão

1. **A IA nunca gera SQL nem `QuerySpec` direto.** O modelo responde num schema JSON **reduzido e estrito** (`response_format: json_schema, strict: true`). O backend traduz para `QuerySpec` + `viz_config` e passa pelo mesmo `validate_widget` do editor (lista branca de `dataset_fields`). Proposta inválida passa por 1 rodada de reparo; se continuar inválida, é descartada e contada.
2. **O que sai para a Groq:** nome do dataset, descrição, e nome/rótulo/tipo/papel dos campos **não-`pii`**, mais o texto do pedido. **Nenhuma linha de dados, amostra ou valor** vai ao modelo. Campos `pii` também ficam fora da lista branca usada na validação.
3. **Fora do caminho crítico.** TV, visualização e editor não dependem da Groq. Falha da IA só afeta a tela "Criar com IA".
4. **Propostas são efêmeras.** Não há tabela de rascunho (rascunho/versionamento continua anti-escopo). Só o que o usuário aceita vira dashboard, pelos endpoints que já existem; a dashboard nasce `offline` (ADR 0009).
5. **Configurações do sistema** em `system_settings` (chave → `value` JSONB + `secret_ciphertext` Fernet). A chave da API Groq é **somente escrita**: a API devolve `configured` e os 4 últimos caracteres. Permissão nova `settings:manage` (só Administrador). Uso da IA exige `dashboard:create` + `dataset:query` no dataset.
6. **Modelos:** allowlist em código: `openai/gpt-oss-120b` (padrão) e `openai/gpt-oss-20b`, ambos de produção na Groq e com suporte a saída estrita (documentação Groq consultada em 30/10/2026). Modelos *preview* ficam fora. `reasoning_effort=low`, `include_reasoning=false`, sem streaming (o modo estrito não suporta).
7. **Erros da Groq não viram 401** para o navegador (o frontend trataria como sessão perdida). Chave inválida → 502 `ai_invalid_key`; limite → 429 `ai_rate_limited` com `Retry-After` repassado; timeout → 504 `ai_timeout`; indisponível → 502 `ai_unavailable`.
8. **Host fixo.** O endereço da Groq vem de `GAMA_GROQ_BASE_URL` (variável de ambiente, padrão `https://api.groq.com/openai/v1`), nunca do usuário: sem superfície de SSRF. A variável existe para o E2E apontar para um servidor falso.
9. **Auditoria:** `settings.ai.update` (sem o valor da chave), `ai.generate` (dataset, modelo, tokens, nº de propostas, tamanho e hash do pedido; **o texto do pedido não é gravado**, pode conter dado sensível).
10. **Limite de uso:** 10 gerações/min por usuário e 5 testes de conexão/min (janela em memória, ADR 0000 #10).

11. **Gráficos com IA dentro de um painel existente** (editor → *Gráficos com IA*): mesmo endpoint, com `dashboard_id`. Exige `dashboard:edit` naquele painel; a IA recebe os títulos dos gráficos já existentes (não os dados) e o backend descarta propostas que mostram a **mesma informação** de um widget do painel — mesma família (valor: KPI/medidor; tendência: linha; recorte: barras/pizza/tabela agrupada; linhas: tabela de colunas), mesmas medidas (agregação + campo), recorte, granularidade e filtros; título, alias, período, ordem e limite não contam. O motivo cita o gráfico existente. A IA também recebe, por gráfico, um resumo do que ele mostra e a regra de evitar métricas dedutíveis (ex.: custo quando já há receita e margem). Se nada novo sobrar, os ajustes de layout também são descartados. Os aceitos entram abaixo dos atuais pelo endpoint de widgets já existente, com `If-Match` (conflito de versão abre o aviso padrão do editor).

12. **A IA entende o layout do painel** (editor): recebe posição e tamanho de cada gráfico (`layout_atual`, com refs curtas `w1…`, não UUIDs), devolve `x/y/w/h` sugeridos para cada novo e `layout_changes` (mover/redimensionar existentes, com motivo). O backend saneia tudo: ref inexistente e mudança sem efeito são descartadas, nada sai da grade, gráfico novo nasce no mínimo completo e existente nunca fica abaixo de 2×2 (ADR 0011); a resposta marca quando a mudança deixa o gráfico na visão compacta. Nada é aplicado sozinho: o usuário marca as mudanças que quer, vê uma prévia do layout final e só então o sistema grava (primeiro `PUT /layout`, depois os `POST /widgets`). Mudança recusada faz o novo gráfico descer sem sobrepor.

## Consequências

- `GAMA_FERNET_KEY` passa a proteger um segredo de negócio: trocar a chave exige recifrar `system_settings.secret_ciphertext` (runbook de rotação atualizado). A chave padrão de dev **não** pode ir a produção.
- A VPS precisa de saída HTTPS para `api.groq.com`.
- Dependência de terceiro com retenção própria: conferir em *Data Controls* da organização Groq e ativar **Zero Data Retention** se disponível (pendente, conta ainda não criada).
- A qualidade das sugestões só é medida com a conta real (Etapa 0/4 do plano): meta de ≥ 80 % de propostas válidas.

## Alternativas descartadas

- **Modelo gerar `QuerySpec` completo:** schema largo com opcionais e `Any`, incompatível com o modo estrito e com mais superfície de erro.
- **Enviar amostras de linhas:** melhora filtros por valor, mas envia dado de negócio/cliente a terceiro. Reavaliar com a diretoria.
- **Chave em `.env`:** o pedido é configurar pela plataforma; `.env` exigiria acesso ao servidor e restart.
