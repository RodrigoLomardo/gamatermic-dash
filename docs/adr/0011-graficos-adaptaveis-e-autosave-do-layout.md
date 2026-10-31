# ADR 0011 — Gráficos adaptáveis ao tamanho e layout salvo ao soltar

Status: aceito · Data: 31/10/2026

## Contexto

Quem edita um painel quer ajustar o tamanho dos gráficos só arrastando, sem que um gráfico fique ilegível ao ser reduzido. Antes, todo widget aceitava qualquer tamanho a partir de 2×2 e mostrava sempre a mesma visão (um gráfico de linha 2×2 virava um rabisco), e o layout só era gravado com o botão *Salvar layout*.

## Decisão

1. **Dois limites por tipo** (`WIDGET_TYPES` no backend, espelhado em `frontend/src/features/widgets/sizes.ts`):
   - *mínimo completo* (`min_w`/`min_h`): menor tamanho da visão completa (linha 4×3, barras/pizza 3×3, tabela 4×3, medidor 2×3, KPI 2×2);
   - *mínimo absoluto* (`COMPACT_MIN` = 2×2): nenhum gráfico fica menor. O backend recusa (`422 widget_too_small`) em `PUT /layout` e `POST /widgets`.
2. **Entre os dois limites, a visão compacta do tipo**, escolhida só pelo tamanho na grade (`w`/`h`), por isso fica igual no desktop, no celular e na TV:
   linha → valor atual + variação + mini tendência; barras → ranking em lista; pizza → participação em %; tabela → lista curta; medidor → % da meta com barra.
   Nada muda no `QuerySpec` nem no dado: é só outro renderer no registry (`COMPACT_REGISTRY`).
3. **No editor**, a troca acontece ao vivo enquanto o usuário arrasta o canto; uma etiqueta "compacta" explica o que mudou. Ele decide se gosta: aumentar volta à visão completa.
4. **Layout salvo ao soltar** (arrastar ou redimensionar), em fila e com `If-Match` encadeado; conflito de versão abre o aviso padrão do editor. O botão *Salvar layout* saiu; o cabeçalho mostra "Salvando layout…/Layout salvo".
5. Redimensionar continua sendo só no **editor** (`dashboard:edit`). Quem só visualiza não altera o painel compartilhado.

## Consequências

- Widgets já salvos abaixo do mínimo completo passam a aparecer na visão compacta (no banco de desenvolvimento em 31/10/2026 não havia nenhum).
- Mudou o tamanho mínimo de um tipo: atualizar `WIDGET_TYPES` e `sizes.ts` juntos.
- A IA (ADR 0010, decisão 12) usa os mesmos limites: gráfico novo nasce na visão completa; reduzir um existente abaixo do completo é sinalizado como "fica na visão compacta".
