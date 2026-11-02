import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { Filter, Override, PeriodSel } from "../dashboards/useDashboardData";
import type { Viz, Widget } from "../widgets/types";

/** Filtro da analise. `src` separa o que veio do clique (breadcrumb) do que foi montado na barra de filtros. */
export type AFilter = Filter & { src: "drill" | "manual"; time?: boolean };
export type AView = { period: PeriodSel | null; filters: AFilter[]; focus: string | null };

export const EMPTY_VIEW: AView = { period: null, filters: [], focus: null };
const LIMIT = 20;

// ---------- URL <-> visao ----------
type Tuple = [string, string, unknown, "d" | "m", (0 | 1)?];

export function parseView(sp: URLSearchParams): AView {
  let period: PeriodSel | null = null;
  const p = sp.get("p"); const from = sp.get("from"); const to = sp.get("to");
  if (from && to && /^\d{4}-\d{2}-\d{2}$/.test(from) && /^\d{4}-\d{2}-\d{2}$/.test(to)) period = { mode: "absolute", from, to };
  else if (p && /^[a-z_0-9]{2,24}$/.test(p)) period = { mode: "relative", preset: p };
  let filters: AFilter[] = [];
  try {
    const raw = JSON.parse(sp.get("f") ?? "[]") as Tuple[];
    if (Array.isArray(raw)) {
      filters = raw.filter((t) => Array.isArray(t) && typeof t[0] === "string" && typeof t[1] === "string").slice(0, LIMIT)
        .map((t) => ({ field: t[0], op: t[1] as Filter["op"], value: t[2], src: t[3] === "d" ? "drill" as const : "manual" as const, ...(t[4] ? { time: true } : {}) }));
    }
  } catch { /* URL adulterada: ignora e abre sem filtros */ }
  return { period, filters, focus: sp.get("w") };
}

export function serializeView(v: AView): URLSearchParams {
  const sp = new URLSearchParams();
  if (v.period?.mode === "relative") sp.set("p", v.period.preset);
  if (v.period?.mode === "absolute") { sp.set("from", v.period.from); sp.set("to", v.period.to); }
  if (v.filters.length) sp.set("f", JSON.stringify(v.filters.map((f): Tuple => [f.field, f.op, f.value, f.src === "drill" ? "d" : "m", f.time ? 1 : 0])));
  if (v.focus) sp.set("w", v.focus);
  return sp;
}

export function useAnalysisView() {
  const [sp, setSp] = useSearchParams();
  const raw = sp.toString();
  const view = useMemo(() => parseView(new URLSearchParams(raw)), [raw]);
  /** `push`: cada passo de drill entra no historico (voltar do navegador desfaz o drill). */
  const set = useCallback((next: AView | ((v: AView) => AView), push = true) => {
    setSp((cur) => serializeView(typeof next === "function" ? next(parseView(cur)) : next), { replace: !push });
  }, [setSp]);
  return [view, set] as const;
}

export const toApiFilters = (fs: AFilter[]): Filter[] => fs.map(({ field, op, value }) => ({ field, op, value }));

// ---------- drill ----------
export const pathOf = (w: Pick<Widget, "viz_config">): string[] => {
  const v = (w.viz_config ?? {}) as Viz;
  return v.drill_path?.length ? v.drill_path : v.drill_field ? [v.drill_field] : [];
};

/** Quantos niveis da hierarquia ja foram "descidos": campos consecutivos do inicio da trilha com filtro de drill. */
export function drillLevel(path: string[], filters: AFilter[]): number {
  let n = 0;
  while (n < path.length && filters.some((f) => f.src === "drill" && !f.time && f.op === "eq" && f.field === path[n])) n++;
  return n;
}

export const GRANS = ["year", "quarter", "month", "week", "day"] as const;
export type Gran = (typeof GRANS)[number];
export const nextGran = (g: Gran): Gran | null => (g === "year" ? "quarter" : g === "quarter" ? "month" : g === "month" || g === "week" ? "day" : null);

/** Granularidade depois de `steps` descidas a partir de `base`. */
export function granAfter(base: Gran, steps: number): Gran {
  let g = base;
  for (let i = 0; i < steps; i++) g = nextGran(g) ?? g;
  return g;
}

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Intervalo [de, ate] (inclusivo) coberto pelo ponto `day` na granularidade `g`. */
export function timeRange(day: string, g: Gran): [string, string] {
  const [y, m, d] = day.slice(0, 10).split("-").map(Number);
  const utc = (yy: number, mm: number, dd: number) => new Date(Date.UTC(yy, mm, dd));
  if (g === "year") return [iso(utc(y, 0, 1)), iso(utc(y, 11, 31))];
  if (g === "quarter") { const q = Math.floor((m - 1) / 3) * 3; return [iso(utc(y, q, 1)), iso(utc(y, q + 3, 0))]; }
  if (g === "month") return [iso(utc(y, m - 1, 1)), iso(utc(y, m, 0))];
  if (g === "week") return [iso(utc(y, m - 1, d)), iso(utc(y, m - 1, d + 6))];
  return [iso(utc(y, m - 1, d)), iso(utc(y, m - 1, d))];
}

export type Plan = { overrides: Record<string, Override>; level: Record<string, number>; gran: Record<string, Gran | undefined> };

/** Para cada widget: em que nivel da hierarquia esta e em que granularidade a serie deve ser pedida. */
export function planOverrides(widgets: Widget[], filters: AFilter[], timeFieldOf: (w: Widget) => string | undefined): Plan {
  const plan: Plan = { overrides: {}, level: {}, gran: {} };
  for (const w of widgets) {
    const qc = w.query_config as { columns?: string[]; time?: { granularity?: Gran } };
    const path = pathOf(w);
    const lvl = drillLevel(path, filters);
    plan.level[w.id] = lvl;
    const ov: Override = {};
    if (lvl > 0 && path.length > 1 && !qc.columns?.length && ["bar", "pie", "table", "line"].includes(w.type)) ov.group_by = path[Math.min(lvl, path.length - 1)];
    if (w.type === "line" && qc.time) {
      const tf = timeFieldOf(w);
      const steps = tf ? filters.filter((f) => f.time && f.field === tf).length : 0;
      const g = granAfter(qc.time.granularity ?? "month", steps);
      plan.gran[w.id] = g;
      if (steps > 0) ov.granularity = g;
    }
    if (ov.group_by || ov.granularity) plan.overrides[w.id] = ov;
  }
  return plan;
}

/** Widget como sera desenhado: dimensao/granularidade trocadas e clique apontando para o campo exibido. */
export function effectiveWidget(w: Widget, ov: Override | undefined): Widget {
  const qc = w.query_config as { dimensions?: string[]; time?: { granularity?: string } };
  const viz = (w.viz_config ?? {}) as Viz;
  const dim = ov?.group_by ?? qc.dimensions?.[0];
  const drillable = !!(viz.drill_field || viz.drill_path?.length);
  const query_config = { ...qc, ...(ov?.group_by ? { dimensions: [ov.group_by] } : {}), ...(ov?.granularity && qc.time ? { time: { ...qc.time, granularity: ov.granularity } } : {}) };
  const viz_config = drillable && dim && w.type !== "line" && !(w.query_config as { columns?: string[] }).columns?.length ? { ...viz, drill_field: dim } : viz;
  return { ...w, query_config, viz_config } as Widget;
}

// ---------- filtros ----------
/** Filtros de drill ate o n-esimo (inclusive) + todos os manuais: breadcrumb "volta ate aqui". */
export function truncateDrill(filters: AFilter[], keepDrill: number): AFilter[] {
  let seen = 0;
  return filters.filter((f) => f.src !== "drill" || ++seen <= keepDrill);
}

export const drillCrumbs = (filters: AFilter[]) => filters.filter((f) => f.src === "drill");

/** Adiciona um filtro de drill substituindo outro de drill no mesmo campo/valor ja existente. */
export function addDrill(filters: AFilter[], f: Omit<AFilter, "src">): AFilter[] {
  if (filters.some((x) => x.src === "drill" && x.field === f.field && x.op === f.op && JSON.stringify(x.value) === JSON.stringify(f.value))) return filters;
  const base = f.time ? filters : filters.filter((x) => !(x.src === "drill" && !x.time && x.field === f.field));
  return [...base, { ...f, src: "drill" as const }].slice(0, LIMIT);
}

export const OP_LABEL: Record<string, string> = { eq: "=", in: "é", neq: "não é", contains: "contém", gte: "≥", lte: "≤", between: "entre" };

export function describeValue(f: Filter, fmtVal: (v: unknown) => string = String): string {
  if (f.op === "between" && Array.isArray(f.value)) return `${fmtVal(f.value[0])} – ${fmtVal(f.value[1])}`;
  if (Array.isArray(f.value)) return f.value.length > 2 ? `${f.value.slice(0, 2).map(fmtVal).join(", ")} +${f.value.length - 2}` : f.value.map(fmtVal).join(", ");
  return fmtVal(f.value);
}
