import { useRef, useState } from "react";
import { Button, Input, Select, cx } from "@/shared/ui/ui";
import { PRESETS, PeriodSel } from "../dashboards/useDashboardData";
import { useOutside } from "./hooks";

const QUICK: [string, string][] = [["this_month", "Este mês"], ["last_month", "Mês passado"], ["this_quarter", "Trimestre"], ["this_year", "Ano"], ["last_12_months", "12 meses"], ["all", "Tudo"]];

/** Seletor segmentado com indicador deslizante; "Outro" abre presets restantes e intervalo absoluto. */
export function PeriodControl({ value, onChange }: { value: PeriodSel; onChange: (p: PeriodSel) => void }) {
  const idx = value.mode === "relative" ? QUICK.findIndex(([k]) => k === value.preset) : -1;
  const active = idx >= 0 ? idx : QUICK.length; // "Outro"
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, () => setOpen(false), open);
  const [from, setFrom] = useState(value.mode === "absolute" ? value.from : "");
  const [to, setTo] = useState(value.mode === "absolute" ? value.to : "");
  const n = QUICK.length + 1;
  const custom = value.mode === "absolute" ? `${value.from.split("-").reverse().join("/")} – ${value.to.split("-").reverse().join("/")}` : PRESETS.find(([k]) => k === (value as { preset: string }).preset)?.[1] ?? "Outro";
  return (
    <div ref={ref} className="relative">
      <div role="group" aria-label="Período" className="an-seg" style={{ "--n": n, "--idx": active } as React.CSSProperties}>
        <span className="an-seg-ind" aria-hidden="true" />
        {QUICK.map(([k, l]) => <button key={k} type="button" aria-pressed={idx >= 0 && QUICK[idx][0] === k} onClick={() => onChange({ mode: "relative", preset: k })}>{l}</button>)}
        <button type="button" aria-pressed={idx < 0} aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen((o) => !o)}>{idx < 0 ? custom : "Outro"}</button>
      </div>
      {open && (
        <div role="dialog" aria-label="Outro período" className="an-pop right-0 top-[calc(100%+8px)] w-80 space-y-4 p-4">
          <label className="block text-xs font-semibold text-ink-mute">Período pré-definido
            <Select className="mt-1" value={value.mode === "relative" ? value.preset : ""} onChange={(e) => { onChange({ mode: "relative", preset: e.target.value }); setOpen(false); }}>
              <option value="" disabled>Escolha…</option>
              {PRESETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </Select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs font-semibold text-ink-mute">De<Input type="date" className="mt-1" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} /></label>
            <label className="text-xs font-semibold text-ink-mute">Até<Input type="date" className="mt-1" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} /></label>
          </div>
          <Button className={cx("w-full")} disabled={!from || !to || from > to} onClick={() => { onChange({ mode: "absolute", from, to }); setOpen(false); }}>Aplicar intervalo</Button>
        </div>
      )}
    </div>
  );
}
