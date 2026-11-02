import type { S } from "@/shared/api/http";

export type Row = Record<string, string | number | boolean | null>;
export type WidgetResult = {
  widget_id: string; type: string; data: Row[] | null; previous: Row[] | null; dataset_version: number | null;
  data_as_of: string | null; generated_at: string | null; period: { from: string; to: string } | null;
  error: { code: string; message: string } | null; ignored_filters?: string[];
};
export type DashboardData = { dashboard_id: string; version: number; widgets: WidgetResult[] };
export type Widget = S["WidgetOut"];
export type Viz = {
  format?: "number" | "currency" | "percent" | "integer"; color?: string; target?: number; min?: number; max?: number;
  horizontal?: boolean; columns?: { field: string; label?: string; format?: "number" | "currency" | "percent" | "integer" | "date" }[]; drill_field?: string; drill_path?: string[];
};
export type DrillHandler = (field: string, value: string) => void;
/** clique em um ponto da serie temporal: recebe a data ISO (YYYY-MM-DD) do inicio do periodo clicado */
export type TimeDrillHandler = (iso: string) => void;
export type RenderProps = { widget: Widget; result: WidgetResult; tv: boolean; onDrill?: DrillHandler; onTimeDrill?: TimeDrillHandler };
