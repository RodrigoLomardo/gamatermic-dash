import { useMemo } from "react";
import { IconGrid } from "@/app/icons";

/** PRNG deterministico (mulberry32) semeado pelo id: cada painel ganha sempre a mesma ilustracao. */
function rng(seed: string) {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) { h = Math.imul(h ^ seed.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
  let a = h >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

/** Previa ILUSTRATIVA (nao usa os dados do painel): barras que crescem na entrada e se reorganizam no hover. */
export function DashPreview({ id, empty }: { id: string; empty: boolean }) {
  const shape = useMemo(() => {
    const r = rng(id);
    const bars = Array.from({ length: 7 }, (_, i) => ({ h: Math.round(28 + r() * 62), h2: Math.round(24 + r() * 66), hot: i === 6 }));
    const lines = [88, 72, 80, 58, 66].map((w) => Math.round(w - r() * 14));
    return { bars, lines };
  }, [id]);
  if (empty) {
    return <div className="pv-empty"><IconGrid width={22} height={22} /> Pronto para o primeiro widget</div>;
  }
  return (
    <div className="pv" aria-hidden="true">
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
      <span className="pv-chip">Prévia ilustrativa</span>
    </div>
  );
}
