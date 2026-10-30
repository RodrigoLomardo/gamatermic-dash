import { useQuery } from "@tanstack/react-query";
import { get, post } from "@/shared/api/http";
import type { S } from "@/shared/api/http";
import type { DashboardData } from "../widgets/types";

export type Filter = { field: string; op: "eq"; value: string };
export type PeriodSel = { mode: "relative"; preset: string } | { mode: "absolute"; from: string; to: string };

export const PRESETS: [string, string][] = [
  ["today", "Hoje"], ["yesterday", "Ontem"], ["last_7_days", "Últimos 7 dias"], ["last_30_days", "Últimos 30 dias"], ["this_month", "Este mês"],
  ["last_month", "Mês passado"], ["this_quarter", "Este trimestre"], ["this_year", "Este ano"], ["last_year", "Ano passado"],
  ["last_12_months", "Últimos 12 meses"], ["all", "Todo o período"],
];

export function useDashboard(id: string | undefined) {
  return useQuery({ queryKey: ["dashboard", id], enabled: !!id, queryFn: () => get<S["DashboardOut"]>(`/dashboards/${id}`) });
}

export function useDashboardData(id: string | undefined, period: PeriodSel | null, filters: Filter[], refreshSeconds: number) {
  return useQuery({
    queryKey: ["dashboard-data", id, period, filters],
    enabled: !!id,
    refetchInterval: Math.max(15, refreshSeconds) * 1000,
    placeholderData: (prev) => prev,
    queryFn: () => post<DashboardData>(`/dashboards/${id}/data`, { period, filters }),
  });
}
