import { useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { IconDownload } from "@/app/icons";
import { useAuth } from "@/app/auth";
import { S, post } from "@/shared/api/http";
import { fmt, fmtDate, fmtDateTime } from "@/shared/lib/format";
import { Button, Empty, ErrorBox, cx, useToasts } from "@/shared/ui/ui";
import type { Filter, PeriodSel } from "../dashboards/useDashboardData";
import type { Widget } from "../widgets/types";
import { FieldInfo, downloadCsv, useCountUp, useOutside } from "./hooks";
import { Sheet } from "./Sheet";

type Rec = S["AnalysisRecordsOut"];
const PAGE = 50;

function cell(v: unknown, t: string) {
  if (v == null || v === "") return <span className="text-ink-mute">—</span>;
  if (t === "date") return fmtDate(String(v));
  if (t === "datetime") return fmtDateTime(String(v));
  if (t === "decimal") return fmt(v, "number");
  if (t === "integer") return String(v);
  if (t === "boolean") return v ? "Sim" : "Não";
  return String(v);
}

/** Drill-through: linhas de origem sob o periodo/filtros atuais, paginadas, com ordenacao e escolha de colunas. */
export function RecordsDrawer({ id, widget, period, filters, fields, onClose }: {
  id: string; widget: Widget; period: PeriodSel | null; filters: Filter[]; fields: FieldInfo[]; onClose: () => void;
}) {
  const { can } = useAuth(); const toast = useToasts((s) => s.push);
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState<{ by: string; dir: "asc" | "desc" } | null>(null);
  const [cols, setCols] = useState<string[]>([]);
  const [pick, setPick] = useState(false); const [busy, setBusy] = useState(false);
  const pop = useRef<HTMLDivElement>(null); useOutside(pop, () => setPick(false), pick);
  const base = { widget_id: widget.id, period, filters, columns: cols, sort };
  const q = useQuery({ queryKey: ["analysis-records", id, base, offset], placeholderData: (p) => p, queryFn: () => post<Rec>(`/dashboards/${id}/analysis/records`, { ...base, offset, limit: PAGE }) });
  const total = useCountUp(q.data?.total ?? 0);
  const shown = q.data?.columns ?? [];
  const choices = useMemo(() => fields.filter((f) => f.datasetIds.includes(widget.dataset_id ?? "")), [fields, widget.dataset_id]);
  const toggleCol = (n: string) => { setOffset(0); setCols((c) => { const cur = c.length ? c : shown.map((x) => x.name); const nx = cur.includes(n) ? cur.filter((x) => x !== n) : [...cur, n].slice(0, 12); return nx.length ? nx : cur; }); };
  const exportCsv = async () => {
    setBusy(true);
    try { await downloadCsv(`/dashboards/${id}/analysis/export`, { widget_id: widget.id, period, filters, columns: cols, sort }, `analise-${widget.title.toLowerCase().replace(/\W+/g, "-")}.csv`); toast("Exportação concluída."); }
    catch (e) { toast((e as Error).message, "danger"); } finally { setBusy(false); }
  };
  const clickSort = (n: string) => { setOffset(0); setSort((s) => (s?.by !== n ? { by: n, dir: "desc" } : s.dir === "desc" ? { by: n, dir: "asc" } : null)); };
  return (
    <Sheet onClose={onClose}
      title={<div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-mute">Registros de origem</p><h2 className="truncate text-xl font-bold">{widget.title}</h2></div>}
      actions={<>
        <div ref={pop} data-anchor className="relative">
          <Button variant="secondary" size="sm" aria-expanded={pick} onClick={() => setPick((p) => !p)}>Colunas</Button>
          {pick && (
            <div role="dialog" aria-label="Escolher colunas" className="an-pop right-0 top-[calc(100%+8px)] w-64 p-2">
              <ul className="an-list max-h-72 overflow-y-auto">
                {choices.map((f, i) => { const on = shown.some((c) => c.name === f.name); return (
                  <li key={f.name} style={{ "--i": Math.min(i, 10) } as React.CSSProperties}>
                    <button type="button" role="checkbox" aria-checked={on} className={cx("an-opt", on && "is-on")} onClick={() => toggleCol(f.name)}><span className="an-check" aria-hidden="true" /><span className="truncate">{f.label}</span></button>
                  </li>); })}
              </ul>
            </div>
          )}
        </div>
        {can("analysis:export") && <Button variant="secondary" size="sm" disabled={busy} onClick={exportCsv}><IconDownload />{busy ? "Gerando…" : "Exportar CSV"}</Button>}
      </>}>
      <div className="flex h-full flex-col">
        <div className="flex items-baseline gap-3 px-6 py-3 text-sm text-ink-soft">
          <span className="tabular text-3xl font-extrabold text-ink">{total.toLocaleString("pt-BR")}</span>
          <span>{q.data?.total === 1 ? "registro" : "registros"} com os filtros atuais</span>
          {q.isFetching && <span className="an-dots" aria-label="Atualizando"><i /><i /><i /></span>}
        </div>
        {q.error ? <div className="px-6"><ErrorBox error={q.error} onRetry={() => q.refetch()} /></div> : !q.data ? <div className="mx-6 h-64 animate-pulse rounded-xl bg-brand-soft" aria-busy="true" /> : q.data.rows.length === 0 ? <div className="px-6"><Empty>Nenhum registro para estes filtros.</Empty></div> : (
          <div className="min-h-0 flex-1 overflow-auto px-6">
            <table className="an-table w-full text-left text-sm">
              <thead><tr>{shown.map((c) => (
                <th key={c.name} scope="col" aria-sort={sort?.by === c.name ? (sort.dir === "asc" ? "ascending" : "descending") : "none"} className={cx(["integer", "decimal"].includes(c.data_type) && "text-right")}>
                  <button type="button" onClick={() => clickSort(c.name)} className="an-th">{c.label}<span aria-hidden="true" className={cx("an-sort", sort?.by === c.name && "is-on", sort?.by === c.name && sort.dir === "asc" && "is-asc")} /></button>
                </th>))}</tr></thead>
              <tbody key={`${offset}-${JSON.stringify(sort)}`}>
                {q.data.rows.map((r, i) => (
                  <tr key={i} style={{ "--i": Math.min(i, 14) } as React.CSSProperties}>
                    {shown.map((c) => <td key={c.name} className={cx(["integer", "decimal"].includes(c.data_type) && "tabular text-right", c.sensitivity === "pii" && "text-ink-mute")}>{cell(r[c.name], c.data_type)}</td>)}
                  </tr>))}
              </tbody>
            </table>
          </div>
        )}
        {q.data && q.data.total > PAGE && (
          <footer className="flex items-center justify-between border-t border-line px-6 py-3 text-sm text-ink-soft">
            <span className="tabular">{offset + 1}–{Math.min(offset + PAGE, q.data.total)} de {q.data.total.toLocaleString("pt-BR")}</span>
            <span className="flex gap-2"><Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Anterior</Button><Button variant="secondary" size="sm" disabled={!q.data.has_more} onClick={() => setOffset(offset + PAGE)}>Próxima</Button></span>
          </footer>
        )}
      </div>
    </Sheet>
  );
}
