import { ReactNode } from "react";
import { cx } from "@/shared/ui/ui";
import { BarCompact, GaugeCompact, LineCompact, PieCompact, TableCompact } from "./compact";
import { BarW, Gauge, Kpi, LineW, PieW, TableW } from "./renderers";
import { COMPACT_LABEL, isCompact } from "./sizes";
import type { DrillHandler, RenderProps, Widget, WidgetResult } from "./types";

// registry: tipo -> renderer (novos widgets entram aqui sem tocar nas paginas)
export const REGISTRY: Record<string, (p: RenderProps) => ReactNode> = {
  kpi: Kpi, gauge: Gauge, line: LineW, bar: BarW, pie: PieW, table: TableW,
};
// visao usada quando o widget fica menor que o tamanho completo do tipo (sizes.ts)
export const COMPACT_REGISTRY: Record<string, (p: RenderProps) => ReactNode> = {
  gauge: GaugeCompact, line: LineCompact, bar: BarCompact, pie: PieCompact, table: TableCompact,
};

export function WidgetCard({ widget, result, tv = false, onDrill, dim, size, showViewHint }: {
  widget: Widget; result?: WidgetResult; tv?: boolean; onDrill?: DrillHandler; dim?: boolean;
  /** tamanho atual na grade (no editor muda ao vivo enquanto o usuario arrasta); padrao: o salvo */
  size?: { w: number; h: number }; showViewHint?: boolean;
}) {
  const { w, h } = size ?? widget;
  const compact = isCompact(widget.type, w, h) && !!COMPACT_REGISTRY[widget.type];
  const R = compact ? COMPACT_REGISTRY[widget.type] : REGISTRY[widget.type];
  const body = !result ? <div className="h-full animate-pulse rounded-lg bg-brand-soft" aria-busy="true" />
    : result.error ? (
      // erro isolado: o widget falha sozinho, a dashboard segue
      <div role="alert" className="flex h-full flex-col items-center justify-center gap-1 text-center text-sm text-danger">
        <span className="font-semibold">Não foi possível carregar</span><span className="text-xs text-ink-mute">{result.error.message}</span>
      </div>
    ) : R ? <R widget={widget} result={result} tv={tv} onDrill={onDrill} /> : <div>Tipo não suportado: {widget.type}</div>;
  return (
    <article className={cx("relative flex h-full min-h-0 flex-col rounded-xl border border-line bg-panel shadow-card", tv ? "p-[clamp(.6rem,1vw,1.2rem)]" : "p-3", dim && "opacity-60")}
      data-view={compact ? "compact" : "full"}>
      <h3 className={cx("mb-1 truncate font-semibold text-ink-soft", tv ? "text-[clamp(.85rem,1.3vw,1.4rem)]" : "text-sm")}>{widget.title}</h3>
      <div className="min-h-0 flex-1">{body}</div>
      {compact && showViewHint && (
        // no canto de baixo: em cima ficam os botoes Editar/remover do editor
        <span className="pointer-events-auto absolute bottom-1.5 left-2 rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-ink-soft"
          title={`Visão compacta: ${COMPACT_LABEL[widget.type]}. Aumente o gráfico para ver a versão completa.`}>
          compacta
        </span>
      )}
    </article>
  );
}
