const TZ = "America/Sao_Paulo";
const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 2 });
const brl0 = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const int = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const pctF = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 });

export type Fmt = "number" | "currency" | "percent" | "integer" | "date" | undefined;

export function toNum(v: unknown): number {
  if (v == null || v === "") return 0;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** Decimais chegam como string (precisao); a formatacao usa Intl pt-BR/BRL. */
export function fmt(v: unknown, f: Fmt, compact = false): string {
  if (v == null || v === "") return "—";
  if (f === "date") return fmtDate(String(v));
  const n = toNum(v);
  if (f === "currency") {
    if (compact && Math.abs(n) >= 1_000_000) return `R$ ${num.format(n / 1_000_000)} mi`;
    if (compact && Math.abs(n) >= 10_000) return `R$ ${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: Math.abs(n) >= 100_000 ? 0 : 1 }).format(n / 1_000)} mil`;
    return Math.abs(n) >= 1000 ? brl0.format(n) : brl.format(n);
  }
  if (f === "percent") return pctF.format(n);
  if (f === "integer") return int.format(n);
  return num.format(n);
}

export function fmtDate(iso: string): string {
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(iso + "T12:00:00") : new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("pt-BR", { timeZone: /^\d{4}-\d{2}-\d{2}$/.test(iso) ? undefined : TZ });
}

export function fmtMonth(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }).replace(".", "");
}

export function fmtDateTime(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { timeZone: TZ, dateStyle: "short", timeStyle: "short" });
}

export function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("pt-BR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
}

export function ago(iso?: string | null, now = Date.now()): string {
  if (!iso) return "nunca";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "agora há pouco";
  if (s < 3600) return `há ${Math.floor(s / 60)} min`;
  if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
  return `há ${Math.floor(s / 86400)} d`;
}

export function deltaPct(cur: number, prev: number): number | null {
  if (!prev) return null;
  return (cur - prev) / Math.abs(prev);
}
