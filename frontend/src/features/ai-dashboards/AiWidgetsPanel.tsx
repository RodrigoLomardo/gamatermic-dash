import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useAuth } from "@/app/auth";
import { ApiError, S, get, post, put } from "@/shared/api/http";
import { Badge, Button, Empty, ErrorBox, Field, Select, Spinner, Textarea, cx, useToasts } from "@/shared/ui/ui";
import { isCompact } from "../widgets/sizes";
import type { Widget } from "../widgets/types";
import { ProposalCard } from "./AiCreatePage";
import { Box, arrange } from "./layout";

type Ds = S["DatasetOut"]; type Out = S["ProposalsOut"]; type Dash = S["DashboardOut"];
const EXAMPLES = ["Complemente com rankings e evolução mensal", "Ticket médio e quantidade por responsável", "Distribuição por segmento"];

/** Dataset mais usado pelos widgets do painel (o "dataset do painel"); sem widgets, o primeiro disponivel. */
export function mainDataset(widgets: Widget[], datasets: Ds[]): string {
  const count = new Map<string, number>();
  for (const w of widgets) if (w.dataset_id) count.set(w.dataset_id, (count.get(w.dataset_id) ?? 0) + 1);
  const best = [...count.entries()].filter(([id]) => datasets.some((d) => d.id === id)).sort((a, b) => b[1] - a[1])[0];
  return best?.[0] ?? datasets[0]?.id ?? "";
}

type PreviewItem = { id: string; title: string; box: Box; kind: "same" | "moved" | "new"; compact: boolean };
const same = (a: Box, b: Box) => a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;
const fmtBox = (b: Box) => `${b.w}×${b.h} em (${b.x}, ${b.y})`;

const KIND_STYLE: Record<PreviewItem["kind"], string> = {
  // cores solidas: modificador de opacidade (bg-x/40) nao funciona com as cores do tema (CSS vars)
  same: "border border-line bg-panel text-ink-mute",
  moved: "border-2 border-accent bg-panel text-ink",
  new: "border-2 border-accent bg-accent text-accent-on",
};

function Swatch({ className, label }: { className: string; label: string }) {
  return <span className="inline-flex items-center gap-1.5"><span aria-hidden className={cx("inline-block h-3 w-4 rounded-sm", className)} />{label}</span>;
}

/** Minimapa do layout final (grade de 12 colunas): o que fica igual, o que muda e o que entra. */
export function LayoutPreview({ items }: { items: PreviewItem[] }) {
  const n = items.filter((i) => i.kind === "new").length, m = items.filter((i) => i.kind === "moved").length;
  return (
    <figure className="space-y-2 rounded-xl border border-line p-3">
      <figcaption>
        <span className="block text-sm font-semibold">Como o painel vai ficar</span>
        <span className="text-xs text-ink-mute">{n} gráfico(s) novo(s), {m} ajustado(s). Cada bloco é um gráfico na grade do painel.</span>
      </figcaption>
      <div aria-hidden className="grid gap-1 rounded-lg bg-brand-soft p-1.5" style={{ gridTemplateColumns: "repeat(12, minmax(0, 1fr))", gridAutoRows: "14px" }}>
        {items.map((i) => (
          <div key={i.id} title={i.title} style={{ gridColumn: `${i.box.x + 1} / span ${i.box.w}`, gridRow: `${i.box.y + 1} / span ${i.box.h}` }}
            className={cx("flex min-w-0 flex-col overflow-hidden rounded-md px-1.5 py-1 text-[10px] leading-tight", KIND_STYLE[i.kind], i.compact && "border-dashed")}>
            {i.kind === "new" && <span className="text-[9px] font-bold uppercase tracking-wide">novo</span>}
            <span className="line-clamp-2 font-medium">{i.title}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
        <Swatch className={KIND_STYLE.new} label="Novo" />
        <Swatch className={KIND_STYLE.moved} label="Muda de lugar ou tamanho" />
        <Swatch className={KIND_STYLE.same} label="Continua igual" />
        <Swatch className="border-2 border-dashed border-ink-mute bg-panel" label="Fica na visão compacta" />
      </div>
    </figure>
  );
}

/**
 * Gera graficos com IA para um painel existente. A IA ve o layout atual (posicoes e tamanhos),
 * sugere onde encaixar cada grafico e, se precisar, mudancas nos existentes; o usuario aceita o que quiser.
 */
export function AiWidgetsPanel({ dashboardId, widgets, version, defaultPeriod, datasets, onAdded, onConflict }: {
  dashboardId: string; widgets: Widget[]; version: number; defaultPeriod: string; datasets: Ds[];
  onAdded: (d: Dash, added: number, moved: number) => void; onConflict: () => void;
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
  const [changes, setChanges] = useState<Set<string>>(new Set());

  // layout final com o que esta marcado agora (recalcula a cada caixinha)
  const plan = useMemo(() => {
    if (!out) return null;
    const ch = new Map(out.layout_changes.filter((c) => changes.has(c.widget_id)).map((c) => [c.widget_id, c.after]));
    const existing = widgets.map((w) => ({ id: w.id, ...(ch.get(w.id) ?? { x: w.x, y: w.y, w: w.w, h: w.h }) }));
    const chosen = out.proposals.filter((p) => picked.has(p.id));
    const boxes = arrange(existing, chosen.map((p) => ({ id: p.id, x: p.x ?? undefined, y: p.y ?? undefined, w: p.w, h: p.h })));
    const items: PreviewItem[] = [
      ...widgets.map((w) => { const b = boxes.get(w.id)!; return { id: w.id, title: w.title, box: b, kind: same(b, w) ? "same" as const : "moved" as const, compact: isCompact(w.type, b.w, b.h) }; }),
      ...chosen.map((p) => ({ id: p.id, title: p.title, box: boxes.get(p.id)!, kind: "new" as const, compact: false })),
    ];
    return { boxes, items, moved: widgets.filter((w) => !same(boxes.get(w.id)!, w)), chosen };
  }, [out, changes, picked, widgets]);

  if (status.isLoading) return <Spinner />;
  if (!status.data?.available) {
    return <p className="text-sm text-ink-soft">O assistente de IA não está ativo. {can("settings:manage") ? "Ative-o em Configurações → IA (Groq)." : "Peça a um administrador para ativá-lo."}</p>;
  }

  const generate = async () => {
    setError(null); setOut(null); setBusy("A IA está montando as sugestões…");
    try {
      const r = await post<Out>("/ai/dashboard-proposals", { dataset_id: dsId, dashboard_id: dashboardId, prompt: prompt.trim(), default_period: defaultPeriod });
      setOut(r); setPicked(new Set(r.proposals.map((p) => p.id))); setChanges(new Set(r.layout_changes.map((c) => c.widget_id)));
    } catch (e) { setError(e); } finally { setBusy(null); }
  };

  const add = async () => {
    if (!out || !plan) return;
    setBusy("Aplicando no painel…"); setError(null);
    let v = version; let last: Dash | null = null; let n = 0;
    const hdr = () => ({ headers: { "If-Match": `"${v}"` } });
    try {
      // 1) abre espaco: ajusta os graficos existentes (o que o usuario aceitou + o que precisou descer)
      if (plan.moved.length) {
        last = await put<Dash>(`/dashboards/${dashboardId}/layout`, { items: plan.moved.map((w) => ({ id: w.id, ...plan.boxes.get(w.id)! })) }, hdr());
        v = last.version;
      }
      // 2) entram os novos nas posicoes finais
      for (const p of plan.chosen) {
        last = await post<Dash>(`/dashboards/${dashboardId}/widgets`, {
          type: p.type, title: p.title, dataset_id: p.dataset_id, query_config: p.query_config, viz_config: p.viz_config,
          follows_global_period: p.follows_global_period, ...plan.boxes.get(p.id)!,
        }, hdr());
        v = last.version; n++;
      }
      if (last) onAdded(last, n, plan.moved.length);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) { onConflict(); return; }
      if (!last) { setError(e); return; }
      // o que ja entrou fica no painel; avisa o que faltou
      toast(`${plan.chosen.length - n} gráfico(s) não foram adicionados: ${e instanceof Error ? e.message : "erro"}`, "danger");
      onAdded(last, n, plan.moved.length);
    } finally { setBusy(null); }
  };

  const k = picked.size; const c = plan?.moved.length ?? 0;
  const applyLabel = k && c ? `Adicionar ${k} gráfico${k > 1 ? "s" : ""} e ajustar ${c}` : k ? `Adicionar ${k} gráfico${k > 1 ? "s" : ""} ao painel`
    : c ? `Aplicar ${c} ajuste${c > 1 ? "s" : ""} de layout` : "Selecione algo para aplicar";
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
          {out.proposals.length === 0 && !out.layout_changes.length ? (
            <Empty>{out.discarded.length
              ? "Tudo o que a IA sugeriu já está no painel. Peça uma informação diferente (por exemplo, por outro campo ou outra métrica)."
              : "Nenhum gráfico novo para este pedido. Reformule o pedido."}</Empty>
          ) : (
            <>
              {out.proposals.length > 0 && (
                <>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={() => setPicked(new Set(out.proposals.map((p) => p.id)))}>Todos</Button>
                    <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Nenhum</Button>
                  </div>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    {out.proposals.map((p) => <ProposalCard key={p.id} p={p} checked={picked.has(p.id)}
                      onToggle={() => setPicked((s) => { const nx = new Set(s); if (nx.has(p.id)) nx.delete(p.id); else nx.add(p.id); return nx; })} />)}
                  </div>
                </>
              )}
              {out.layout_changes.length > 0 && (
                <section aria-labelledby="ai-layout-changes" className="space-y-2 rounded-xl border border-line p-3">
                  <h3 id="ai-layout-changes" className="text-sm font-semibold">Mudanças sugeridas no layout</h3>
                  <ul className="space-y-2">
                    {out.layout_changes.map((ch) => (
                      <li key={ch.widget_id}>
                        <label className="flex cursor-pointer items-start gap-2 text-sm">
                          <input type="checkbox" className="mt-1" checked={changes.has(ch.widget_id)}
                            onChange={() => setChanges((s) => { const nx = new Set(s); if (nx.has(ch.widget_id)) nx.delete(ch.widget_id); else nx.add(ch.widget_id); return nx; })} />
                          <span>
                            <span className="font-semibold">Ajustar “{ch.title}”</span>{" "}
                            <span className="text-ink-mute">{fmtBox(ch.before)} → {fmtBox(ch.after)}</span>
                            {ch.compact && <> {" "}<Badge tone="warn">fica na visão compacta</Badge></>}
                            {ch.reason && <span className="block text-xs text-ink-soft">{ch.reason}</span>}
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {plan && <LayoutPreview items={plan.items} />}
              <div className="flex justify-end border-t border-line pt-3">
                <Button onClick={add} disabled={(k === 0 && c === 0) || !!busy}>{applyLabel}</Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
