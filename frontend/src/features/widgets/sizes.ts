/**
 * Tamanhos na grade de 12 colunas (espelha WIDGET_TYPES/COMPACT_MIN do backend).
 * full: menor tamanho da visao completa. Entre COMPACT_MIN e full o widget mostra a visao compacta.
 */
export const COMPACT_MIN = { w: 2, h: 2 } as const;

export const FULL_MIN: Record<string, { w: number; h: number }> = {
  kpi: { w: 2, h: 2 }, gauge: { w: 2, h: 3 }, line: { w: 4, h: 3 }, bar: { w: 3, h: 3 }, pie: { w: 3, h: 3 }, table: { w: 4, h: 3 },
};

/** Tamanho padrao de um widget novo (visao completa com folga). */
export const DEFAULT_SIZE: Record<string, { w: number; h: number }> = {
  kpi: { w: 3, h: 3 }, gauge: { w: 3, h: 3 }, line: { w: 8, h: 4 }, bar: { w: 6, h: 4 }, pie: { w: 4, h: 4 }, table: { w: 6, h: 4 },
};

export function isCompact(type: string, w: number, h: number): boolean {
  const f = FULL_MIN[type];
  return !!f && (w < f.w || h < f.h);
}

export const COMPACT_LABEL: Record<string, string> = {
  line: "valor atual e tendência", bar: "ranking", pie: "participação em lista", table: "lista curta", gauge: "percentual da meta",
};
