import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { ApiError, S, api, get, post } from "@/shared/api/http";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, Select, Spinner, Textarea, useToasts, cx } from "@/shared/ui/ui";
import { PRESETS } from "../dashboards/useDashboardData";
import { WidgetCard } from "../widgets/WidgetCard";
import type { Widget, WidgetResult } from "../widgets/types";
import { pack, slugify } from "./layout";

type Ds = S["DatasetOut"]; type Out = S["ProposalsOut"]; type Proposal = S["Proposal"]; type Dash = S["DashboardOut"]; type Run = S["RunOut"];
const fail = (e: unknown) => (e instanceof ApiError ? e.message : (e as Error).message);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const EXAMPLES = ["Faturamento por mês nos últimos 12 meses e top 10 clientes", "Quantos pedidos por segmento e ticket médio", "Pipeline em aberto por responsável"];

/** Anexo: infere o schema, cria o dataset (modo append) e carrega o arquivo pelo pipeline normal de ingestao. */
async function importFile(file: File, name: string, onStep: (s: string) => void): Promise<Ds> {
  onStep("Lendo colunas do arquivo…");
  const fd = new FormData(); fd.append("file", file);
  const inf = await api<S["InferOut"]>("POST", "/datasets/infer-schema", { form: fd });
  if (!inf.columns.length) throw new Error("Não encontrei colunas no arquivo.");
  const slug = (slugify(name).replace(/-/g, "_") || "dados").replace(/^[^a-z]+/, "") || "dados";
  const fields = inf.columns.map(({ sample: _s, ...f }) => f);
  onStep("Criando o dataset…");
  const ds = await post<Ds>("/datasets", {
    slug: `${slug.slice(0, 60)}_${Date.now().toString(36)}`, name, load_mode: "append",
    time_field: fields.find((f) => f.role === "time")?.name ?? null, parser_options: { sheet: inf.sheet ?? undefined }, fields,
    description: `Importado pelo assistente de IA a partir de ${file.name}.`,
  });
  onStep("Carregando os dados…");
  const up = new FormData(); up.append("file", file);
  let run = await api<Run>("POST", `/datasets/${ds.id}/uploads`, { form: up, query: { sheet: inf.sheet ?? undefined } });
  for (let i = 0; i < 120 && ["queued", "running"].includes(run.status); i++) { await sleep(1000); run = await get<Run>(`/ingestion/runs/${run.id}`); }
  if (!["succeeded", "succeeded_with_errors"].includes(run.status)) throw new Error(run.error_summary || "A carga do arquivo não foi concluída.");
  return ds;
}

function asWidget(p: Proposal): Widget {
  return { id: p.id, type: p.type, title: p.title, x: 0, y: 0, w: p.w, h: p.h, dataset_id: p.dataset_id, query_config: p.query_config,
    viz_config: p.viz_config, follows_global_period: p.follows_global_period } as Widget;
}

export function ProposalCard({ p, checked, onToggle }: { p: Proposal; checked: boolean; onToggle: () => void }) {
  return (
    <div className={cx("flex min-w-0 flex-col gap-2 rounded-xl border-2 p-2 transition", checked ? "border-accent" : "border-transparent")}>
      <div className="h-64"><WidgetCard widget={asWidget(p)} result={p.preview as unknown as WidgetResult} dim={!checked} /></div>
      <p className="px-1 text-xs text-ink-soft">{p.rationale}</p>
      <label className="flex cursor-pointer items-center gap-2 px-1 text-sm font-semibold">
        <input type="checkbox" checked={checked} onChange={onToggle} /> Usar “{p.title}”
      </label>
    </div>
  );
}

export function AiCreatePage() {
  const { can } = useAuth(); const nav = useNavigate(); const toast = useToasts((s) => s.push);
  const status = useQuery({ queryKey: ["ai-status"], queryFn: () => get<S["AiStatusOut"]>("/ai/status") });
  const datasets = useQuery({ queryKey: ["datasets"], queryFn: () => get<Ds[]>("/datasets") });
  const canImport = can("dataset:manage") && can("ingestion:upload");
  const [source, setSource] = useState<"existing" | "file">("existing");
  const [dsId, setDsId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [period, setPeriod] = useState("last_12_months");
  const [step, setStep] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [out, setOut] = useState<Out | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  const dsList = useMemo(() => datasets.data ?? [], [datasets.data]);
  const selectedDs = useMemo(() => dsList.find((d) => d.id === (out?.proposals[0]?.dataset_id ?? dsId)), [dsList, dsId, out]);
  const ready = prompt.trim().length >= 3 && (source === "existing" ? !!dsId : !!file && fileName.trim().length >= 2);

  const generate = async () => {
    setError(null); setOut(null);
    try {
      let target = dsId;
      if (source === "file" && file) {
        const ds = await importFile(file, fileName.trim(), setStep);
        target = ds.id; setDsId(ds.id); setSource("existing"); setFile(null); datasets.refetch();
      }
      setStep("A IA está montando as sugestões…");
      const r = await post<Out>("/ai/dashboard-proposals", { dataset_id: target, prompt: prompt.trim(), default_period: period });
      setOut(r); setPicked(new Set(r.proposals.map((p) => p.id)));
      if (!name) setName(prompt.trim().slice(0, 60));
    } catch (e) { setError(e); } finally { setStep(null); }
  };

  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const create = async () => {
    if (!out) return;
    setCreating(true);
    try {
      const chosen = pack(out.proposals.filter((p) => picked.has(p.id)));
      const ds = dsList.find((d) => d.id === out.proposals[0]?.dataset_id) ?? dsList.find((d) => d.id === dsId);
      const d = await post<Dash>("/dashboards", {
        slug: `${slugify(name) || "painel-ia"}-${Date.now().toString(36)}`.slice(0, 79), name: name.trim(), sector_id: ds?.sector_id ?? null,
        default_period: period, description: `Criado com o assistente de IA: “${prompt.trim().slice(0, 200)}”`,
      });
      for (const p of chosen) {
        await post<Dash>(`/dashboards/${d.id}/widgets`, { type: p.type, title: p.title, dataset_id: p.dataset_id, query_config: p.query_config,
          viz_config: p.viz_config, follows_global_period: p.follows_global_period, x: p.x, y: p.y, w: p.w, h: p.h });
      }
      toast(chosen.length ? `Painel criado com ${chosen.length} gráfico(s). Ele está fora do ar até você lançar.` : "Painel em branco criado.");
      nav(`/dashboards/${d.id}/editar`);
    } catch (e) { toast(fail(e), "danger"); } finally { setCreating(false); }
  };

  if (status.isLoading || datasets.isLoading) return <Spinner />;
  if (status.error) return <ErrorBox error={status.error} onRetry={() => status.refetch()} />;
  if (!status.data?.available) {
    return (
      <div className="mx-auto max-w-lg"><Card title="Criar com IA">
        <p className="text-sm text-ink-soft">O assistente de IA ainda não está ativo.</p>
        {can("settings:manage")
          ? <p className="mt-3 text-sm">Configure a chave da Groq em <Link className="font-semibold text-accent-dark underline" to="/configuracoes">Configurações</Link>.</p>
          : <p className="mt-3 text-sm">Peça a um administrador para ativá-lo em Configurações.</p>}
        <Link to="/dashboards/nova" className="mt-4 inline-block"><Button variant="secondary">Criar sem IA</Button></Link>
      </Card></div>
    );
  }

  const n = picked.size;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><Link to="/dashboards/nova" className="text-sm text-ink-mute hover:underline">← Criar sem IA</Link><h1 className="text-2xl font-bold">Criar dashboard com IA</h1></div>
        <Badge tone="accent">{status.data.model}</Badge>
      </div>

      <Card title="1. Dados">
        <div className="space-y-3">
          {canImport && (
            <div role="radiogroup" aria-label="Origem dos dados" className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2"><input type="radio" name="src" checked={source === "existing"} onChange={() => setSource("existing")} /> Dataset existente</label>
              <label className="flex items-center gap-2"><input type="radio" name="src" checked={source === "file"} onChange={() => setSource("file")} /> Anexar arquivo (CSV ou XLSX)</label>
            </div>
          )}
          {source === "existing" ? (
            dsList.length === 0 ? <Empty>Nenhum dataset disponível para o seu perfil.</Empty> : (
              <div className="max-w-md"><Field label="Dataset">{(id) => (
                <Select id={id} value={dsId} onChange={(e) => { setDsId(e.target.value); setOut(null); }}>
                  <option value="">Escolha…</option>{dsList.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.row_count} linhas)</option>)}
                </Select>)}</Field></div>
            )
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="Arquivo" hint="Vira um dataset novo, carregado pelo processo normal de cargas.">{(id) => (
                <input id={id} type="file" accept=".csv,.txt,.xlsx" className="text-sm" onChange={(e) => {
                  const f = e.target.files?.[0] ?? null; setFile(f); if (f && !fileName) setFileName(f.name.replace(/\.[^.]+$/, ""));
                }} />)}</Field>
              <Field label="Nome do dataset">{(id) => <Input id={id} value={fileName} onChange={(e) => setFileName(e.target.value)} />}</Field>
            </div>
          )}
        </div>
      </Card>

      <Card title="2. O que você quer ver?">
        <div className="space-y-3">
          <Field label="Pedido" hint="Ex.: faturamento por mês, ranking de clientes, comparação entre empresas. A IA vê só os nomes dos campos, não os dados.">
            {(id) => <Textarea id={id} rows={3} maxLength={1000} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={EXAMPLES[0]} />}
          </Field>
          <div className="flex flex-wrap gap-2">{EXAMPLES.map((x) => <button key={x} type="button" className="rounded-full border border-line px-3 py-1 text-xs hover:bg-brand-soft" onClick={() => setPrompt(x)}>{x}</button>)}</div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-56"><Field label="Período padrão do painel">{(id) => <Select id={id} value={period} onChange={(e) => setPeriod(e.target.value)}>{PRESETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field></div>
            <Button onClick={generate} disabled={!ready || !!step}>{out ? "Gerar de novo" : "Gerar sugestões"}</Button>
          </div>
          {step && <p role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-ink-soft"><span className="h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />{step}</p>}
          {!!error && <ErrorBox error={error} onRetry={ready ? generate : undefined} />}
        </div>
      </Card>

      {out && (
        <Card title="3. Escolha os gráficos" actions={out.proposals.length > 0 && (
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => setPicked(new Set(out.proposals.map((p) => p.id)))}>Todos</Button>
            <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Nenhum</Button>
          </div>)}>
          <div className="space-y-3">
            {out.explanation && <p className="text-sm text-ink-soft">{out.explanation}</p>}
            {out.discarded.length > 0 && (
              <details className="text-xs text-ink-mute"><summary>{out.discarded.length} sugestão(ões) descartada(s) por não passar na validação</summary>
                <ul className="ml-4 list-disc">{out.discarded.map((d, i) => <li key={i}>{d.title}: {d.reason}</li>)}</ul></details>
            )}
            {out.proposals.length === 0 ? <Empty>A IA não encontrou gráficos para este pedido. Reformule ou comece em branco.</Empty> : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {out.proposals.map((p) => <ProposalCard key={p.id} p={p} checked={picked.has(p.id)} onToggle={() => toggle(p.id)} />)}
              </div>
            )}
            <div className="flex flex-wrap items-end gap-3 border-t border-line pt-3">
              <div className="w-72"><Field label="Nome do painel">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field></div>
              <Button disabled={creating || name.trim().length < 2} onClick={create}>{n > 0 ? `Criar painel com ${n} gráfico${n > 1 ? "s" : ""}` : "Começar em branco"}</Button>
              {selectedDs && <span className="text-xs text-ink-mute">Dados: {selectedDs.name} · {out.usage.prompt_tokens + out.usage.completion_tokens} tokens</span>}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
