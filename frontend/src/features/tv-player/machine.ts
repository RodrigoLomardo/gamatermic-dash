/** Logica pura do player (testavel sem DOM): estados de "desatualizado" e rotacao da playlist. */
export type Source = { dataset_id: string; name: string; last_loaded_at: string | null; stale: boolean };

export type ConnState = "online" | "offline";
export const OFFLINE_AFTER_MS = 3 * 60_000; // sem sucesso de rede ha 3 min -> "sem conexao"

export function connectionState(lastOkAt: number | null, now: number): ConnState {
  return lastOkAt != null && now - lastOkAt < OFFLINE_AFTER_MS ? "online" : "offline";
}

export function staleSources(sources: Source[] | undefined): Source[] {
  return (sources ?? []).filter((s) => s.stale);
}

export function nextIndex(cur: number, len: number): number {
  return len <= 1 ? 0 : (cur + 1) % len;
}

/** Item removido/sem acesso e pulado: devolve o proximo indice cuja dashboard nao esta em `blocked`. */
export function nextPlayable(cur: number, items: { dashboard_id: string }[], blocked: Set<string>): number {
  for (let i = 1; i <= items.length; i++) {
    const idx = (cur + i) % items.length;
    if (!blocked.has(items[idx].dashboard_id)) return idx;
  }
  return cur;
}

export function backoff(attempt: number, rnd = Math.random): number {
  const base = Math.min(60_000, 1000 * 2 ** attempt);
  return Math.round(base / 2 + rnd() * (base / 2)); // jitter
}

/** Deslocamento sutil de pixels (anti burn-in): ate 3 px, muda a cada 5 min. */
export function burnInOffset(now: number): { x: number; y: number } {
  const k = Math.floor(now / 300_000);
  return { x: (k % 7) - 3, y: (Math.floor(k / 7) % 7) - 3 };
}
