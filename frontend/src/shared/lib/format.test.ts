import { ago, deltaPct, fmt, fmtDate, toNum } from "./format";

describe("format pt-BR", () => {
  it("formata moeda sem perder o centavo em valores pequenos", () => {
    expect(fmt("36488.85", "currency").replace(/\s/g, " ")).toBe("R$ 36.489");
    expect(fmt("359.6", "currency").replace(/\s/g, " ")).toBe("R$ 359,60");
  });
  it("compacta milhoes", () => {
    expect(fmt("4210000", "currency", true)).toBe("R$ 4,21 mi");
    expect(fmt("25000", "currency", true)).toBe("R$ 25 mil");
  });
  it("trata nulos e strings numericas", () => {
    expect(fmt(null, "number")).toBe("—");
    expect(toNum("12.5")).toBe(12.5);
    expect(toNum("abc")).toBe(0);
  });
  it("datas ISO sem deslocar de dia por fuso", () => {
    expect(fmtDate("2026-01-03")).toBe("03/01/2026");
  });
  it("variacao percentual", () => {
    expect(deltaPct(150, 100)).toBe(0.5);
    expect(deltaPct(10, 0)).toBeNull();
  });
  it("tempo relativo", () => {
    const now = Date.parse("2026-10-30T12:00:00Z");
    expect(ago("2026-10-30T11:30:00Z", now)).toBe("há 30 min");
    expect(ago(null)).toBe("nunca");
  });
});
