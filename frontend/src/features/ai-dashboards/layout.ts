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
