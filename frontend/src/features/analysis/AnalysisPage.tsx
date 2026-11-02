import { useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { IconChevronRight, IconExpand, IconRows, IconUndo } from "@/app/icons";
import { fmtDateTime } from "@/shared/lib/format";
import { Badge, Button, Empty, ErrorBox, Spinner, cx } from "@/shared/ui/ui";
import { useMedia } from "@/shared/hooks/useMedia";
import { PeriodSel, useDashboard, useDashboardData } from "../dashboards/useDashboardData";
import { WidgetCard } from "../widgets/WidgetCard";
import type { Widget, WidgetResult } from "../widgets/types";
import { ExpandedWidget } from "./ExpandedWidget";
import { FilterBar } from "./FilterBar";
import { PeriodControl } from "./PeriodControl";
import { RecordsDrawer } from "./RecordsDrawer";
import { SearchBox } from "./SearchBox";
import { ViewsMenu } from "./ViewsMenu";
import { fieldIndex, fmtVal, useAnalysisFields } from "./hooks";
import { AFilter, EMPTY_VIEW, addDrill, describeValue, drillCrumbs, effectiveWidget, pathOf, planOverrides, timeRange, toApiFilters, truncateDrill, useAnalysisView } from "./state";

type Cell = { w: Widget; r?: WidgetResult; level: number; path: string[]; ov?: { group_by?: string } };

function AnalysisCell({ cell, i, labelOf, onDrill, onTimeDrill, onExpand, onRecords, drilled }: {
  cell: Cell; i: number; labelOf: (f: string) => string; drilled: boolean;
  onDrill: (w: Widget) => (f: string, v: string) => void; onTimeDrill: (w: Widget) => ((iso: string) => void) | undefined;
  onExpand: (w: Widget, rect: DOMRect) => void; onRecords: (w: Widget) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { w, r, level, path } = cell;
  const ignored = r?.ignored_filters ?? [];
  const eff = useMemo(() => effectiveWidget(w, cell.ov), [w, cell.ov]);
  return (
    <div ref={ref} className="an-cell group relative h-full" style={{ "--i": Math.min(i, 12) } as React.CSSProperties} data-drilled={drilled || undefined}>
      <WidgetCard widget={eff} result={r} onDrill={onDrill(w)} onTimeDrill={onTimeDrill(w)} />
      <div className="an-tools" role="toolbar" aria-label={`Ações de ${w.title}`}>
        <button type="button" aria-label={`Expandir ${w.title}`} title="Tela cheia" onClick={() => ref.current && onExpand(w, ref.current.getBoundingClientRect())}><IconExpand /></button>
        <button type="button" aria-label={`Ver registros de ${w.title}`} title="Ver registros" onClick={() => onRecords(w)}><IconRows /></button>
      </div>
      {path.length > 1 && level > 0 && (
        <span className="an-level" key={level} title={`Hierarquia: ${path.map(labelOf).join(" › ")}`}>
          {path.slice(0, Math.min(level + 1, path.length)).map((p, k) => <i key={p} className={cx(k === Math.min(level, path.length - 1) && "is-cur")} />)}
          {labelOf(path[Math.min(level, path.length - 1)])}
        </span>
      )}
      {ignored.length > 0 && <span className="an-ignored" title={`O dataset deste gráfico não tem: ${ignored.map(labelOf).join(", ")}. O filtro não foi aplicado aqui.`}>filtro não se aplica · {ignored.map(labelOf).join(", ")}</span>}
    </div>
  );
}

export function AnalysisPage() {
  const { id } = useParams();
  const dash = useDashboard(id);
  const [view, setView] = useAnalysisView();
  const fieldsQ = useAnalysisFields(id);
  const fields = useMemo(() => fieldIndex(fieldsQ.data), [fieldsQ.data]);
  const [adding, setAdding] = useState(false);
  const [presetField, setPresetField] = useState<string | undefined>();
  const [expandFrom, setExpandFrom] = useState<DOMRect | null>(null);
  const [recordsFor, setRecordsFor] = useState<string | null>(null);
  const desktop = useMedia("(min-width: 768px)");

  const widgets = useMemo(() => dash.data?.widgets ?? [], [dash.data]);
  const timeByDs = useMemo(() => new Map((fieldsQ.data?.datasets ?? []).map((d) => [d.dataset_id, d.time_field ?? undefined])), [fieldsQ.data]);
  const timeFieldOf = (w: Widget) => (w.dataset_id ? timeByDs.get(w.dataset_id) : undefined);
  const plan = useMemo(() => planOverrides(widgets, view.filters, (w) => (w.dataset_id ? timeByDs.get(w.dataset_id) : undefined)), [widgets, view.filters, timeByDs]);
  const apiFilters = useMemo(() => toApiFilters(view.filters), [view.filters]);
  const period: PeriodSel | null = view.period;
  const data = useDashboardData(id, period, apiFilters, dash.data?.refresh_interval_seconds ?? 60, plan.overrides);
  const results = useMemo(() => Object.fromEntries((data.data?.widgets ?? []).map((r) => [r.widget_id, r])) as Record<string, WidgetResult>, [data.data]);
  const labelOf = (f: string) => fields.get(f)?.label ?? f;

  const set = setView;
  const drillOf = (_w: Widget) => (field: string, value: string) => set((v) => ({ ...v, filters: addDrill(v.filters, { field, op: "eq", value }) }));
  const timeDrillOf = (w: Widget) => {
    const tf = timeFieldOf(w); const g = plan.gran[w.id];
    if (w.type !== "line" || !tf || !g) return undefined;
    return (iso: string) => set((v) => ({ ...v, filters: addDrill(v.filters, { field: tf, op: "between", value: timeRange(iso, g), time: true }) }));
  };
  const crumbs = drillCrumbs(view.filters);
  const dirty = view.filters.length > 0 || view.period !== null;
  const focusW = widgets.find((w) => w.id === view.focus);
  const recW = widgets.find((w) => w.id === recordsFor);

  if (dash.isLoading) return <Spinner />;
  if (dash.error) return <ErrorBox error={dash.error} />;
  const d = dash.data!;
  const activePeriod: PeriodSel = period ?? { mode: "relative", preset: d.default_period };
  const asOf = data.data?.widgets.map((x) => x.data_as_of).filter(Boolean).sort().pop();
  const cells: Cell[] = [...widgets].sort((a, b) => a.y - b.y || a.x - b.x).map((w) => ({ w, r: results[w.id], level: plan.level[w.id] ?? 0, path: pathOf(w), ov: plan.overrides[w.id] }));
  const crumbText = (f: AFilter) => `${labelOf(f.field)}: ${describeValue(f, fmtVal)}`;
  const filterable = [...fields.values()];

  return (
    <div className="an-root space-y-5">
      <div className="an-progress" data-active={data.isFetching || undefined} aria-hidden="true" />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Link to={`/dashboards/${d.id}`} className="text-sm text-ink-mute hover:underline">← {d.name}</Link>
          <h1 className="mt-1 text-3xl font-extrabold tracking-tight">Análise</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SearchBox id={d.id} onValue={(h) => set((v) => ({ ...v, filters: [...v.filters, { field: h.field, op: "in" as const, value: [h.value], src: "manual" as const }].slice(0, 20) }))}
            onField={(h) => { setPresetField(h.field); setAdding(true); }} />
          <ViewsMenu id={d.id} current={view} onApply={(v) => set(v)} />
        </div>
      </header>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <FilterBar id={d.id} filters={view.filters} fields={fields} adding={adding} presetField={presetField}
          onAddingChange={(v) => { setAdding(v); if (!v) setPresetField(undefined); }} onChange={(filters) => set((v) => ({ ...v, filters }))} />
        <PeriodControl value={activePeriod} onChange={(p) => set((v) => ({ ...v, period: p }))} />
      </div>

      <nav aria-label="Caminho do drill" className="an-crumbs">
        <button type="button" className={cx("an-crumb", crumbs.length === 0 && "is-cur")} aria-current={crumbs.length === 0 ? "page" : undefined}
          onClick={() => set((v) => ({ ...v, filters: truncateDrill(v.filters, 0) }))}>Visão geral</button>
        {crumbs.map((c, i) => (
          <span key={`${c.field}${JSON.stringify(c.value)}`} className="contents">
            <IconChevronRight className="an-sep" />
            <button type="button" className={cx("an-crumb", i === crumbs.length - 1 && "is-cur")} aria-current={i === crumbs.length - 1 ? "page" : undefined}
              onClick={() => set((v) => ({ ...v, filters: truncateDrill(v.filters, i + 1) }))}>{crumbText(c)}</button>
          </span>
        ))}
        <span className="ml-auto flex items-center gap-2">
          {crumbs.length > 0 && <Button variant="ghost" size="sm" onClick={() => set((v) => ({ ...v, filters: truncateDrill(v.filters, crumbs.length - 1) }))}><IconUndo />Voltar um nível</Button>}
          {dirty && <Button variant="ghost" size="sm" onClick={() => set(EMPTY_VIEW)}>Limpar tudo</Button>}
        </span>
      </nav>

      <p className={cx("text-xs text-ink-mute", data.isFetching && "animate-pulse")}>
        {data.error ? <Badge tone="danger">Falha ao atualizar — exibindo último dado</Badge> : <>Dados de {fmtDateTime(asOf)} · clique em barras, fatias, linhas e pontos para aprofundar · passe o mouse sobre um gráfico para expandir ou ver os registros</>}
        {fieldsQ.isError && <span className="ml-2 text-warn">Sem acesso à lista de campos: filtros avançados indisponíveis.</span>}
      </p>

      {widgets.length === 0 ? <Empty>Esta dashboard ainda não tem widgets.</Empty> : desktop ? (
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(12, minmax(0, 1fr))", gridAutoRows: "84px" }}>
          {cells.map((c, i) => (
            <div key={c.w.id} style={{ gridColumn: `${c.w.x + 1} / span ${c.w.w}`, gridRow: `${c.w.y + 1} / span ${c.w.h}` }}>
              <AnalysisCell cell={c} i={i} labelOf={labelOf} drilled={c.level > 0} onDrill={drillOf} onTimeDrill={timeDrillOf}
                onExpand={(w, rect) => { setExpandFrom(rect); set((v) => ({ ...v, focus: w.id })); }} onRecords={(w) => setRecordsFor(w.id)} />
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {cells.map((c, i) => (
            <div key={c.w.id} style={{ height: Math.max(180, c.w.h * 70) }}>
              <AnalysisCell cell={c} i={i} labelOf={labelOf} drilled={c.level > 0} onDrill={drillOf} onTimeDrill={timeDrillOf}
                onExpand={(w) => { setExpandFrom(null); set((v) => ({ ...v, focus: w.id })); }} onRecords={(w) => setRecordsFor(w.id)} />
            </div>
          ))}
        </div>
      )}

      {focusW && id && (
        <ExpandedWidget id={id} widget={focusW} initial={plan.overrides[focusW.id]} from={expandFrom} period={period} filters={apiFilters} fields={filterable}
          onClose={() => set((v) => ({ ...v, focus: null }), false)}
          onDrill={drillOf(focusW)} onTimeDrill={timeDrillOf(focusW)} onRecords={() => setRecordsFor(focusW.id)} />
      )}
      {recW && id && <RecordsDrawer id={id} widget={recW} period={period} filters={apiFilters} fields={filterable} onClose={() => setRecordsFor(null)} />}
    </div>
  );
}
