# Contrato dos datasets (relatório Ploomes)

Fonte: `Vendas Ploomes 2025_2026.xlsx`, uma aba por dataset (nome da aba em `parser_options.sheet`, cabeçalho na linha 1). Encoding: XLSX nativo; CSV em UTF-8 ou Windows-1252, separador `;` `,` tab ou `|` (detectado), decimal `1.234,56`, data `dd/mm/aaaa`. Linhas vazias são ignoradas; colunas extras viram aviso; coluna obrigatória ausente **falha a carga inteira**. Limite de rejeição padrão: 20 % das linhas (acima disso nada é alterado).

| dataset | aba | modo | chave natural | campo de tempo |
|---|---|---|---|---|
| `vendas` | Vendas | upsert | `Número` | `Data do Pedido` |
| `propostas_ganhas` | Propostas Ganhas | upsert | `Código` + `Número da revisão` | `Data` |
| `propostas_perdidas` | Propostas Perdidas | upsert | `Código` + `Número da revisão` | `Data` |
| `propostas_abertas` | Propostas Abertas | **replace_snapshot** | `Código` + `Número da revisão` | `Data` |

## vendas
`Número` int ✱chave · `Empresa que irá Faturar` texto · `Data do Pedido` data ✱ · `Cliente` · `Segmento do Cliente` · `Projeto` · `Valor` decimal ✱ · `Responsável` · `Usuários colaboradores do Negócio` · `Condição de Pagamento` · `Produtos` · `Prazo de Pagamento_Nº Dias` int (fórmula de planilha: lido pelo valor calculado salvo no arquivo).

## propostas_* (ganhas / perdidas / abertas)
Comuns: `Código` int ✱chave · `Número da revisão` int ✱chave · `Última revisão` booleano · `Empresa que irá Faturar` · `Cliente do Negócio` · `Valor` decimal ✱ · `Data` data ✱ · `Responsável`.
Ganhas: `Criador`, `Previsão de Faturamento`. Perdidas: `Término do Negócio` (data/hora), `Motivo de perda do Negócio`. Abertas: `Negócio`, `Contato` (**PII**, mascarado), `Produtos da proposta`, `Condição de Pagamento`, `Previsão de Faturamento`.

✱ obrigatório. Alterar nomes de colunas na exportação do Ploomes exige atualizar o mapeamento em **Dados e cargas** (ou `bootstrap/definitions.py`); a validação de cabeçalho acusa a coluna ausente com o nome esperado.

## Regras de negócio assumidas (confirmar com a diretoria)
- "Faturamento" = soma de `Valor` dos pedidos por `Data do Pedido` (não é nota fiscal emitida).
- Comparações "vs período anterior" usam o mesmo recorte decorrido (mês até hoje × mês anterior até o mesmo dia).
- Metas: ainda não há arquivo; o medidor usa meta fixa editável (placeholder).
