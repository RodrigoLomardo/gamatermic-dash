import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import GridLayout, { Layout, WidthProvider } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { ApiError, S, del, get, patch, post, put } from "@/shared/api/http";
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, Select, Spinner, useToasts } from "@/shared/ui/ui";
import { PRESETS, useDashboardData } from "../dashboards/useDashboardData";
import { AiWidgetsPanel } from "../ai-dashboards/AiWidgetsPanel";
import { WidgetCard } from "../widgets/WidgetCard";
import { COMPACT_MIN, DEFAULT_SIZE } from "../widgets/sizes";
import type { Widget } from "../widgets/types";
import { Draft, WidgetConfigForm, blankDraft } from "./WidgetConfig";

const RGL = WidthProvider(GridLayout);
type Dash = S["DashboardOut"]; type Ds = S["DatasetOut"];
const fail = (e: unknown) => (e instanceof ApiError ? e.message : (e as Error).message);

export function NewDashboardPage() {
  const nav = useNavigate(); const toast = useToasts((s) => s.push);
  const sectors = useQuery({ queryKey: ["sectors"], queryFn: () => get<S["SectorOut"][]>("/sectors") });
  const [name, setName] = useState(""); const [sector, setSector] = useState("");
  const slug = name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const create = async () => {
    try { const d = await post<Dash>("/dashboards", { slug: slug || "nova", name, sector_id: sector || null }); nav(`/dashboards/${d.id}/editar`); }
    catch (e) { toast(fail(e), "danger"); }
  };
  return (
    <div className="mx-auto max-w-md"><Card title="Nova dashboard"><div className="space-y-4">
      <Field label="Nome">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
      <Field label="Setor">{(id) => <Select id={id} value={sector} onChange={(e) => setSector(e.target.value)}><option value="">—</option>{sectors.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>}</Field>
      <Button disabled={name.length < 2} onClick={create}>Criar e editar</Button>
      <p className="border-t border-line pt-3 text-sm text-ink-soft">Prefere partir de sugestões? <Link to="/dashboards/nova/ia" className="font-semibold text-accent-dark underline">Criar com IA</Link></p>
    </div></Card></div>
  );
}

export function EditorPage() {
  const { id } = useParams(); const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const dash = useQuery({ queryKey: ["editor", id], queryFn: () => get<Dash>(`/dashboards/${id}`), staleTime: 0 });
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: () => get<Ds[]>("/datasets") });
  const [widgets, setWidgets] = useState<Widget[]>([]);
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState<string | "new" | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [conflict, setConflict] = useState(false);
  // tamanho ao vivo enquanto o usuario redimensiona (troca visao completa/compacta antes de soltar)
  const [live, setLive] = useState<Record<string, { w: number; h: number }>>({});
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const versionRef = useRef(0);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const [meta, setMeta] = useState<{ name: string; period: string; refresh: number } | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const closeAi = useCallback(() => setAiOpen(false), []); // estavel: o Modal refoca a cada troca de onClose
  const canAi = useAuth((s) => s.can)("dataset:query");
  const data = useDashboardData(id, null, [], 60);
  const results = useMemo(() => Object.fromEntries((data.data?.widgets ?? []).map((r) => [r.widget_id, r])), [data.data]);

  useEffect(() => { if (dash.data) { setWidgets(dash.data.widgets); setVersion(dash.data.version); setMeta({ name: dash.data.name, period: dash.data.default_period, refresh: dash.data.refresh_interval_seconds }); versionRef.current = dash.data.version; } }, [dash.data]);
  const hdr = () => ({ headers: { "If-Match": `"${versionRef.current}"` } });
  const apply = (d: Dash) => { setWidgets(d.widgets); setVersion(d.version); versionRef.current = d.version; setLive({}); qc.invalidateQueries({ queryKey: ["dashboard-data", id] }); };
  const guarded = async (fn: () => Promise<void>) => {
    try { await fn(); } catch (e) { if (e instanceof ApiError && e.status === 409) setConflict(true); else toast(fail(e), "danger"); }
  };

  // salva sozinho ao soltar (arrastar ou redimensionar); saves em fila para encadear a versao (If-Match)
  const autoSave = (l: Layout[]) => {
    const key = (xs: { i?: string; id?: string; x: number; y: number; w: number; h: number }[]) => xs.map((x) => `${x.i ?? x.id}:${x.x},${x.y},${x.w},${x.h}`).sort().join("|");
    if (key(l) === key(widgets)) { setLive({}); return; }
    const items = l.map((x) => ({ id: x.i, x: x.x, y: x.y, w: x.w, h: x.h }));
    setSaveState("saving");
    saveQueue.current = saveQueue.current.then(async () => {
      try { apply(await put<Dash>(`/dashboards/${id}/layout`, { items }, hdr())); setSaveState("saved"); }
      catch (e) { setSaveState("error"); if (e instanceof ApiError && e.status === 409) setConflict(true); else toast(fail(e), "danger"); }
    });
  };
  const saveMeta = () => guarded(async () => { apply(await patch<Dash>(`/dashboards/${id}`, { name: meta!.name, default_period: meta!.period, refresh_interval_seconds: meta!.refresh }, hdr())); toast("Configurações salvas."); });
  const saveWidget = () => guarded(async () => {
    if (!draft) return;
    if (selected === "new") {
      const y = Math.max(0, ...widgets.map((w) => w.y + w.h));
      apply(await post<Dash>(`/dashboards/${id}/widgets`, { ...draft, x: 0, y, ...(DEFAULT_SIZE[draft.type] ?? { w: 6, h: 4 }) }, hdr()));
    } else apply(await patch<Dash>(`/dashboards/${id}/widgets/${selected}`, draft, hdr()));
    setSelected(null); setDraft(null); toast("Widget salvo.");
  });
  const removeWidget = (wid: string) => guarded(async () => { if (confirm("Remover este widget?")) { apply(await del<Dash>(`/dashboards/${id}/widgets/${wid}`, hdr())); setSelected(null); } });

  if (dash.isLoading || datasets.isLoading || !meta) return <Spinner />;
  if (dash.error) return <ErrorBox error={dash.error} />;
  const layout: Layout[] = widgets.map((w) => ({ i: w.id, x: w.x, y: w.y, w: w.w, h: w.h, minW: COMPACT_MIN.w, minH: COMPACT_MIN.h }));
  const startNew = () => { const ds = datasets.data?.[0]; if (ds) { setDraft(blankDraft(ds)); setSelected("new"); } };
  const edit = (w: Widget) => { setDraft({ type: w.type, title: w.title, dataset_id: w.dataset_id!, query_config: w.query_config as any, viz_config: w.viz_config as any, follows_global_period: w.follows_global_period }); setSelected(w.id); };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><Link to={`/dashboards/${id}`} className="text-sm text-ink-mute hover:underline">← Voltar à visualização</Link><h1 className="text-2xl font-bold">Editor — {dash.data!.name}</h1></div>
        <div className="flex items-center gap-2">
          {/* status a esquerda dos botoes: reserva largura sem deixar vao entre os botoes e a borda direita */}
          <span role="status" aria-live="polite" className="min-w-[9rem] text-right text-xs text-ink-mute">
            {saveState === "saving" ? "Salvando layout…" : saveState === "saved" ? "Layout salvo" : saveState === "error" ? "Layout não salvo" : ""}
          </span>
          <Badge tone="neutral">versão {version}</Badge>
          {/* nova aba: o editor continua aberto; vale tambem para painel fora do ar (quem edita pode pre-visualizar) */}
          <a href={`/tv/preview/${id}`} target="_blank" rel="noopener noreferrer" aria-label="Prévia na TV (abre em nova aba)"><Button variant="secondary" tabIndex={-1}>Prévia na TV ↗</Button></a>
          {canAi && <Button variant="secondary" onClick={() => setAiOpen(true)}>Gráficos com IA</Button>}
          <Button variant="secondary" onClick={startNew}>+ Widget</Button>
        </div>
      </div>
      <Card title="Configurações" className="print:hidden">
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="Nome">{(i) => <Input id={i} value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value })} />}</Field>
          <Field label="Período padrão">{(i) => <Select id={i} value={meta.period} onChange={(e) => setMeta({ ...meta, period: e.target.value })}>{PRESETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field>
          <Field label="Atualização (s)">{(i) => <Input id={i} type="number" min={15} value={meta.refresh} onChange={(e) => setMeta({ ...meta, refresh: Number(e.target.value) })} />}</Field>
          <div className="flex items-end"><Button variant="secondary" onClick={saveMeta}>Salvar configurações</Button></div>
        </div>
      </Card>
      <p className="text-sm text-ink-mute">
        Arraste para mover e puxe o canto inferior direito para redimensionar. Abaixo do tamanho completo, o gráfico troca para uma visão compacta
        (ranking, valor com tendência, lista). Tudo é salvo ao soltar e aparece igual no desktop e na TV.
      </p>
      <RGL className="layout" layout={layout} cols={12} rowHeight={84} margin={[12, 12]} draggableCancel=".no-drag"
        onResize={(_l, _old, item) => setLive((s) => (s[item.i]?.w === item.w && s[item.i]?.h === item.h ? s : { ...s, [item.i]: { w: item.w, h: item.h } }))}
        onResizeStop={(l) => autoSave(l)} onDragStop={(l) => autoSave(l)}>
        {widgets.map((w) => (
          <div key={w.id} className="relative">
            <WidgetCard widget={w} result={results[w.id]} size={live[w.id] ?? w} showViewHint />
            <div className="no-drag absolute right-2 top-2 flex gap-1">
              <button className="rounded bg-panel/90 px-2 py-0.5 text-xs font-semibold shadow hover:bg-brand-soft" onClick={() => edit(w)}>Editar</button>
              <button aria-label={`Remover ${w.title}`} className="rounded bg-panel/90 px-2 py-0.5 text-xs font-semibold text-danger shadow hover:bg-brand-soft" onClick={() => removeWidget(w.id)}>✕</button>
            </div>
          </div>
        ))}
      </RGL>
      <Modal open={!!draft} wide title={selected === "new" ? "Novo widget" : "Editar widget"} onClose={() => { setSelected(null); setDraft(null); }}>
        {draft && <WidgetConfigForm draft={draft} onChange={setDraft} onApply={saveWidget} applyLabel="Salvar widget" />}
      </Modal>
      <Modal open={aiOpen} wide title="Gráficos com IA" onClose={closeAi}>
        <AiWidgetsPanel dashboardId={id!} widgets={widgets} version={version} defaultPeriod={meta.period} datasets={datasets.data ?? []}
          onAdded={(d, n, m) => { apply(d); setAiOpen(false); toast([n && `${n} gráfico(s) adicionado(s)`, m && `${m} ajustado(s)`].filter(Boolean).join(" e ") + " no painel."); }}
          onConflict={() => { setAiOpen(false); setConflict(true); }} />
      </Modal>
      <Modal open={conflict} title="Conflito de edição" onClose={() => setConflict(false)}>
        <p className="mb-4 text-sm">Esta dashboard foi alterada por outra pessoa enquanto você editava. Recarregue para ver a versão atual (suas mudanças não salvas serão descartadas).</p>
        <Button onClick={() => { setConflict(false); dash.refetch(); }}>Recarregar versão atual</Button>
      </Modal>
    </div>
  );
}
