import { create } from "zustand";
import { useEffect, useState } from "react";

const apply = (theme: "tv" | "default") => {
  if (theme === "tv") document.documentElement.dataset.theme = "tv";
  else delete document.documentElement.dataset.theme;
};

/** Aplica o tema sincronamente (graficos leem as CSS vars na montagem) e o reaplica no efeito (StrictMode remonta). */
export function useTheme(theme: "tv" | "default") {
  useState(() => apply(theme));
  useEffect(() => { apply(theme); return () => apply("default"); }, [theme]);
}

export type ColorMode = "light" | "dark";
const KEY = "gama-color-mode";

function initialMode(): ColorMode {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* storage indisponivel */ }
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

const paint = (mode: ColorMode) => {
  document.documentElement.dataset.mode = mode;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", mode === "dark" ? "#0f1926" : "#001F3B");
};

/** Modo claro/escuro do sistema inteiro (a TV tem tema proprio e o sobrepoe). Persistido por navegador. */
export const useColorMode = create<{ mode: ColorMode; toggle: () => void }>((set, get) => {
  const mode = initialMode();
  if (typeof document !== "undefined") paint(mode);
  return {
    mode,
    toggle: () => {
      const next: ColorMode = get().mode === "dark" ? "light" : "dark";
      const root = document.documentElement;
      root.classList.add("theme-fade");
      window.setTimeout(() => root.classList.remove("theme-fade"), 400);
      paint(next);
      try { localStorage.setItem(KEY, next); } catch { /* ignora */ }
      set({ mode: next });
    },
  };
});
