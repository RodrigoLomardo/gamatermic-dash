import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { S, get, post } from "@/shared/api/http";
import { fmtDateTime } from "@/shared/lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Select, Spinner, useToasts, cx } from "@/shared/ui/ui";
import { WidgetCard } from "../widgets/WidgetCard";
import type { Widget } from "../widgets/types";
import { useMedia } from "@/shared/hooks/useMedia";
import { PRESETS, Filter, PeriodSel, useDashboard, useDashboardData } from "./useDashboardData";
import { SharePanel } from "../admin/SharePanel";
import { PublishControl } from "./PublishControl";

export function DashboardsListPage() {
  const { can } = useAuth(); const nav = useNavigate(); const toast = useToasts((s) => s.push);
  const q = useQuery({ queryKey: ["dashboards"], queryFn: () => get<S["DashboardSummary"][]>("/dashboards") });
  const dup = async (id: string) => { try { const d = await post<S["DashboardOut"]>(`/dashboards/${id}/duplicate`); toast("Dashboard duplicada."); nav(`/dashboards/${d.id}/editar`); } catch (e) { toast((e as Error).message, "danger"); } };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">Dashboards</h1>
        {can("dashboard:create") && (
          <div className="flex gap-2">
            {can("dataset:query") && <Link to="/dashboards/nova/ia"><Button variant="secondary">Criar com IA</Button></Link>}
            <Link to="/dashboards/nova"><Button>Nova dashboard</Button></Link>
          </div>
        )}
      </div>
      {q.isLoading && <Spinner />}
      {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.length === 0 && <Empty>Nenhuma dashboard disponível para o seu perfil. Peça acesso a um administrador.</Empty>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {q.data?.map((d) => (
          <Card key={d.id} className="transition hover:shadow-lg">
            <Link to={`/dashboards/${d.id}`} className="block">
              <h2 className="text-lg font-semibold text-brand">{d.name}</h2>
              <p className="mt-1 line-clamp-2 min-h-[2.5rem] text-sm text-ink-soft">{d.description}</p>
            </Link>
            <div className="mt-3 flex items-center justify-between text-xs text-ink-mute">
              <span>{d.widget_count} widgets · atualizada {fmtDateTime(d.updated_at)}</span>
              {can("dashboard:create") && <button className="font-semibold text-accent-dark hover:underline" onClick={() => dup(d.id)}>Duplicar</button>}
            </div>
            <div className="mt-3 border-t border-line pt-3"><PublishControl id={d.id} name={d.name} status={d.status} canEdit={can("dashboard:edit")} compact /></div>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function WidgetGrid({ widgets, results, tv = false, onDrill }: { widgets: Widget[]; results: Record<string, any>; tv?: boolean; onDrill?: (f: string, v: string) => void }) {
  const sorted = useMemo(() => [...widgets].sort((a, b) => a.y - b.y || a.x - b.x), [widgets]);
  const desktop = useMedia("(min-width: 768px)");
  // um unico layout e renderizado por vez (sem widgets duplicados no DOM)
  if (desktop) {
    return (
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(12, minmax(0, 1fr))", gridAutoRows: "84px" }}>
        {sorted.map((w) => (
          <div key={w.id} style={{ gridColumn: `${w.x + 1} / span ${w.w}`, gridRow: `${w.y + 1} / span ${w.h}` }}>
            <WidgetCard widget={w} result={results[w.id]} tv={tv} onDrill={onDrill} />
          </div>
        ))}
      </div>
    );
  }
  // mobile: empilha por ordem (y, x)
  return (
    <div className="space-y-3">
      {sorted.map((w) => (
        <div key={w.id} style={{ height: Math.max(150, w.h * 70) }}><WidgetCard widget={w} result={results[w.id]} onDrill={onDrill} /></div>
      ))}
    </div>
  );
}

export function DashboardViewPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const dash = useDashboard(id);
  const [preset, setPreset] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filter[]>([]);
  const [share, setShare] = useState(false);
  const period: PeriodSel | null = preset ? { mode: "relative", preset } : null;
  const data = useDashboardData(id, period, filters, dash.data?.refresh_interval_seconds ?? 60);
  const results = useMemo(() => Object.fromEntries((data.data?.widgets ?? []).map((r) => [r.widget_id, r])), [data.data]);
  const drill = (field: string, value: string) => setFilters((f) => (f.some((x) => x.field === field && x.value === value) ? f : [...f.filter((x) => x.field !== field), { field, op: "eq", value }]));
  if (dash.isLoading) return <Spinner />;
  if (dash.error) return <ErrorBox error={dash.error} />;
  const d = dash.data!;
  const asOf = data.data?.widgets.map((w) => w.data_as_of).filter(Boolean).sort().pop();
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/dashboards" className="text-sm text-ink-mute hover:underline">← Dashboards</Link>
          <h1 className="text-2xl font-bold">{d.name}</h1>
          {d.description && <p className="text-sm text-ink-soft">{d.description}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm font-medium text-ink-soft" htmlFor="period">Período</label>
          <Select id="period" className="w-48" value={preset ?? d.default_period} onChange={(e) => setPreset(e.target.value)}>
            {PRESETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </Select>
          <Link to={`/tv/painel/${d.id}`}><Button variant="secondary">Abrir visualização (TV)</Button></Link>
          {can("grant:manage") && <Button variant="secondary" onClick={() => setShare(true)}>Compartilhar</Button>}
          {d.can_edit && <Link to={`/dashboards/${d.id}/editar`}><Button>Editar</Button></Link>}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-panel px-4 py-2">
        <PublishControl id={d.id} name={d.name} status={d.status} canEdit={d.can_edit} />
        {d.status !== "published" && <p role="status" className="text-sm text-warn">Fora do ar: só quem edita vê este painel. Lance para liberar aos gestores e às TVs.</p>}
      </div>
      {filters.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Filtros ativos">
          <span className="text-sm text-ink-mute">Filtros:</span>
          {filters.map((f) => (
            <button key={f.field} className="rounded-full bg-accent-soft px-3 py-1 text-sm font-semibold text-accent-dark" aria-label={`Remover filtro ${f.field} ${f.value}`}
              onClick={() => setFilters(filters.filter((x) => x !== f))}>{f.field}: {f.value} ✕</button>
          ))}
          <button className="text-sm font-semibold text-ink-soft underline" onClick={() => setFilters([])}>Limpar</button>
        </div>
      )}
      <p className={cx("text-xs text-ink-mute", data.isFetching && "animate-pulse")}>
        {data.error ? <Badge tone="danger">Falha ao atualizar — exibindo último dado</Badge> : <>Dados de {fmtDateTime(asOf)} · atualiza a cada {d.refresh_interval_seconds}s · clique em barras, fatias e linhas para filtrar</>}
      </p>
      {d.widgets.length === 0 ? <Empty>Esta dashboard ainda não tem widgets.</Empty> : <WidgetGrid widgets={d.widgets} results={results} onDrill={drill} />}
      {share && <SharePanel resourceType="dashboard" resourceId={d.id} onClose={() => setShare(false)} />}
    </div>
  );
}
