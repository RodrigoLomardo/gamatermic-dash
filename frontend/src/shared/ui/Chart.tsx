import { BarChart, GaugeChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([BarChart, LineChart, PieChart, GaugeChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

export function cssVar(name: string, el?: Element | null): string {
  return getComputedStyle(el ?? document.documentElement).getPropertyValue(name).trim();
}

export const palette = (el?: Element | null) => [1, 2, 3, 4, 5, 6, 7, 8].map((i) => cssVar(`--chart-${i}`, el));

/** Wrapper fino do ECharts (Canvas: leve em hardware fraco de TV). */
/** onIndexClick: clique em qualquer ponto da grade devolve o indice da categoria mais proxima (series temporais: o clique nao precisa acertar o simbolo). */
export function Chart({ option, onClick, onIndexClick, label }: { option: echarts.EChartsCoreOption; onClick?: (p: any) => void; onIndexClick?: (index: number) => void; label: string }) {
  const host = useRef<HTMLDivElement>(null);
  const inst = useRef<echarts.ECharts | null>(null);
  const click = useRef(onClick);
  click.current = onClick;
  const idxClick = useRef(onIndexClick);
  idxClick.current = onIndexClick;

  useEffect(() => {
    if (!host.current) return;
    const c = echarts.init(host.current, undefined, { renderer: "canvas" });
    inst.current = c;
    c.on("click", (p) => click.current?.(p));
    c.getZr().on("click", (e) => {
      if (!idxClick.current) return;
      const pt = [e.offsetX, e.offsetY];
      if (!c.containPixel("grid", pt)) return;
      const i = Math.round(Number(c.convertFromPixel({ seriesIndex: 0 }, pt)[0]));
      if (Number.isFinite(i) && i >= 0) idxClick.current(i);
    });
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(host.current);
    return () => { ro.disconnect(); c.dispose(); inst.current = null; };
  }, []);

  useEffect(() => { inst.current?.setOption(option, true); }, [option]);

  return <div ref={host} role="img" aria-label={label} className={`h-full w-full min-h-0${onIndexClick ? " cursor-pointer" : ""}`} />;
}
