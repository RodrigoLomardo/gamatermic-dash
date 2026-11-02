import { useMemo } from "react";
import { Chart, cssVar, palette } from "@/shared/ui/Chart";
import { cx } from "@/shared/ui/ui";
import { deltaPct, fmt, fmtDate, fmtPeriod, toNum } from "@/shared/lib/format";
import type { RenderProps, Row, Viz } from "./types";

const EMPTY: Row[] = [];
const vz = (p: RenderProps) => (p.widget.viz_config ?? {}) as Viz;
const keysOf = (rows: Row[], skip: string[] = []) => Object.keys(rows[0] ?? {}).filter((k) => !skip.includes(k));

function colorFor(name: string | undefined, fallback: string): string {
  if (name === "danger") return cssVar("--danger");
  if (name === "accent" || name === "primary") return cssVar("--chart-1");
  return fallback;
}

export function Kpi({ widget, result, tv }: RenderProps) {
  const v = vz({ widget, result, tv });
  const row = result.data?.[0] ?? {};
  const key = Object.keys(row)[0];
  const cur = key ? toNum(row[key]) : 0;
  const prev = result.previous?.[0] && key ? toNum(result.previous[0][key]) : null;
  const d = prev != null ? deltaPct(cur, prev) : null;
  const good = v.color === "danger" ? (d ?? 0) <= 0 : (d ?? 0) >= 0;
  return (
    <div className="flex h-full flex-col justify-center">
      <div className={cx("tabular font-extrabold leading-tight text-ink", tv ? "whitespace-nowrap text-[clamp(1.6rem,2.5vw,3rem)]" : "whitespace-nowrap text-[clamp(1.4rem,2vw,2.1rem)]")}
        style={v.color ? { color: colorFor(v.color, "") || undefined } : undefined}>
        {key ? fmt(row[key], v.format ?? "number", true) : "—"}
      </div>
      {result.previous && (
        <div className={cx("mt-1 flex items-center gap-x-2", tv ? "flex-wrap text-[clamp(.75rem,1.05vw,1.15rem)]" : "text-sm")}>
          {d != null ? (
            <span className={cx("font-semibold", good ? "text-ok" : "text-danger")} aria-label={`variação de ${(d * 100).toFixed(1)} por cento`}>
              {d >= 0 ? "▲" : "▼"} {Math.abs(d * 100).toFixed(1).replace(".", ",")}%
            </span>
          ) : <span className="text-ink-mute">sem base</span>}
          <span className="text-ink-mute">vs período anterior ({fmt(prev, v.format ?? "number", true)})</span>
        </div>
      )}
    </div>
  );
}

export function Gauge({ widget, result, tv }: RenderProps) {
  const v = vz({ widget, result, tv });
  const row = result.data?.[0] ?? {};
  const val = toNum(Object.values(row)[0]);
  const target = v.target ?? v.max ?? 0;
  const pct = target ? val / target : 0;
  const option = useMemo(() => {
    const [c1] = palette();
    return {
      series: [{
        type: "gauge", startAngle: 200, endAngle: -20, min: 0, max: Math.max(target, val, 1), radius: "100%", center: ["50%", "70%"],
        progress: { show: true, width: tv ? 18 : 14, itemStyle: { color: pct >= 1 ? cssVar("--ok") : c1 } },
        axisLine: { lineStyle: { width: tv ? 18 : 14, color: [[1, cssVar("--line")]] } },
        axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false },
        detail: { valueAnimation: true, offsetCenter: [0, "-8%"], fontSize: tv ? 22 : 22, fontWeight: 800, color: cssVar("--ink"),
          formatter: () => `${Math.round(pct * 100)}%` },
        data: [{ value: val }],
      }],
    };
  }, [val, target, pct, tv]);
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1"><Chart option={option} label={`${widget.title}: ${Math.round(pct * 100)}% da meta`} /></div>
      <p className={cx("text-center tabular text-ink-soft", tv ? "text-[clamp(.7rem,1vw,1.1rem)]" : "text-xs")}>
        {fmt(val, v.format, true)} de {fmt(target, v.format, true)}
      </p>
    </div>
  );
}

function baseText(tv: boolean) {
  return { color: cssVar("--ink-soft"), fontSize: tv ? 16 : 12, fontFamily: "Inter Variable, system-ui, sans-serif" };
}

export function LineW({ widget, result, tv, onTimeDrill }: RenderProps) {
  const v = vz({ widget, result, tv });
  const rows = result.data ?? EMPTY;
  const gran = (widget.query_config as { time?: { granularity?: string } }).time?.granularity;
  const option = useMemo(() => {
    const cols = palette();
    const dims = keysOf(rows, ["time"]);
    const qc = widget.query_config as { dimensions?: string[]; measures?: { alias: string }[]; time?: { granularity?: string } };
    const dimKey = qc.dimensions?.[0];
    const measureKeys = dims.filter((k) => k !== dimKey);
    const times = [...new Set(rows.map((r) => String(r.time)))].sort();
    const series = dimKey
      ? [...new Set(rows.map((r) => String(r[dimKey])))].map((g, i) => ({
          name: g, type: "line", smooth: true, symbol: "none", color: cols[i % cols.length],
          data: times.map((t) => toNum(rows.find((r) => String(r.time) === t && String(r[dimKey]) === g)?.[measureKeys[0]])),
        }))
      : measureKeys.map((k, i) => ({
          name: k, type: "line", smooth: true, symbol: "circle", symbolSize: tv ? 9 : 6, color: colorFor(v.color, cols[i % cols.length]),
          lineStyle: { width: tv ? 4 : 3 }, areaStyle: { opacity: 0.12 },
          data: times.map((t) => toNum(rows.find((r) => String(r.time) === t)?.[k])),
        }));
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", valueFormatter: (x: number) => fmt(x, v.format) },
      legend: series.length > 1 ? { bottom: 0, textStyle: baseText(tv) } : undefined,
      xAxis: { type: "category", data: times.map((t) => fmtPeriod(t, gran)), axisLabel: baseText(tv), axisLine: { lineStyle: { color: cssVar("--line") } } },
      yAxis: { type: "value", axisLabel: { ...baseText(tv), formatter: (x: number) => fmt(x, v.format, true).replace("R$ ", "") }, splitLine: { lineStyle: { color: cssVar("--line") } } },
      series,
    };
  }, [rows, v.format, v.color, tv, widget.query_config, gran]);
  if (!rows.length) return <NoData />;
  const times = [...new Set(rows.map((r) => String(r.time)))].sort();
  return <Chart option={option} label={widget.title} onIndexClick={onTimeDrill ? (i) => times[i] && onTimeDrill(times[i].slice(0, 10)) : undefined} />;
}

export function BarW({ widget, result, tv, onDrill }: RenderProps) {
  const v = vz({ widget, result, tv });
  const rows = result.data ?? EMPTY;
  const qc = widget.query_config as { dimensions?: string[]; measures?: { alias: string }[] };
  const dim = qc.dimensions?.[0] ?? "";
  const mk = qc.measures?.[0]?.alias ?? "";
  const option = useMemo(() => {
    const ordered = v.horizontal ? [...rows].reverse() : rows;
    const dense = tv && ordered.length > 6;
    const txt = { ...baseText(tv), fontSize: dense ? 13 : baseText(tv).fontSize };
    const cat = ordered.map((r) => String(r[dim] ?? "—"));
    const vals = ordered.map((r) => toNum(r[mk]));
    const label = { show: true, position: v.horizontal ? "right" : "top", formatter: (p: { value: number }) => fmt(p.value, v.format, true).replace("R$ ", ""), ...txt };
    return {
      grid: { left: 8, right: v.horizontal ? 64 : 12, top: 16, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (x: number) => fmt(x, v.format) },
      xAxis: v.horizontal ? { type: "value", show: false } : { type: "category", data: cat, axisLabel: { ...txt, interval: 0, width: 90, overflow: "truncate" } },
      yAxis: v.horizontal ? { type: "category", data: cat, axisLabel: { ...txt, interval: 0, width: tv ? 200 : 120, overflow: "truncate" }, axisLine: { show: false }, axisTick: { show: false } } : { type: "value", show: false },
      series: [{ type: "bar", data: vals, barMaxWidth: dense ? 16 : tv ? 40 : 26, itemStyle: { color: colorFor(v.color, cssVar("--chart-1")), borderRadius: 4 }, label }],
    };
  }, [rows, dim, mk, v.horizontal, v.format, v.color, tv]);
  if (!rows.length) return <NoData />;
  return <Chart option={option} label={widget.title} onClick={(p) => v.drill_field && onDrill?.(v.drill_field, String(p.name))} />;
}

export function PieW({ widget, result, tv, onDrill }: RenderProps) {
  const v = vz({ widget, result, tv });
  const rows = result.data ?? EMPTY;
  const qc = widget.query_config as { dimensions?: string[]; measures?: { alias: string }[] };
  const dim = qc.dimensions?.[0] ?? "";
  const mk = qc.measures?.[0]?.alias ?? "";
  const option = useMemo(() => ({
    color: palette(),
    tooltip: { trigger: "item", valueFormatter: (x: number) => fmt(x, v.format) },
    legend: { orient: "vertical", right: 0, top: "middle", textStyle: baseText(tv), icon: "circle" },
    series: [{
      type: "pie", radius: ["48%", "78%"], center: ["36%", "50%"], avoidLabelOverlap: true, label: { show: false },
      itemStyle: { borderColor: cssVar("--panel"), borderWidth: 2 },
      data: rows.map((r) => ({ name: String(r[dim] ?? "—"), value: toNum(r[mk]) })),
    }],
  }), [rows, dim, mk, v.format, tv]);
  if (!rows.length) return <NoData />;
  return <Chart option={option} label={widget.title} onClick={(p) => v.drill_field && onDrill?.(v.drill_field, String(p.name))} />;
}

export function TableW({ widget, result, tv, onDrill }: RenderProps) {
  const v = vz({ widget, result, tv });
  const rows = result.data ?? EMPTY;
  const cols = v.columns?.length ? v.columns : keysOf(rows).map((k) => ({ field: k, label: k, format: undefined }));
  if (!rows.length) return <NoData />;
  return (
    <div className="h-full overflow-auto">
      <table className={cx("w-full text-left", tv ? "text-[clamp(.85rem,1.25vw,1.35rem)]" : "text-sm")}>
        <thead className="sticky top-0 bg-panel">
          <tr className="border-b border-line text-xs uppercase tracking-wide text-ink-mute">
            {cols.map((c) => <th key={c.field} scope="col" className={cx("px-2 py-1.5 font-semibold", c.format && c.format !== "date" && "text-right")}>{c.label ?? c.field}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r, i) => (
            <tr key={i} className={cx(v.drill_field && "cursor-pointer hover:bg-brand-soft")}
              onClick={() => v.drill_field && r[v.drill_field] != null && onDrill?.(v.drill_field, String(r[v.drill_field]))}>
              {cols.map((c) => {
                const raw = r[c.field];
                const numeric = c.format && c.format !== "date";
                return (
                  <td key={c.field} className={cx("px-2 py-1.5 text-ink", numeric && "tabular text-right font-medium")}>
                    {c.format === "date" && raw ? fmtDate(String(raw)) : c.format ? fmt(raw, c.format) : String(raw ?? "—")}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function NoData() {
  return <div className="flex h-full items-center justify-center text-sm text-ink-mute">Sem dados no período</div>;
}
