import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useAuth } from "@/app/auth";
import { IconPlus, IconSparkles, IconX } from "@/app/icons";
import { S, get, post } from "@/shared/api/http";
import { Button, cx, useToasts } from "@/shared/ui/ui";
import type { Filter } from "../dashboards/useDashboardData";
import { WidgetCard } from "../widgets/WidgetCard";
import type { Widget, WidgetResult } from "../widgets/types";
import { toApiFilters, type AFilter, type AView } from "./state";

type Out = S["AnalysisChatOut"];
type Msg = { id: number; role: "user" | "assistant"; text: string; out?: Out; error?: boolean };

const STARTERS = ["Qual o faturamento por mês?", "Top 10 clientes por valor", "Pedidos por empresa do grupo", "Ticket médio por vendedor"];
const key = (id: string) => `gama:analysis-chat:${id}`;

function load(id: string): Msg[] {
  try { return JSON.parse(sessionStorage.getItem(key(id)) ?? "[]") as Msg[]; } catch { return []; }
}

export function periodApi(p: AView["period"]) {
  return p ? (p.mode === "relative" ? { mode: "relative", preset: p.preset } : { mode: "absolute", from: p.from, to: p.to }) : null;
}

/** Converte "aplicar a tela" da resposta em novo estado da visao (filtros entram como manuais, editaveis). */
export function applyToView(v: AView, a: NonNullable<Out["apply"]>): AView {
  const per = a.period as { mode?: string; preset?: string; from?: string; to?: string } | null;
  const incoming: AFilter[] = a.filters.map((f) => ({ field: f.field, op: f.op as Filter["op"], value: f.value, src: "manual" as const }));
  const kept = v.filters.filter((f) => !incoming.some((n) => n.field === f.field && f.src === "manual"));
  return {
    ...v, filters: [...kept, ...incoming].slice(0, 20),
    period: per?.mode === "absolute" && per.from && per.to ? { mode: "absolute", from: per.from, to: per.to } : per?.preset ? { mode: "relative", preset: per.preset } : v.period,
  };
}

function Bubble({ m, children }: { m: Msg; children?: React.ReactNode }) {
  return <div className={cx("an-msg", m.role === "user" ? "is-user" : "is-bot", m.error && "is-error")}><p>{m.text}</p>{children}</div>;
}

function Answer({ m, dashId, canEdit, onApply, onAsk }: { m: Msg; dashId: string; canEdit: boolean; onApply: (a: NonNullable<Out["apply"]>) => void; onAsk: (q: string) => void }) {
  const out = m.out!; const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const [added, setAdded] = useState(false);
  const add = useMutation({
    mutationFn: async () => {
      const w = out.widget!;
      const dash = await get<S["DashboardOut"]>(`/dashboards/${dashId}`);
      const y = Math.max(0, ...dash.widgets.map((x) => x.y + x.h));
      return post(`/dashboards/${dashId}/widgets`, { type: w.type, title: w.title, dataset_id: w.dataset_id, query_config: w.query_config, viz_config: w.viz_config,
        follows_global_period: w.follows_global_period, x: 0, y, w: w.w, h: w.h }, { headers: { "If-Match": `"${dash.version}"` } });
    },
    onSuccess: async () => { setAdded(true); toast("Gráfico adicionado ao painel (confira em Editar)."); await qc.invalidateQueries({ queryKey: ["dashboard", dashId] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const widget = out.widget as unknown as Widget | null;
  const result = out.result as unknown as WidgetResult | null;
  return (
    <Bubble m={m}>
      {out.interpretation.length > 0 && <ul className="an-interp" aria-label="Como entendi">{out.interpretation.map((t) => <li key={t}>{t}</li>)}</ul>}
      {widget && result && (
        <div className="an-chat-chart"><WidgetCard widget={widget} result={result} size={{ w: 12, h: 8 }} /></div>
      )}
      {out.notes.map((n) => <p key={n} className="an-note">{n}</p>)}
      {(out.apply || widget) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {out.apply && <button type="button" className="an-btn" onClick={() => onApply(out.apply!)}>Aplicar à tela</button>}
          {widget && canEdit && <button type="button" className="an-btn" disabled={add.isPending || added} onClick={() => add.mutate()}><IconPlus width={14} height={14} />{added ? "Adicionado" : "Adicionar ao painel"}</button>}
        </div>
      )}
      {out.suggestions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">{out.suggestions.map((q) => <button key={q} type="button" className="an-suggest" onClick={() => onAsk(q)}>{q}</button>)}</div>
      )}
    </Bubble>
  );
}

/** Chat lateral: a IA escolhe a consulta (QuerySpec validado), o backend calcula. Numeros nunca vem do texto do modelo. */
export function ChatPanel({ dashId, view, onApply, onClose }: { dashId: string; view: AView; onApply: (a: NonNullable<Out["apply"]>) => void; onClose: () => void }) {
  const canEdit = useAuth((s) => s.can)("dashboard:edit");
  const [msgs, setMsgs] = useState<Msg[]>(() => load(dashId));
  const [text, setText] = useState("");
  const scroller = useRef<HTMLDivElement>(null); const input = useRef<HTMLTextAreaElement>(null);
  const next = useRef(Date.now());
  useEffect(() => { try { sessionStorage.setItem(key(dashId), JSON.stringify(msgs.slice(-30))); } catch { /* sem storage: so nao persiste */ } }, [msgs, dashId]);
  useEffect(() => { input.current?.focus(); }, []);

  const send = useMutation({
    mutationFn: ({ q, history }: { q: string; history: { role: "user" | "assistant"; text: string }[] }) => {
      return post<Out>(`/dashboards/${dashId}/analysis/chat`, { message: q, history, view: { period: periodApi(view.period), filters: toApiFilters(view.filters) } });
    },
    onSuccess: (out) => setMsgs((m) => [...m, { id: ++next.current, role: "assistant", text: out.message, out }]),
    onError: (e: Error) => setMsgs((m) => [...m, { id: ++next.current, role: "assistant", error: true, text: e.message }]),
  });
  useEffect(() => { if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight; }, [msgs.length, send.isPending]); // rolagem suave vem do CSS

  const ask = (q: string) => {
    const t = q.trim();
    if (!t || send.isPending) return;
    // historico = conversa ANTES desta pergunta (ela segue separada no pedido); a resposta anterior leva o resumo do que foi mostrado
    const history = msgs.filter((m) => !m.error).slice(-8).map((m) => ({ role: m.role, text: (m.role === "assistant" && m.out?.summary ? `${m.text}\n[mostrado: ${m.out.summary}]` : m.text).slice(0, 1500) }));
    setMsgs((m) => [...m, { id: ++next.current, role: "user", text: t }]);
    setText("");
    send.mutate({ q: t, history });
  };
  const submit = (e: FormEvent) => { e.preventDefault(); ask(text); };
  const empty = msgs.length === 0;
  return (
    <aside className="an-chat" aria-label="Perguntar à IA">
      <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="flex items-center gap-2"><span className="an-orb" aria-hidden="true"><IconSparkles width={14} height={14} /></span><h2 className="text-sm font-bold">Pergunte aos seus dados</h2></div>
        <div className="flex items-center gap-1">
          {!empty && <button type="button" className="an-suggest" onClick={() => setMsgs([])}>Limpar</button>}
          <button type="button" aria-label="Fechar chat" className="an-icon-btn" onClick={onClose}><IconX width={16} height={16} /></button>
        </div>
      </header>
      <div ref={scroller} className="min-h-0 flex-1 scroll-smooth space-y-3 overflow-y-auto px-4 py-4" role="log" aria-live="polite">
        {empty && (
          <div className="an-hello">
            <p className="text-base font-semibold">Como posso ajudar na análise?</p>
            <p className="mt-1 text-sm text-ink-soft">Faça perguntas em português. Eu escolho a consulta; os números vêm sempre do banco, nunca do texto da IA.</p>
            <div className="mt-3 flex flex-wrap gap-1.5">{STARTERS.map((q) => <button key={q} type="button" className="an-suggest" onClick={() => ask(q)}>{q}</button>)}</div>
          </div>
        )}
        {msgs.map((m) => m.out ? <Answer key={m.id} m={m} dashId={dashId} canEdit={canEdit} onApply={onApply} onAsk={ask} /> : <Bubble key={m.id} m={m} />)}
        {send.isPending && <div className="an-msg is-bot" aria-label="Pensando"><span className="an-dots"><i /><i /><i /></span></div>}
      </div>
      <form onSubmit={submit} className="border-t border-line p-3">
        <div className="an-compose">
          <textarea ref={input} rows={1} maxLength={600} aria-label="Sua pergunta" placeholder="Ex.: top 10 clientes em 2025" value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(text); } }} />
          <Button type="submit" size="sm" disabled={!text.trim() || send.isPending}>Enviar</Button>
        </div>
      </form>
    </aside>
  );
}

export function useChatStatus(dashId: string | undefined) {
  return useQuery({ queryKey: ["analysis-chat-status", dashId], enabled: !!dashId, retry: false, staleTime: 60_000, queryFn: () => get<S["AnalysisChatStatus"]>(`/dashboards/${dashId}/analysis/chat/status`) });
}
