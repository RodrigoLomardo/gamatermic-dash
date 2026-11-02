import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { IconGrid } from "@/app/icons";
import { S, get, post } from "@/shared/api/http";
import { WidgetCard } from "../widgets/WidgetCard";
import type { DashboardData, Widget } from "../widgets/types";

/** PRNG deterministico (mulberry32) semeado pelo id: cada painel ganha sempre a mesma ilustracao. */
function rng(seed: string) {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) { h = Math.imul(h ^ seed.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
  let a = h >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

const LOGICAL_W = 1200; // largura "de desktop" em que a dashboard e desenhada antes de reduzir
const ROW = 96;         // gridAutoRows (84) + gap (12)
const PREVIEW_H = 188;

/** Ilustracao generica (sem dados): usada enquanto nao ha dado real ou se a leitura falhar. */
function Illustration({ id }: { id: string }) {
  const shape = useMemo(() => {
    const r = rng(id);
    const bars = Array.from({ length: 7 }, (_, i) => ({ h: Math.round(28 + r() * 62), h2: Math.round(24 + r() * 66), hot: i === 6 }));
    const lines = [88, 72, 80, 58, 66].map((w) => Math.round(w - r() * 14));
    return { bars, lines };
  }, [id]);
  return (
    <div className="pv-panel">
      <div className="pv-float">
        <div className="pv-bars">
          {shape.bars.map((b, i) => <span key={i} className={b.hot ? "pv-bar is-hot" : "pv-bar"} style={{ "--h": b.h, "--h2": b.h2, "--i": i } as React.CSSProperties} />)}
        </div>
        <div className="pv-lines">
          {shape.lines.map((w, i) => <span key={i} className="pv-line" style={{ "--w": w, "--i": i } as React.CSSProperties} />)}
        </div>
      </div>
    </div>
  );
}

/** Os widgets REAIS do painel, reduzidos. Sem interacao; no hover desliza suavemente para mostrar mais do painel. */
function LiveCanvas({ id, widgets, data }: { id: string; widgets: Widget[]; data: DashboardData }) {
  const box = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0);
  useEffect(() => {
    const el = box.current; if (!el) return;
    const measure = () => setScale(el.clientWidth / LOGICAL_W);
    measure();
    const ro = new ResizeObserver(measure); ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const results = useMemo(() => Object.fromEntries(data.widgets.map((r) => [r.widget_id, r])), [data]);
  const rows = Math.max(1, ...widgets.map((w) => w.y + w.h));
  const pan = scale ? Math.max(0, Math.min(rows * ROW * scale - PREVIEW_H + 12, 260)) / scale : 0;
  return (
    <div ref={box} className="pv-live" data-testid={`preview-${id}`}>
      {scale > 0 && (
        <div className="pv-canvas" style={{ "--s": scale, "--ny": `${-pan}px` } as React.CSSProperties}>
          <div className="grid gap-3 p-3" style={{ gridTemplateColumns: "repeat(12, minmax(0, 1fr))", gridAutoRows: "84px" }}>
            {widgets.map((w) => (
              <div key={w.id} style={{ gridColumn: `${w.x + 1} / span ${w.w}`, gridRow: `${w.y + 1} / span ${w.h}` }}>
                <WidgetCard widget={w} result={results[w.id]} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Live({ id }: { id: string }) {
  const dash = useQuery({ queryKey: ["dashboard", id], queryFn: () => get<S["DashboardOut"]>(`/dashboards/${id}`), staleTime: 60_000 });
  const data = useQuery({ queryKey: ["dashboard-preview", id], queryFn: () => post<DashboardData>(`/dashboards/${id}/data`, { period: null, filters: [] }), staleTime: 60_000, retry: 0 });
  if (dash.error || data.error) return <Illustration id={id} />;
  if (!dash.data || !data.data) return <div className="pv-skel" />;
  return <LiveCanvas id={id} widgets={dash.data.widgets as unknown as Widget[]} data={data.data} />;
}

/** Previa do painel no card: carrega so quando entra na tela (cada painel faz 2 requisicoes e monta varios graficos). */
export function DashPreview({ id, empty }: { id: string; empty: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || empty) return;
    if (typeof IntersectionObserver === "undefined") { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e?.isIntersecting) { setSeen(true); io.disconnect(); } }, { rootMargin: "240px" });
    io.observe(el);
    return () => io.disconnect();
  }, [empty]);
  if (empty) return <div className="pv-empty"><IconGrid width={22} height={22} /> Pronto para o primeiro widget</div>;
  return <div ref={ref} className="pv" aria-hidden="true">{seen ? <Live id={id} /> : <div className="pv-skel" />}</div>;
}
