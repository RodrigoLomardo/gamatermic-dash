import { backoff, burnInOffset, connectionState, nextIndex, nextPlayable, staleSources } from "./machine";

describe("player machine", () => {
  it("considera offline apos 3 min sem sucesso", () => {
    expect(connectionState(1000, 1000 + 60_000)).toBe("online");
    expect(connectionState(1000, 1000 + 181_000)).toBe("offline");
    expect(connectionState(null, 5)).toBe("offline");
  });
  it("detecta fontes atrasadas (distinto de conexao)", () => {
    expect(staleSources([{ dataset_id: "a", name: "A", last_loaded_at: null, stale: true }, { dataset_id: "b", name: "B", last_loaded_at: null, stale: false }])).toHaveLength(1);
    expect(staleSources(undefined)).toEqual([]);
  });
  it("rotaciona e pula itens bloqueados", () => {
    expect(nextIndex(2, 3)).toBe(0);
    expect(nextIndex(0, 1)).toBe(0);
    const items = [{ dashboard_id: "a" }, { dashboard_id: "b" }, { dashboard_id: "c" }];
    expect(nextPlayable(0, items, new Set(["b"]))).toBe(2);
    expect(nextPlayable(0, items, new Set(["b", "c", "a"]))).toBe(0);
  });
  it("backoff exponencial com jitter limitado a 60 s", () => {
    expect(backoff(0, () => 0)).toBe(500);
    expect(backoff(0, () => 1)).toBe(1000);
    expect(backoff(10, () => 1)).toBe(60_000);
    expect(backoff(10, () => 0)).toBe(30_000);
  });
  it("anti burn-in varia pouco", () => {
    const o = burnInOffset(Date.now());
    expect(Math.abs(o.x)).toBeLessThanOrEqual(3);
    expect(Math.abs(o.y)).toBeLessThanOrEqual(3);
  });
});
