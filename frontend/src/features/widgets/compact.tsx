import { useMemo } from "react";
import { Chart, cssVar } from "@/shared/ui/Chart";
import { cx } from "@/shared/ui/ui";
import { deltaPct, fmt, fmtMonth, toNum } from "@/shared/lib/format";
import { NoData } from "./renderers";
import type { RenderProps, Row, Viz } from "./types";

// Visoes compactas: o que cada grafico mostra quando o usuario o reduz abaixo do tamanho completo.
type QC = { dimensions?: string[]; measures?: { alias: string }[]; columns?: string[] };
const qcOf = (p: RenderProps) => (p.widget.query_config ?? {}) as QC;
const vzOf = (p: RenderProps) => (p.widget.viz_config ?? {}) as Viz;

/** Linha -> ultimo valor, variacao contra o ponto anterior e mini tendencia. */
export function LineCompact(p: RenderProps) {
  const v = vzOf(p); const data = p.result.data;
  const rows = useMemo(() => data ?? [], [data]);
  const mk = qcOf(p).measures?.[0]?.alias ?? Object.keys(rows[0] ?? {}).find((k) => k !== "time") ?? "";
  const series = useMemo(() => {
    const by = new Map<string, number>();
    for (const r of rows) by.set(String(r.time), (by.get(String(r.time)) ?? 0) + toNum(r[mk])); // soma as series do mesmo periodo
    return [...by.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [rows, mk]);
  const option = useMemo(() => ({
    grid: { left: 0, right: 0, top: 4, bottom: 0 }, xAxis: { type: "category", show: false, data: series.map(([t]) => t) },
    yAxis: { type: "value", show: false, scale: true },
    series: [{ type: "line", smooth: true, symbol: "none", data: series.map(([, x]) => x), lineStyle: { width: 2, color: cssVar("--chart-1") }, areaStyle: { opacity: 0.12, color: cssVar("--chart-1") } }],
  }), [series]);
  if (!series.length) return <NoData />;
  const [lastT, last] = series[series.length - 1];
  const prev = series.length > 1 ? series[series.length - 2][1] : null;
  const d = prev != null ? deltaPct(last, prev) : null;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={cx("tabular truncate font-extrabold leading-tight text-ink", p.tv ? "text-[clamp(1.2rem,2vw,2.4rem)]" : "text-xl")}>{fmt(last, v.format ?? "number", true)}</div>
      <div className="flex items-center gap-1 text-xs text-ink-mute">
        <span>{fmtMonth(lastT)}</span>
        {d != null && <span className={cx("font-semibold", d >= 0 ? "text-ok" : "text-danger")}>{d >= 0 ? "▲" : "▼"} {Math.abs(d * 100).toFixed(1).replace(".", ",")}%</span>}
      </div>
      <div className="min-h-0 flex-1"><Chart option={option} label={`Tendência de ${p.widget.title}`} /></div>
    </div>
  );
}

function Ranking({ p, items, share }: { p: RenderProps; items: { name: string; value: number }[]; share: boolean }) {
  const v = vzOf(p);
  const total = items.reduce((a, b) => a + b.value, 0);
  const max = Math.max(...items.map((i) => i.value), 0);
  if (!items.length) return <NoData />;
  return (
    <ol className={cx("h-full space-y-1 overflow-hidden", p.tv ? "text-[clamp(.75rem,1.05vw,1.15rem)]" : "text-xs")}>
      {items.map((it, i) => (
        <li key={i} className={cx("relative flex items-center justify-between gap-2 rounded px-1.5 py-0.5", v.drill_field && "cursor-pointer hover:bg-brand-soft")}
          onClick={() => v.drill_field && p.onDrill?.(v.drill_field, it.name)}>
          <span aria-hidden className="absolute inset-y-0 left-0 rounded bg-brand-soft" style={{ width: `${max ? (it.value / max) * 100 : 0}%` }} />
          <span className="relative truncate text-ink">{i + 1}. {it.name}</span>
          <span className="relative tabular shrink-0 font-semibold text-ink">
            {share && total ? `${((it.value / total) * 100).toFixed(0)}%` : fmt(it.value, v.format ?? "number", true)}
          </span>
        </li>
      ))}
    </ol>
  );
}

const rank = (rows: Row[], dim: string, mk: string) =>
  rows.map((r) => ({ name: String(r[dim] ?? "—"), value: toNum(r[mk]) })).sort((a, b) => b.value - a.value).slice(0, 8);

/** Barras -> ranking em lista. */
export function BarCompact(p: RenderProps) {
  const qc = qcOf(p);
  return <Ranking p={p} items={rank(p.result.data ?? [], qc.dimensions?.[0] ?? "", qc.measures?.[0]?.alias ?? "")} share={false} />;
}

/** Pizza -> participacao (%) em lista. */
export function PieCompact(p: RenderProps) {
  const qc = qcOf(p);
  return <Ranking p={p} items={rank(p.result.data ?? [], qc.dimensions?.[0] ?? "", qc.measures?.[0]?.alias ?? "")} share />;
}

/** Tabela -> lista curta: 1a coluna como nome e a ultima numerica como valor. */
export function TableCompact(p: RenderProps) {
  const rows = p.result.data ?? [];
  const qc = qcOf(p); const v = vzOf(p);
  const cols = v.columns?.map((c) => c.field) ?? Object.keys(rows[0] ?? {});
  const name = qc.dimensions?.[0] ?? cols[0] ?? "";
  const num = qc.measures?.[0]?.alias ?? [...cols].reverse().find((c) => c !== name && rows.some((r) => r[c] != null && !isNaN(Number(r[c])))) ?? "";
  const items = rows.slice(0, 8).map((r) => ({ name: String(r[name] ?? "—"), value: toNum(r[num]) }));
  const colFmt = v.columns?.find((c) => c.field === num)?.format;
  return <Ranking p={{ ...p, widget: { ...p.widget, viz_config: { ...v, format: colFmt && colFmt !== "date" ? colFmt : v.format } } }} items={items} share={false} />;
}

/** Medidor -> percentual da meta com barra. */
export function GaugeCompact(p: RenderProps) {
  const v = vzOf(p);
  const val = toNum(Object.values(p.result.data?.[0] ?? {})[0]);
  const target = v.target ?? v.max ?? 0;
  const pct = target ? val / target : 0;
  return (
    <div className="flex h-full flex-col justify-center gap-1">
      <div className={cx("tabular font-extrabold text-ink", p.tv ? "text-[clamp(1.2rem,2vw,2.4rem)]" : "text-xl")}>{Math.round(pct * 100)}%</div>
      <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct * 100)} aria-label={`${p.widget.title}: percentual da meta`}>
        <div className={cx("h-full rounded-full", pct >= 1 ? "bg-ok" : "bg-accent")} style={{ width: `${Math.min(pct, 1) * 100}%` }} />
      </div>
      <p className="truncate text-xs text-ink-mute">{fmt(val, v.format, true)} de {fmt(target, v.format, true)}</p>
    </div>
  );
}
