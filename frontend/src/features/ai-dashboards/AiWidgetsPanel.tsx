import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useAuth } from "@/app/auth";
import { ApiError, S, get, post } from "@/shared/api/http";
import { Button, Empty, ErrorBox, Field, Select, Spinner, Textarea, useToasts } from "@/shared/ui/ui";
import type { Widget } from "../widgets/types";
import { ProposalCard } from "./AiCreatePage";
import { pack } from "./layout";

type Ds = S["DatasetOut"]; type Out = S["ProposalsOut"]; type Dash = S["DashboardOut"];
const EXAMPLES = ["Complemente com rankings e evolução mensal", "Ticket médio e quantidade por responsável", "Distribuição por segmento"];

/** Dataset mais usado pelos widgets do painel (o "dataset do painel"); sem widgets, o primeiro disponivel. */
export function mainDataset(widgets: Widget[], datasets: Ds[]): string {
  const count = new Map<string, number>();
  for (const w of widgets) if (w.dataset_id) count.set(w.dataset_id, (count.get(w.dataset_id) ?? 0) + 1);
  const best = [...count.entries()].filter(([id]) => datasets.some((d) => d.id === id)).sort((a, b) => b[1] - a[1])[0];
  return best?.[0] ?? datasets[0]?.id ?? "";
}

/**
 * Gera graficos com IA para um painel existente e os acrescenta abaixo dos atuais.
 * A IA ve os titulos ja no painel e o backend descarta repetidos (dashboard_id na requisicao).
 */
export function AiWidgetsPanel({ dashboardId, widgets, version, defaultPeriod, datasets, onAdded, onConflict }: {
  dashboardId: string; widgets: Widget[]; version: number; defaultPeriod: string; datasets: Ds[];
  onAdded: (d: Dash, added: number) => void; onConflict: () => void;
}) {
  const { can } = useAuth(); const toast = useToasts((s) => s.push);
  const status = useQuery({ queryKey: ["ai-status"], queryFn: () => get<S["AiStatusOut"]>("/ai/status") });
  const used = useMemo(() => new Set(widgets.map((w) => w.dataset_id)), [widgets]);
  // datasets do painel primeiro
  const ordered = useMemo(() => [...datasets].sort((a, b) => Number(used.has(b.id)) - Number(used.has(a.id))), [datasets, used]);
  const [dsId, setDsId] = useState(() => mainDataset(widgets, datasets));
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [out, setOut] = useState<Out | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  if (status.isLoading) return <Spinner />;
  if (!status.data?.available) {
    return <p className="text-sm text-ink-soft">O assistente de IA não está ativo. {can("settings:manage") ? "Ative-o em Configurações → IA (Groq)." : "Peça a um administrador para ativá-lo."}</p>;
  }

  const generate = async () => {
    setError(null); setOut(null); setBusy("A IA está montando as sugestões…");
    try {
      const r = await post<Out>("/ai/dashboard-proposals", { dataset_id: dsId, dashboard_id: dashboardId, prompt: prompt.trim(), default_period: defaultPeriod });
      setOut(r); setPicked(new Set(r.proposals.map((p) => p.id)));
    } catch (e) { setError(e); } finally { setBusy(null); }
  };

  const add = async () => {
    if (!out) return;
    setBusy("Adicionando ao painel…"); setError(null);
    const top = Math.max(0, ...widgets.map((w) => w.y + w.h));
    const chosen = pack(out.proposals.filter((p) => picked.has(p.id)));
    let v = version; let last: Dash | null = null; let n = 0;
    try {
      for (const p of chosen) {
        last = await post<Dash>(`/dashboards/${dashboardId}/widgets`, {
          type: p.type, title: p.title, dataset_id: p.dataset_id, query_config: p.query_config, viz_config: p.viz_config,
          follows_global_period: p.follows_global_period, x: p.x, y: top + p.y, w: p.w, h: p.h,
        }, { headers: { "If-Match": `"${v}"` } });
        v = last.version; n++;
      }
      if (last) onAdded(last, n);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) { onConflict(); return; }
      if (!last) { setError(e); return; }
      // o que ja entrou fica no painel; avisa o que faltou
      toast(`${chosen.length - n} gráfico(s) não foram adicionados: ${e instanceof Error ? e.message : "erro"}`, "danger");
      onAdded(last, n);
    } finally { setBusy(null); }
  };

  const k = picked.size;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-[minmax(0,20rem)_1fr]">
        <Field label="Dados" hint={used.has(dsId) ? "Dataset usado neste painel." : undefined}>
          {(id) => <Select id={id} value={dsId} onChange={(e) => { setDsId(e.target.value); setOut(null); }}>
            {ordered.map((d) => <option key={d.id} value={d.id}>{d.name}{used.has(d.id) ? " (do painel)" : ""}</option>)}
          </Select>}
        </Field>
        <Field label="Que gráficos você quer acrescentar?" hint="A IA vê os gráficos que já existem e não repete.">
          {(id) => <Textarea id={id} rows={2} maxLength={1000} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={EXAMPLES[0]} />}
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {EXAMPLES.map((x) => <button key={x} type="button" className="rounded-full border border-line px-3 py-1 text-xs hover:bg-brand-soft" onClick={() => setPrompt(x)}>{x}</button>)}
        <Button className="ml-auto" onClick={generate} disabled={prompt.trim().length < 3 || !dsId || !!busy}>{out ? "Gerar de novo" : "Gerar gráficos"}</Button>
      </div>
      {busy && <p role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-ink-soft"><span className="h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />{busy}</p>}
      {!!error && <ErrorBox error={error} />}
      {out && (
        <div className="space-y-3">
          {out.explanation && <p className="text-sm text-ink-soft">{out.explanation}</p>}
          {out.discarded.length > 0 && (
            <details className="text-xs text-ink-mute"><summary>{out.discarded.length} sugestão(ões) descartada(s) (inválidas ou repetidas)</summary>
              <ul className="ml-4 list-disc">{out.discarded.map((d, i) => <li key={i}>{d.title}: {d.reason}</li>)}</ul></details>
          )}
          {out.proposals.length === 0 ? <Empty>Nenhum gráfico novo para este pedido. Reformule o pedido.</Empty> : (
            <>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => setPicked(new Set(out.proposals.map((p) => p.id)))}>Todos</Button>
                <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Nenhum</Button>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {out.proposals.map((p) => <ProposalCard key={p.id} p={p} checked={picked.has(p.id)}
                  onToggle={() => setPicked((s) => { const nx = new Set(s); if (nx.has(p.id)) nx.delete(p.id); else nx.add(p.id); return nx; })} />)}
              </div>
              <div className="flex justify-end border-t border-line pt-3">
                <Button onClick={add} disabled={k === 0 || !!busy}>{k ? `Adicionar ${k} gráfico${k > 1 ? "s" : ""} ao painel` : "Selecione ao menos um"}</Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
