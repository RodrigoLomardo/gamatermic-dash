import { ReactNode, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { IconX } from "@/app/icons";

/** Folha lateral com entrada/saida animadas (slide + fade do fundo). Foco volta a quem abriu. */
export function Sheet({ title, onClose, children, actions }: { title: ReactNode; onClose: () => void; children: ReactNode; actions?: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null); const back = useRef<HTMLDivElement>(null);
  const closing = useRef(false);
  const close = useCallback(() => {
    if (closing.current) return; closing.current = true;
    const dur = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 240;
    panel.current?.animate([{ transform: "none" }, { transform: "translateX(100%)" }], { duration: dur, easing: "cubic-bezier(.4,0,1,1)", fill: "forwards" });
    back.current?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: dur, fill: "forwards" });
    setTimeout(onClose, dur);
  }, [onClose]);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    // captura + stopImmediatePropagation: com a tela cheia aberta por baixo, Esc fecha so a camada de cima
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopImmediatePropagation(); close(); } };
    window.addEventListener("keydown", key, true);
    return () => { window.removeEventListener("keydown", key, true); prev?.focus?.(); };
  }, [close]);
  return createPortal(
    <div className="fixed inset-0 z-50">
      <div ref={back} className="an-backdrop absolute inset-0" onMouseDown={close} />
      <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : "Detalhes"} className="an-sheet absolute inset-y-0 right-0 flex w-[min(60rem,94vw)] flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-line px-6 py-4">
          <div className="min-w-0 flex-1">{title}</div>
          <div className="flex items-center gap-2">{actions}<button type="button" aria-label="Fechar" className="an-icon-btn" onClick={close}><IconX width={16} height={16} /></button></div>
        </header>
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
