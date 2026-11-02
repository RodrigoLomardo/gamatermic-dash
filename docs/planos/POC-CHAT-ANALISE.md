# POC — chat de análise (Etapa 1 do plano GAMA-FEAT-PAINEL-ANALITICO)

Data: 02/11/2026 · Modelo: `openai/gpt-oss-120b` (Groq, conta gratuita) · Dataset: `vendas_ploomes` (relatório real, 2.222 pedidos, 12 campos) ·
Perguntas: as 30 dos gestores (arquivo do pedido) · Reprodução: `cd backend && PYTHONPATH=. uv run python -u ../scripts/poc_chat_analise.py --rounds 3 --pace 10`

## Como foi medido

Cada pergunta passa pelo mesmo núcleo do produto (`chat.answer`): prompt só com metadados → Groq (JSON estrito) → tradução para `QuerySpec` →
validação pela lista branca → 1 rodada de reparo → execução no banco. Classificação das perguntas (feita por mim, não pelos gestores):

- **S (13)** responde com um gráfico exato; **P (14)** dá para mostrar a parte calculável (aproximação honesta); **U (3)** o sistema não calcula (churn, novos × recorrentes, projeção).
- **Correta** = S/P: gráfico cuja consulta responde à pergunta (medida, agrupamento, período conferidos por regra no script); U: recusa explicativa.
- **Critério estrito:** recusar algo que dava para mostrar conta como **erro**. A 1ª versão do script contava recusa como acerto em P e dava 93% — número inflado, descartado.

## Resultados

| Rodada | Prompt | Perguntas medidas | Válidas | Corretas (estrito) |
|---|---|---|---|---|
| 1 | inicial | 30 | 96,7% (1 erro de conexão) | **50%** (15/30): recusava demais ("posso mostrar X" e não mostrava) |
| 2 | "regra de ouro": mostrar a parte calculável; receitas para YoY, participação, tendência por grupo | 27 (cota da Groq cortou as 3 últimas) | 100% | **81%** (22/27; 85% reclassificando a Q13) |
| 3 | + clarify raro; potencial de expansão, recompra, venda em equipe | 17 (cota esgotada; interrompida a pedido) | 94% (1 falha: Q1 caiu no fallback depois de 11 min de 429) | **82%** (14/17) |

Itens de decisão do plano (§10, metas **propostas**, sem baseline): ≥ 80% válidas · ≥ 70% corretas · p95 ≤ 8 s.

- **Válidas:** atendida (≈ 94–100%).
- **Corretas:** atendida na amostra (≈ 81–85%), **mas a amostra final é incompleta**: 44 de 90 execuções planejadas, nenhuma rodada completa com o prompt final, e as perguntas 28–30 nunca foram medidas com os prompts revisados.
- **Latência:** respostas sem espera de cota levam 1–2 s (p50 ≈ 1,3 s). O p95 medido (> 40 s) é quase todo **espera de 429** da conta gratuita (1 caso de 683 s). Não dá para afirmar o p95 do produto até rodar com cota própria.
- **Variação entre rodadas (3 repetições):** não medida de forma completa. Observado: a mesma pergunta (Q1) passou na rodada 2 e caiu no fallback na rodada 3.

## O que o modelo faz bem / mal

Bem: faturamento por período, ticket médio ao longo do tempo, pedidos por mês, ranking top N, participação por empresa/segmento/forma de pagamento,
comparativo 2026 × mesmo período de 2025 (`compare_to = last_year`), tendência por grupo, e recusa com explicação de churn, novos × recorrentes e projeção.
Nunca devolveu número no texto; todos os valores vieram do banco.

Mal / a monitorar: (1) ainda recusa ou pede esclarecimento de vez em quando o que dava para mostrar (venda em equipe, "pequenos negócios"); (2) Q14 (aumento/queda por cliente)
às vezes devolve um gráfico que não responde; (3) perguntas compostas ("A e B") podem virar só A.

## Decisão

**Continuar** (critério da Etapa 1): o chat foi construído e ativado atrás da flag `analysis_chat` (RF-16). Recomendações antes de liberar a todos:

1. Rodar `--rounds 3` completo **com cota paga** (ou `gpt-oss-20b`) para fechar variação e p95; a conta gratuita bloqueia por tokens/min (≈ 3,5 mil tokens por pergunta, prompt incluso).
2. Substituir minha classificação S/P/U por revisão de 2–3 gestores nas respostas das perguntas P.
3. Se faltar cobertura para razões entre medidas (margem %, média ponderada), considerar ADR para medidas derivadas — é a causa de várias recusas legítimas.

Limitação de método: o verificador é por regras sobre o `QuerySpec` (campo, agregação, dimensão, período); não confere o *valor* numérico contra um resultado esperado definido por pessoas.
