import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { S, get, post } from "@/shared/api/http";
import { Button, Field, Input, Select, Spinner, cx } from "@/shared/ui/ui";
import { PRESETS } from "../dashboards/useDashboardData";
import { WidgetCard } from "../widgets/WidgetCard";
import type { Widget, WidgetResult } from "../widgets/types";

export type Draft = {
  type: string; title: string; dataset_id: string; query_config: Record<string, any>; viz_config: Record<string, any>; follows_global_period: boolean;
};
type Ds = S["DatasetOut"];
const AGGS = [["sum", "Soma"], ["avg", "Média"], ["count", "Contagem"], ["count_distinct", "Contagem distinta"], ["min", "Mínimo"], ["max", "Máximo"]];
const OPS = [["eq", "="], ["neq", "≠"], ["in", "em (a,b,c)"], ["gt", ">"], ["gte", "≥"], ["lt", "<"], ["lte", "≤"], ["contains", "contém"]];
const TYPES = [["kpi", "Indicador (KPI)"], ["gauge", "Medidor (meta)"], ["line", "Linha / evolução"], ["bar", "Barras"], ["pie", "Pizza"], ["table", "Tabela"]];
const FORMATS = [["currency", "Moeda (R$)"], ["number", "Número"], ["integer", "Inteiro"], ["percent", "Percentual"]];

export function blankDraft(dataset: Ds, type = "kpi"): Draft {
  const measure = dataset.fields.find((f) => f.role === "measure");
  const dim = dataset.fields.find((f) => f.role === "dimension");
  const m = measure ? { agg: "sum", field: measure.name, alias: "valor" } : { agg: "count", alias: "valor" };
  const qc: Record<string, any> = { measures: [m] };
  if (type === "bar" || type === "pie") qc.dimensions = dim ? [dim.name] : [];
  if (type === "line") qc.time = { granularity: "month" };
  if (type === "table") { qc.columns = dataset.fields.slice(0, 5).map((f) => f.name); delete qc.measures; }
  return { type, title: "Novo widget", dataset_id: dataset.id, query_config: qc, viz_config: { format: measure ? "currency" : "integer" }, follows_global_period: true };
}

export function normalizeForType(d: Draft, ds: Ds): Draft {
  const fresh = blankDraft(ds, d.type);
  return { ...d, query_config: { ...fresh.query_config, filters: d.query_config.filters, period: d.query_config.period }, viz_config: { ...fresh.viz_config, format: d.viz_config.format } };
}

export function WidgetConfigForm({ draft, onChange, onApply, applyLabel }: { draft: Draft; onChange: (d: Draft) => void; onApply: () => void; applyLabel: string }) {
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: () => get<Ds[]>("/datasets") });
  const ds = datasets.data?.find((d) => d.id === draft.dataset_id);
  const [preview, setPreview] = useState<WidgetResult | null>(null);
  const [perr, setPerr] = useState<string | null>(null);
  const qc = draft.query_config; const vz = draft.viz_config;
  const set = (patch: Partial<Draft>) => onChange({ ...draft, ...patch });
  const setQ = (patch: Record<string, any>) => set({ query_config: { ...qc, ...patch } });
  const setV = (patch: Record<string, any>) => set({ viz_config: { ...vz, ...patch } });
  const m0 = qc.measures?.[0];
  const numeric = ds?.fields.filter((f) => f.data_type === "integer" || f.data_type === "decimal") ?? [];

  useEffect(() => { setPreview(null); setPerr(null); }, [draft.type, draft.dataset_id]);

  if (datasets.isLoading || !ds) return <Spinner />;
  const runPreview = async () => {
    setPerr(null);
    try {
      const r = await post<any>("/query/preview", { dataset_id: draft.dataset_id, type: draft.type, query_config: { ...qc, period: qc.period ?? (ds.time_field ? { mode: "relative", preset: "this_month" } : undefined) } });
      setPreview({ widget_id: "preview", type: draft.type, data: r.data, previous: r.previous, dataset_version: r.dataset_version, data_as_of: r.data_as_of, generated_at: null, period: r.period, error: null });
    } catch (e) { setPreview(null); setPerr((e as Error).message); }
  };
  const fieldOpts = ds.fields.map((f) => <option key={f.name} value={f.name}>{f.label}</option>);
  const w: Widget = { id: "preview", ...draft, x: 0, y: 0, w: 4, h: 3 } as unknown as Widget;
  const setFilter = (i: number, patch: Record<string, any>) => setQ({ filters: (qc.filters ?? []).map((f: any, j: number) => (i === j ? { ...f, ...patch } : f)) });
  const parseVal = (op: string, s: string) => (op === "in" ? s.split(",").map((x) => x.trim()).filter(Boolean) : s === "true" ? true : s === "false" ? false : s);

  return (
    <div className="space-y-4">
      <Field label="Título">{(id) => <Input id={id} value={draft.title} onChange={(e) => set({ title: e.target.value })} />}</Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Tipo">{(id) => <Select id={id} value={draft.type} onChange={(e) => onChange(normalizeForType({ ...draft, type: e.target.value }, ds))}>{TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field>
        <Field label="Dataset">{(id) => <Select id={id} value={draft.dataset_id} onChange={(e) => { const n = datasets.data!.find((x) => x.id === e.target.value)!; onChange({ ...blankDraft(n, draft.type), title: draft.title }); }}>{datasets.data!.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select>}</Field>
      </div>

      {draft.type === "table" && !qc.measures?.length ? (
        <Field label="Colunas (modo linhas)" hint="Mantenha Ctrl/Cmd para selecionar várias.">
          {(id) => <select id={id} multiple className="h-32 w-full rounded-lg border border-line bg-panel p-2 text-sm" value={qc.columns ?? []} onChange={(e) => setQ({ columns: [...e.target.selectedOptions].map((o) => o.value) })}>{fieldOpts}</select>}
        </Field>
      ) : (
        <>
          {["bar", "pie", "table"].includes(draft.type) && (
            <Field label="Agrupar por">{(id) => <Select id={id} value={qc.dimensions?.[0] ?? ""} onChange={(e) => setQ({ dimensions: e.target.value ? [e.target.value] : [] })}><option value="">—</option>{fieldOpts}</Select>}</Field>
          )}
          {draft.type === "line" && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Granularidade">{(id) => <Select id={id} value={qc.time?.granularity ?? "month"} onChange={(e) => setQ({ time: { ...qc.time, granularity: e.target.value } })}>{["day", "week", "month", "quarter", "year"].map((g) => <option key={g} value={g}>{{ day: "Dia", week: "Semana", month: "Mês", quarter: "Trimestre", year: "Ano" }[g]}</option>)}</Select>}</Field>
              <Field label="Séries por (opcional)">{(id) => <Select id={id} value={qc.dimensions?.[0] ?? ""} onChange={(e) => setQ({ dimensions: e.target.value ? [e.target.value] : [] })}><option value="">—</option>{fieldOpts}</Select>}</Field>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Cálculo">{(id) => <Select id={id} value={m0?.agg ?? "sum"} onChange={(e) => setQ({ measures: [{ ...m0, agg: e.target.value, alias: m0?.alias ?? "valor" }] })}>{AGGS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field>
            <Field label="Campo">{(id) => <Select id={id} value={m0?.field ?? ""} disabled={m0?.agg === "count"} onChange={(e) => setQ({ measures: [{ ...m0, field: e.target.value || undefined }] })}><option value="">—</option>{(["sum", "avg"].includes(m0?.agg) ? numeric : ds.fields).map((f) => <option key={f.name} value={f.name}>{f.label}</option>)}</Select>}</Field>
          </div>
          {["bar", "pie"].includes(draft.type) && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Ordenar">{(id) => <Select id={id} value={qc.sort?.[0]?.dir ?? "desc"} onChange={(e) => setQ({ sort: [{ by: m0?.alias ?? "valor", dir: e.target.value }] })}><option value="desc">Maior primeiro</option><option value="asc">Menor primeiro</option></Select>}</Field>
              <Field label="Limite (Top N)">{(id) => <Input id={id} type="number" min={1} max={50} value={qc.limit ?? 10} onChange={(e) => setQ({ limit: Number(e.target.value) })} />}</Field>
            </div>
          )}
        </>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Field label="Formato">{(id) => <Select id={id} value={vz.format ?? "number"} onChange={(e) => setV({ format: e.target.value })}>{FORMATS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field>
        {draft.type === "gauge" && <Field label="Meta">{(id) => <Input id={id} type="number" value={vz.target ?? ""} onChange={(e) => setV({ target: e.target.value === "" ? undefined : Number(e.target.value) })} />}</Field>}
        {(draft.type === "kpi") && <label className="mt-6 flex items-center gap-2 text-sm"><input type="checkbox" checked={!!qc.compare_previous_period} onChange={(e) => setQ({ compare_previous_period: e.target.checked })} /> Comparar com período anterior</label>}
        {draft.type === "bar" && <label className="mt-6 flex items-center gap-2 text-sm"><input type="checkbox" checked={!!vz.horizontal} onChange={(e) => setV({ horizontal: e.target.checked })} /> Barras horizontais</label>}
      </div>

      <fieldset className="space-y-2 rounded-lg border border-line p-3">
        <legend className="px-1 text-sm font-semibold text-ink-soft">Período</legend>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.follows_global_period} onChange={(e) => set({ follows_global_period: e.target.checked })} /> Seguir o período da dashboard</label>
        <Select aria-label="Período próprio" value={qc.period?.preset ?? ""} onChange={(e) => setQ({ period: e.target.value ? { mode: "relative", preset: e.target.value } : undefined })}>
          <option value="">Padrão da dashboard</option>{PRESETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </Select>
        <p className="text-xs text-ink-mute">Com “seguir” desligado, o widget usa sempre o período próprio.</p>
      </fieldset>

      <fieldset className="space-y-2 rounded-lg border border-line p-3">
        <legend className="px-1 text-sm font-semibold text-ink-soft">Filtros</legend>
        {(qc.filters ?? []).map((f: any, i: number) => (
          <div key={i} className="grid grid-cols-[1fr_auto_1fr_auto] items-center gap-2">
            <Select aria-label="Campo do filtro" value={f.field} onChange={(e) => setFilter(i, { field: e.target.value })}>{fieldOpts}</Select>
            <Select aria-label="Operador" value={f.op} onChange={(e) => setFilter(i, { op: e.target.value })}>{OPS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
            <Input aria-label="Valor" value={Array.isArray(f.value) ? f.value.join(",") : String(f.value ?? "")} onChange={(e) => setFilter(i, { value: parseVal(f.op, e.target.value) })} />
            <button aria-label="Remover filtro" className="text-danger" onClick={() => setQ({ filters: qc.filters.filter((_: any, j: number) => j !== i) })}>✕</button>
          </div>
        ))}
        <Button variant="secondary" size="sm" onClick={() => setQ({ filters: [...(qc.filters ?? []), { field: ds.fields[0].name, op: "eq", value: "" }] })}>+ Filtro</Button>
      </fieldset>

      <div className="flex gap-2">
        <Button variant="secondary" onClick={runPreview}>Pré-visualizar</Button>
        <Button onClick={onApply}>{applyLabel}</Button>
      </div>
      {perr && <p role="alert" className="text-sm text-danger">{perr}</p>}
      {preview && <div className={cx("h-56")}><WidgetCard widget={w} result={preview} /></div>}
    </div>
  );
}
