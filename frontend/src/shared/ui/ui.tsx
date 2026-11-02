import { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes, useEffect, useId, useRef } from "react";
import { create } from "zustand";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
export { cx };

export function Button({ variant = "primary", size = "md", className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md" | "lg" }) {
  const v = {
    primary: "bg-accent text-accent-on hover:brightness-95 rounded-[8px_2px_8px_8px]",
    secondary: "rounded-lg bg-panel text-ink border border-line hover:bg-brand-soft",
    ghost: "rounded-lg text-ink-soft hover:bg-brand-soft",
    danger: "rounded-lg bg-danger text-on-status hover:opacity-90",
  }[variant];
  const s = { sm: "px-2.5 py-1 text-sm", md: "px-4 py-2 text-sm", lg: "px-6 py-3 text-base" }[size];
  return <button {...p} className={cx("inline-flex items-center justify-center gap-2 font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed", v, s, className)} />;
}

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string | null; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-ink-soft">{label}</label>
      {children(id)}
      {hint && !error && <p className="text-xs text-ink-mute">{hint}</p>}
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
    </div>
  );
}

const inputCls = "w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink placeholder:text-ink-mute focus:border-accent";
export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={cx(inputCls, p.className)} />;
export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={cx(inputCls, p.className)} />;
export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={cx(inputCls, p.className)} />;

export function Card({ title, actions, children, className, pad = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={cx("rounded-xl border border-line bg-panel shadow-card", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "ok" | "warn" | "danger" | "accent"; children: ReactNode }) {
  const t = {
    neutral: "bg-brand-soft text-ink-soft", ok: "bg-ok-soft text-ok-ink", warn: "bg-warn-soft text-warn-ink",
    danger: "bg-danger-soft text-danger-ink", accent: "bg-accent-soft text-accent-dark",
  }[tone];
  return <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold", t)}>{children}</span>;
}

export function Spinner({ label = "Carregando…" }: { label?: string }) {
  return <div role="status" className="flex items-center gap-2 p-6 text-ink-mute"><span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />{label}</div>;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error ?? "Erro");
  return (
    <div role="alert" className="rounded-lg border border-danger bg-danger-soft p-4 text-sm text-danger-ink">
      {msg} {onRetry && <button className="ml-2 font-semibold underline" onClick={onRetry}>Tentar de novo</button>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-line p-8 text-center text-ink-mute">{children}</div>;
}

export function Modal({ open, title, onClose, children, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("keydown", key); prev?.focus(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={cx("mt-10 w-full rounded-xl bg-panel shadow-2xl", wide ? "max-w-3xl" : "max-w-lg")}>
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button aria-label="Fechar" className="rounded p-1 text-ink-mute hover:bg-brand-soft" onClick={onClose}>✕</button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Table({ head, children, empty }: { head: string[]; children: ReactNode; empty?: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead><tr className="border-b border-line text-xs uppercase tracking-wide text-ink-mute">{head.map((h) => <th key={h} scope="col" className="px-3 py-2 font-semibold">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
      {empty}
    </div>
  );
}

type Toast = { id: number; text: string; tone: "ok" | "danger" };
export const useToasts = create<{ items: Toast[]; push: (text: string, tone?: Toast["tone"]) => void }>((set) => ({
  items: [],
  push: (text, tone = "ok") => {
    const id = Date.now() + Math.random();
    set((s) => ({ items: [...s.items, { id, text, tone }] }));
    setTimeout(() => set((s) => ({ items: s.items.filter((t) => t.id !== id) })), 5000);
  },
}));

export function Toasts() {
  const items = useToasts((s) => s.items);
  return (
    <div aria-live="polite" className="fixed bottom-4 right-4 z-[60] space-y-2">
      {items.map((t) => (
        <div key={t.id} className={cx("max-w-sm rounded-lg px-4 py-3 text-sm font-medium text-on-status shadow-lg", t.tone === "ok" ? "bg-ok" : "bg-danger")}>{t.text}</div>
      ))}
    </div>
  );
}

export function Logo({ light = true, height = 36 }: { light?: boolean; height?: number }) {
  // logo oficial (traco branco): usar sobre fundo azul-marinho; no fundo claro aplica filtro para o azul da marca
  return <img src="/brand/logo-gamatermic.png" alt="Gamatermic" style={{ height, width: "auto", ...(light ? {} : { filter: "brightness(0) saturate(100%) invert(10%) sepia(60%) saturate(2700%) hue-rotate(188deg)" }) }} />;
}
