import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { S, api, get } from "@/shared/api/http";
import { fmtDate } from "@/shared/lib/format";

export type FieldInfo = { name: string; label: string; data_type: string; role: string; datasetIds: string[] };
export type AnalysisFields = S["AnalysisFieldsOut"];

export function useAnalysisFields(id: string | undefined) {
  return useQuery({ queryKey: ["analysis-fields", id], enabled: !!id, retry: false, staleTime: 5 * 60_000, queryFn: () => get<AnalysisFields>(`/dashboards/${id}/analysis/fields`) });
}

/** Campos de todos os datasets do painel, unidos pelo nome (um filtro vale em todo dataset que tem o campo). */
export function fieldIndex(data: AnalysisFields | undefined): Map<string, FieldInfo> {
  const m = new Map<string, FieldInfo>();
  for (const ds of data?.datasets ?? []) {
    for (const f of ds.fields) {
      const cur = m.get(f.name);
      if (cur) cur.datasetIds.push(ds.dataset_id);
      else m.set(f.name, { name: f.name, label: f.label, data_type: f.data_type, role: f.role, datasetIds: [ds.dataset_id] });
    }
  }
  return m;
}

export function useDebounced<T>(value: T, ms = 220): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

export function useValues(id: string | undefined, datasetId: string | undefined, field: string | undefined, q: string) {
  const dq = useDebounced(q);
  return useQuery({
    queryKey: ["analysis-values", id, datasetId, field, dq], enabled: !!id && !!datasetId && !!field, placeholderData: (p) => p, staleTime: 30_000,
    queryFn: () => get<S["AnalysisValuesOut"]>(`/dashboards/${id}/analysis/values`, { query: { dataset_id: datasetId, field, q: dq || undefined } }),
  });
}

/** Contagem animada (easing) para numeros que mudam: total de registros etc. */
export function useCountUp(target: number, ms = 650): number {
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(target); from.current = target; return; }
    const a = from.current; const t0 = performance.now(); let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / ms); const e = 1 - Math.pow(1 - k, 3);
      const cur = Math.round(a + (target - a) * e); setV(cur); from.current = cur;
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

export const fmtVal = (v: unknown): string => (typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) ? fmtDate(v) : v === true ? "Sim" : v === false ? "Não" : String(v));

/** Baixa um CSV gerado pelo backend (precisa do header Authorization, entao nao da para usar um link). */
export async function downloadCsv(path: string, body: unknown, filename: string) {
  const csv = await api<string>("POST", path, { body, text: true });
  const url = URL.createObjectURL(new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" })); // Response.text() descarta o BOM; o Excel pt-BR precisa dele
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function useOutside(ref: React.RefObject<HTMLElement>, onOut: () => void, active = true) {
  const cb = useRef(onOut); cb.current = onOut;
  useEffect(() => {
    if (!active) return;
    // o gatilho (botao) fica dentro do mesmo [data-anchor]: clicar nele nao deve fechar e reabrir
    const down = (e: MouseEvent) => { const box = ref.current?.closest("[data-anchor]") ?? ref.current; if (box && !box.contains(e.target as Node)) cb.current(); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") cb.current(); };
    document.addEventListener("mousedown", down); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key); };
  }, [ref, active]);
}
