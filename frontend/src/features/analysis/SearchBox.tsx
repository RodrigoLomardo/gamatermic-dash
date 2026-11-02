import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { IconSearch } from "@/app/icons";
import { S, get } from "@/shared/api/http";
import { cx } from "@/shared/ui/ui";
import { useDebounced, useOutside } from "./hooks";

type Hit = S["AnalysisSearchHit"];

/** Busca global: campos (abre o filtro) e valores (aplica o filtro direto). Atalho: "/". */
export function SearchBox({ id, onValue, onField }: { id: string; onValue: (h: Hit) => void; onField: (h: Hit) => void }) {
  const [q, setQ] = useState(""); const [open, setOpen] = useState(false); const [cur, setCur] = useState(0);
  const dq = useDebounced(q, 250);
  const box = useRef<HTMLDivElement>(null); const input = useRef<HTMLInputElement>(null);
  useOutside(box, () => setOpen(false), open);
  const res = useQuery({ queryKey: ["analysis-search", id, dq], enabled: dq.trim().length >= 2, placeholderData: (p) => p, queryFn: () => get<S["AnalysisSearchOut"]>(`/dashboards/${id}/analysis/search`, { query: { q: dq.trim() } }) });
  const hits = dq.trim().length >= 2 ? res.data?.hits ?? [] : [];
  useEffect(() => setCur(0), [dq]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test((e.target as HTMLElement).tagName)) { e.preventDefault(); input.current?.focus(); } };
    document.addEventListener("keydown", k); return () => document.removeEventListener("keydown", k);
  }, []);
  const pick = (h: Hit) => { (h.kind === "value" ? onValue : onField)(h); setQ(""); setOpen(false); input.current?.blur(); };
  return (
    <div ref={box} data-anchor className="relative">
      <div className="an-search">
        <IconSearch width={16} height={16} />
        <input ref={input} value={q} role="combobox" aria-expanded={open && hits.length > 0} aria-controls="an-search-list" aria-autocomplete="list" aria-label="Buscar campo ou valor"
          placeholder="Buscar cliente, campo…" onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setCur((c) => Math.min(hits.length - 1, c + 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setCur((c) => Math.max(0, c - 1)); }
            else if (e.key === "Enter" && hits[cur]) { e.preventDefault(); pick(hits[cur]); }
          }} />
        <kbd aria-hidden="true">/</kbd>
      </div>
      {open && dq.trim().length >= 2 && (
        <div className="an-pop right-0 top-[calc(100%+8px)] w-[26rem] max-w-[90vw] p-2">
          <ul id="an-search-list" role="listbox" className="an-list max-h-80 overflow-y-auto">
            {hits.map((h, i) => (
              <li key={`${h.dataset_id}-${h.field}-${h.value ?? ""}`} role="option" aria-selected={i === cur} style={{ "--i": Math.min(i, 12) } as React.CSSProperties}>
                <button type="button" className={cx("an-opt", i === cur && "is-cur")} onMouseEnter={() => setCur(i)} onClick={() => pick(h)}>
                  <span className={cx("an-tag", h.kind === "field" && "is-field")}>{h.kind === "field" ? "Campo" : h.label}</span>
                  <span className="min-w-0 flex-1 truncate text-left">{h.kind === "field" ? h.label : h.value}</span>
                  <span className="truncate text-xs text-ink-mute">{h.kind === "value" ? `${h.count}×` : h.dataset_name}</span>
                </button>
              </li>
            ))}
            {hits.length === 0 && <li className="px-3 py-4 text-center text-sm text-ink-mute">{res.isFetching ? "Buscando…" : "Nada encontrado."}</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
