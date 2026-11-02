import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { IconCopy, IconDots, IconLink, IconPencil, IconPower, IconTrash } from "@/app/icons";

export type CardMenuProps = {
  id: string; name: string; online: boolean;
  canEdit: boolean; canCreate: boolean; canDelete: boolean; busy: boolean;
  onDuplicate: () => void; onToggleOnline: () => void; onCopyLink: () => void; onCopyViewLink: () => void; onDelete: () => void;
  onOpenChange?: (open: boolean) => void;
};

/** Menu "⋯" do card: fecha com Esc, clique fora ou ao escolher; devolve o foco ao botao. */
export function CardMenu(p: CardMenuProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const set = (v: boolean) => { setOpen(v); p.onOpenChange?.(v); };
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) { setOpen(false); p.onOpenChange?.(false); } };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); p.onOpenChange?.(false); btn.current?.focus(); } };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", esc);
    root.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  const act = (fn: () => void) => () => { set(false); fn(); };
  const arrows = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = [...(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
    const i = items.indexOf(document.activeElement as HTMLElement);
    items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
  };
  return (
    <div ref={root} className="relative">
      <button ref={btn} type="button" aria-label={`Ações de ${p.name}`} aria-haspopup="menu" aria-expanded={open} onClick={() => set(!open)}
        className="grid h-10 w-10 place-items-center rounded-xl text-ink-soft transition hover:bg-brand-soft hover:text-ink active:scale-90"><IconDots /></button>
      {open && (
        <div role="menu" aria-label={`Ações de ${p.name}`} className="library-menu" onKeyDown={arrows}>
          {p.canEdit && <Link role="menuitem" to={`/dashboards/${p.id}/editar`} onClick={() => set(false)}><IconPencil /> Editar</Link>}
          {p.canCreate && <button role="menuitem" type="button" onClick={act(p.onDuplicate)}><IconCopy /> Duplicar</button>}
          {p.online && <button role="menuitem" type="button" onClick={act(p.onCopyLink)}><IconLink /> Copiar link do painel</button>}
          {p.online && <button role="menuitem" type="button" onClick={act(p.onCopyViewLink)}><IconLink /> Copiar link da TV</button>}
          {p.canEdit && <button role="menuitem" type="button" disabled={p.busy} onClick={act(p.onToggleOnline)}><IconPower /> {p.online ? "Tirar do ar" : "Lançar (colocar no ar)"}</button>}
          {p.canDelete && <><hr /><button role="menuitem" type="button" className="is-danger" onClick={act(p.onDelete)}><IconTrash /> Excluir</button></>}
        </div>
      )}
    </div>
  );
}
