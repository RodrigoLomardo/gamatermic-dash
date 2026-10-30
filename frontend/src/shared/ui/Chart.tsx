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
export function Chart({ option, onClick, label }: { option: echarts.EChartsCoreOption; onClick?: (p: any) => void; label: string }) {
  const host = useRef<HTMLDivElement>(null);
  const inst = useRef<echarts.ECharts | null>(null);
  const click = useRef(onClick);
  click.current = onClick;

  useEffect(() => {
    if (!host.current) return;
    const c = echarts.init(host.current, undefined, { renderer: "canvas" });
    inst.current = c;
    c.on("click", (p) => click.current?.(p));
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(host.current);
    return () => { ro.disconnect(); c.dispose(); inst.current = null; };
  }, []);

  useEffect(() => { inst.current?.setOption(option, true); }, [option]);

  return <div ref={host} role="img" aria-label={label} className="h-full w-full min-h-0" />;
}
