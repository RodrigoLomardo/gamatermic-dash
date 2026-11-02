import { cx } from "@/shared/ui/ui";
import { IconMoon, IconSun } from "./icons";
import { useColorMode } from "./theme";

/** Alterna claro/escuro. `onDark` ajusta as cores quando o botao fica sobre fundo navy fixo (login, topo mobile). */
export function ThemeToggle({ onDark = false, className }: { onDark?: boolean; className?: string }) {
  const { mode, toggle } = useColorMode();
  const dark = mode === "dark";
  return (
    <button type="button" onClick={toggle} aria-label={dark ? "Ativar modo claro" : "Ativar modo escuro"} title={dark ? "Modo claro" : "Modo escuro"}
      className={cx("group relative grid h-10 w-10 place-items-center overflow-hidden rounded-xl border transition hover:scale-105 active:scale-95",
        onDark ? "border-white/25 text-white hover:bg-white/10" : "border-line bg-panel text-ink-soft hover:text-ink hover:bg-brand-soft", className)}>
      <span className={cx("absolute transition-all duration-500 ease-out", dark ? "rotate-0 scale-100 opacity-100" : "-rotate-90 scale-50 opacity-0")}><IconMoon /></span>
      <span className={cx("absolute transition-all duration-500 ease-out", dark ? "rotate-90 scale-50 opacity-0" : "rotate-0 scale-100 opacity-100")}><IconSun /></span>
    </button>
  );
}
