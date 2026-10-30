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
