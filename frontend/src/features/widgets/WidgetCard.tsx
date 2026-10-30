import { ReactNode } from "react";
import { cx } from "@/shared/ui/ui";
import { BarW, Gauge, Kpi, LineW, PieW, TableW } from "./renderers";
import type { DrillHandler, RenderProps, Widget, WidgetResult } from "./types";

// registry: tipo -> renderer (novos widgets entram aqui sem tocar nas paginas)
export const REGISTRY: Record<string, (p: RenderProps) => ReactNode> = {
  kpi: Kpi, gauge: Gauge, line: LineW, bar: BarW, pie: PieW, table: TableW,
};

export function WidgetCard({ widget, result, tv = false, onDrill, dim }: { widget: Widget; result?: WidgetResult; tv?: boolean; onDrill?: DrillHandler; dim?: boolean }) {
  const R = REGISTRY[widget.type];
  const body = !result ? <div className="h-full animate-pulse rounded-lg bg-brand-soft" aria-busy="true" />
    : result.error ? (
      // erro isolado: o widget falha sozinho, a dashboard segue
      <div role="alert" className="flex h-full flex-col items-center justify-center gap-1 text-center text-sm text-danger">
        <span className="font-semibold">Não foi possível carregar</span><span className="text-xs text-ink-mute">{result.error.message}</span>
      </div>
    ) : R ? <R widget={widget} result={result} tv={tv} onDrill={onDrill} /> : <div>Tipo não suportado: {widget.type}</div>;
  return (
    <article className={cx("flex h-full min-h-0 flex-col rounded-xl border border-line bg-panel shadow-card", tv ? "p-[clamp(.6rem,1vw,1.2rem)]" : "p-3", dim && "opacity-60")}>
      <h3 className={cx("truncate font-semibold text-ink-soft", tv ? "mb-1 text-[clamp(.85rem,1.3vw,1.4rem)]" : "mb-1 text-sm")}>{widget.title}</h3>
      <div className="min-h-0 flex-1">{body}</div>
    </article>
  );
}
