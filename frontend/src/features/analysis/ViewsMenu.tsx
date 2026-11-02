import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { IconBookmark, IconX } from "@/app/icons";
import { S, del, get, post } from "@/shared/api/http";
import { Button, Input, useToasts } from "@/shared/ui/ui";
import { useOutside } from "./hooks";
import type { AView } from "./state";

type ViewOut = S["AnalysisViewOut"];

/** Visoes salvas (pessoais): periodo + filtros + drill. Abrir uma aplica o estado na URL. */
export function ViewsMenu({ id, current, onApply }: { id: string; current: AView; onApply: (v: AView) => void }) {
  const [open, setOpen] = useState(false); const [name, setName] = useState("");
  const ref = useRef<HTMLDivElement>(null); useOutside(ref, () => setOpen(false), open);
  const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const views = useQuery({ queryKey: ["analysis-views", id], enabled: open, queryFn: () => get<ViewOut[]>(`/dashboards/${id}/analysis/views`) });
  const state = () => ({
    period: current.period ? (current.period.mode === "relative" ? { mode: "relative", preset: current.period.preset } : { mode: "absolute", from: current.period.from, to: current.period.to }) : null,
    filters: current.filters.map((f) => ({ field: f.field, op: f.op, value: f.value, src: f.src, time: !!f.time })), focus_widget_id: current.focus,
  });
  const save = useMutation({
    mutationFn: () => post<ViewOut>(`/dashboards/${id}/analysis/views`, { name: name.trim(), state: state() }),
    onSuccess: async () => { setName(""); toast("Visão salva."); await qc.invalidateQueries({ queryKey: ["analysis-views", id] }); },
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const remove = useMutation({
    mutationFn: (vid: string) => del(`/dashboards/${id}/analysis/views/${vid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analysis-views", id] }),
    onError: (e: Error) => toast(e.message, "danger"),
  });
  const apply = (v: ViewOut) => {
    const st = v.state;
    onApply({
      period: st.period ? (st.period.mode === "absolute" && st.period.from && st.period.to ? { mode: "absolute", from: st.period.from, to: st.period.to } : { mode: "relative", preset: st.period.preset ?? "this_month" }) : null,
      filters: (st.filters ?? []).map((f) => ({ field: f.field, op: f.op as never, value: f.value, src: f.src ?? "manual", ...(f.time ? { time: true } : {}) })),
      focus: st.focus_widget_id ?? null,
    });
    setOpen(false);
  };
  return (
    <div ref={ref} data-anchor className="relative">
      <Button variant="secondary" aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen((o) => !o)}><IconBookmark />Visões</Button>
      {open && (
        <div role="dialog" aria-label="Visões salvas" className="an-pop right-0 top-[calc(100%+8px)] w-80 p-3">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) save.mutate(); }}>
            <Input aria-label="Nome da visão" placeholder="Nome para a visão atual" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
            <Button size="sm" type="submit" disabled={!name.trim() || save.isPending}>Salvar</Button>
          </form>
          <ul className="an-list mt-3 max-h-64 overflow-y-auto">
            {(views.data ?? []).map((v, i) => (
              <li key={v.id} style={{ "--i": Math.min(i, 10) } as React.CSSProperties} className="group flex items-center">
                <button type="button" className="an-opt flex-1" onClick={() => apply(v)}><span className="truncate">{v.name}</span></button>
                <button type="button" className="an-chip-x opacity-0 transition group-hover:opacity-100 focus:opacity-100" aria-label={`Excluir visão ${v.name}`} onClick={() => remove.mutate(v.id)}><IconX /></button>
              </li>
            ))}
            {views.isLoading && <li className="px-2 py-3 text-sm text-ink-mute">Carregando…</li>}
            {views.data?.length === 0 && <li className="px-2 py-3 text-center text-sm text-ink-mute">Nenhuma visão salva ainda.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
