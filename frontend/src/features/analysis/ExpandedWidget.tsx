import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { IconDownload, IconRows, IconX } from "@/app/icons";
import { useAuth } from "@/app/auth";
import { post } from "@/shared/api/http";
import { Select, cx, useToasts } from "@/shared/ui/ui";
import type { Filter, Override, PeriodSel } from "../dashboards/useDashboardData";
import { WidgetCard } from "../widgets/WidgetCard";
import type { DrillHandler, TimeDrillHandler, Viz, Widget, WidgetResult } from "../widgets/types";
import { FieldInfo, downloadCsv } from "./hooks";

const LABEL: Record<string, string> = { bar: "Barras", pie: "Pizza", line: "Linha", table: "Tabela" };
const LIMITS = [10, 30, 50];

/** Tela cheia de um widget: troca visual e "agrupar por" sem gravar nada no painel. Abre/fecha a partir do card (FLIP). */
export function ExpandedWidget({ id, widget, initial, from, period, filters, fields, onClose, onDrill, onTimeDrill, onRecords }: {
  id: string; widget: Widget; initial?: Override; from: DOMRect | null; period: PeriodSel | null; filters: Filter[]; fields: FieldInfo[];
  onClose: () => void; onDrill: DrillHandler; onTimeDrill?: TimeDrillHandler; onRecords: () => void;
}) {
  const { can } = useAuth(); const toast = useToasts((s) => s.push);
  const qc = widget.query_config as { dimensions?: string[]; columns?: string[]; time?: unknown };
  const viz = (widget.viz_config ?? {}) as Viz;
  const shape: "dim" | "time" | "fixed" = qc.columns?.length ? "fixed" : qc.time ? "time" : widget.type === "kpi" || widget.type === "gauge" ? "fixed" : "dim";
  const types = shape === "dim" ? ["bar", "pie", "table"] : shape === "time" ? ["line", "table"] : [widget.type];
  const [type, setType] = useState(widget.type);
  const [group, setGroup] = useState<string | undefined>(initial?.group_by); // parte do nivel de drill em que o card esta
  const [limit, setLimit] = useState<number | undefined>(shape === "dim" ? (widget.type === "pie" ? 10 : 30) : undefined);
  const dims = useMemo(() => fields.filter((f) => f.datasetIds.includes(widget.dataset_id ?? "") && f.role === "dimension"), [fields, widget.dataset_id]);
  const dim = group ?? qc.dimensions?.[0];
  const override = { ...(group ? { group_by: group } : {}), ...(initial?.granularity ? { granularity: initial.granularity } : {}), ...(limit ? { limit } : {}) };
  const q = useQuery({
    queryKey: ["analysis-expanded", id, widget.id, period, filters, override], placeholderData: (p) => p,
    queryFn: () => post<WidgetResult>(`/dashboards/${id}/analysis/query`, { widget_id: widget.id, period, force_period: period !== null, filters, override: Object.keys(override).length ? override : null }),
  });
  const synthetic = useMemo(() => ({
    ...widget, type, query_config: { ...qc, ...(group ? { dimensions: [group] } : {}), ...(initial?.granularity && qc.time ? { time: { ...(qc.time as object), granularity: initial.granularity } } : {}) },
    viz_config: { ...viz, ...(group ? { columns: undefined } : {}), ...(dim && shape !== "time" ? { drill_field: dim } : {}), ...(type === "bar" && viz.horizontal === undefined ? { horizontal: true } : {}) },
  }) as Widget, [widget, type, group, dim, shape]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- animacao FLIP: do card ate a tela cheia (e de volta) ----
  const panel = useRef<HTMLDivElement>(null); const back = useRef<HTMLDivElement>(null); const closing = useRef(false);
  const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const delta = useCallback(() => {
    const to = panel.current!.getBoundingClientRect();
    return from ? `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width}, ${from.height / to.height})` : "scale(.94)";
  }, [from]);
  useEffect(() => {
    if (reduced() || !panel.current) return;
    panel.current.animate([{ transform: delta(), opacity: .35 }, { transform: "none", opacity: 1 }], { duration: 460, easing: "cubic-bezier(.2,.85,.25,1)" });
    back.current?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 320 });
  }, [delta]);
  const close = useCallback(() => {
    if (closing.current) return; closing.current = true;
    if (reduced() || !panel.current) return onClose();
    panel.current.animate([{ transform: "none", opacity: 1 }, { transform: delta(), opacity: 0 }], { duration: 300, easing: "cubic-bezier(.5,0,.75,0)", fill: "forwards" });
    back.current?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, fill: "forwards" });
    setTimeout(onClose, 290);
  }, [delta, onClose]);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null; panel.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", key); return () => { window.removeEventListener("keydown", key); prev?.focus?.(); };
  }, [close]);

  const exportCsv = async () => {
    try { await downloadCsv(`/dashboards/${id}/analysis/export`, { widget_id: widget.id, period, force_period: period !== null, filters }, `analise-${widget.title.toLowerCase().replace(/\W+/g, "-")}.csv`); toast("Exportação concluída."); }
    catch (e) { toast((e as Error).message, "danger"); }
  };
  return createPortal(
    <div className="fixed inset-0 z-50 p-3 md:p-8">
      <div ref={back} className="an-backdrop absolute inset-0" onMouseDown={close} />
      <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={`${widget.title} em tela cheia`} className="an-expanded relative mx-auto flex h-full max-w-7xl flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
          <h2 className="mr-auto min-w-0 truncate text-lg font-bold">{widget.title}</h2>
          {types.length > 1 && (
            <div role="group" aria-label="Tipo de visual" className="an-seg" style={{ "--n": types.length, "--idx": types.indexOf(type) } as React.CSSProperties}>
              <span className="an-seg-ind" aria-hidden="true" />
              {types.map((t) => <button key={t} type="button" aria-pressed={type === t} onClick={() => setType(t as Widget["type"])}>{LABEL[t]}</button>)}
            </div>
          )}
          {shape !== "fixed" && dims.length > 0 && (
            <label className="flex items-center gap-2 whitespace-nowrap text-sm text-ink-soft">{shape === "time" ? "Série por" : "Agrupar por"}
              <Select className="w-44" value={group ?? (shape === "time" ? "" : qc.dimensions?.[0] ?? "")} onChange={(e) => setGroup(e.target.value || undefined)}>
                {shape === "time" && <option value="">Sem série</option>}
                {dims.map((f) => <option key={f.name} value={f.name}>{f.label}</option>)}
              </Select>
            </label>
          )}
          {shape === "dim" && (
            <label className="flex items-center gap-2 whitespace-nowrap text-sm text-ink-soft">Exibir
              <Select className="w-20" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>{LIMITS.map((n) => <option key={n} value={n}>{n}</option>)}</Select>
            </label>
          )}
          <button type="button" className="an-btn" onClick={onRecords}><IconRows />Ver registros</button>
          {can("analysis:export") && <button type="button" className="an-btn" onClick={exportCsv}><IconDownload />CSV</button>}
          <button type="button" aria-label="Fechar tela cheia" className="an-icon-btn" onClick={close}><IconX width={16} height={16} /></button>
        </header>
        <div className={cx("min-h-0 flex-1 p-4 transition-opacity", q.isFetching && "opacity-70")}>
          <WidgetCard widget={synthetic} result={q.data} size={{ w: 12, h: 8 }} onDrill={onDrill} onTimeDrill={type === "line" ? onTimeDrill : undefined} />
        </div>
      </div>
    </div>,
    document.body,
  );
}
