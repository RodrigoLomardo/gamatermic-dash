/** Empacota widgets na grade de 12 colunas, na ordem dada: preenche a linha e quebra quando nao cabe. */
export function pack<T extends { w: number; h: number }>(items: T[], cols = 12): (T & { x: number; y: number })[] {
  let x = 0, y = 0, rowH = 0;
  return items.map((it) => {
    const w = Math.min(it.w, cols);
    if (x + w > cols) { y += rowH; x = 0; rowH = 0; }
    const out = { ...it, w, x, y };
    x += w; rowH = Math.max(rowH, it.h);
    return out;
  });
}

export const slugify = (s: string) =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);

export type Box = { x: number; y: number; w: number; h: number };
type Placed = Box & { id: string };

const overlaps = (a: Box, b: Box) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** Coloca `box` na posicao pedida e, se bater em algo ja colocado, desce ate caber (mesma coluna). */
function settle(box: Placed, placed: Placed[]): Placed {
  const b = { ...box };
  for (let guard = 0; guard < 500; guard++) {
    const hits = placed.filter((p) => overlaps(b, p));
    if (!hits.length) return b;
    b.y = Math.max(...hits.map((p) => p.y + p.h));
  }
  return b;
}

/** Sobe o grafico novo enquanto houver espaco livre acima (o editor ja mostra assim; evita buraco salvo no banco). */
function rise(box: Placed, placed: Placed[]): Placed {
  const b = { ...box };
  while (b.y > 0 && !placed.some((p) => overlaps({ ...b, y: b.y - 1 }, p))) b.y -= 1;
  return b;
}

/**
 * Layout final ao aceitar sugestoes da IA: graficos existentes (ja com as mudancas aceitas) primeiro,
 * depois os novos na posicao sugerida; o que colidir desce e o que ficar solto sobe. Novos sem posicao vao para o fim, empacotados.
 * Graficos existentes so mudam pelo que o usuario aceitou (ou se precisarem descer por colisao).
 */
export function arrange(existing: Placed[], incoming: (Partial<Box> & { id: string; w: number; h: number })[], cols = 12): Map<string, Box> {
  const placed: Placed[] = [];
  const byPos = (a: Box, b: Box) => a.y - b.y || a.x - b.x;
  for (const e of [...existing].sort(byPos)) placed.push(settle({ ...e, w: Math.min(e.w, cols), x: Math.min(e.x, cols - Math.min(e.w, cols)) }, placed));
  const withPos = incoming.filter((i) => i.x != null && i.y != null) as Placed[];
  for (const n of [...withPos].sort(byPos)) placed.push(rise(settle({ ...n, w: Math.min(n.w, cols), x: Math.min(n.x, cols - Math.min(n.w, cols)) }, placed), placed));
  const top = Math.max(0, ...placed.map((p) => p.y + p.h));
  for (const p of pack(incoming.filter((i) => i.x == null || i.y == null), cols)) placed.push(rise(settle({ id: p.id, x: p.x, y: top + p.y, w: p.w, h: p.h }, placed), placed));
  return new Map(placed.map(({ id, ...b }) => [id, b]));
}
