import type { Widget } from "../widgets/types";
import { AFilter, addDrill, drillLevel, effectiveWidget, granAfter, parseView, planOverrides, serializeView, timeRange, truncateDrill } from "./state";

const drill = (field: string, value: string): AFilter => ({ field, op: "eq", value, src: "drill" });
const w = (over: Partial<Widget>): Widget => ({
  id: "w1", type: "bar", title: "t", x: 0, y: 0, w: 6, h: 4, dataset_id: "d", follows_global_period: true,
  query_config: { dimensions: ["segmento"], measures: [{ agg: "sum", field: "valor", alias: "total" }] },
  viz_config: { drill_path: ["segmento", "cliente", "responsavel"], drill_field: "segmento" }, ...over,
} as Widget);

describe("URL da visão", () => {
  it("ida e volta preserva período, filtros (drill/manual) e foco", () => {
    const v = { period: { mode: "relative" as const, preset: "this_year" }, focus: "abc",
      filters: [drill("segmento", "Indústria"), { field: "marca", op: "in" as const, value: ["A", "B"], src: "manual" as const }, { field: "data", op: "between" as const, value: ["2026-01-01", "2026-03-31"], src: "drill" as const, time: true }] };
    expect(parseView(serializeView(v))).toEqual(v);
  });
  it("período absoluto vai em from/to", () => {
    const sp = serializeView({ period: { mode: "absolute", from: "2026-01-01", to: "2026-02-01" }, filters: [], focus: null });
    expect(sp.get("from")).toBe("2026-01-01");
    expect(parseView(sp).period).toEqual({ mode: "absolute", from: "2026-01-01", to: "2026-02-01" });
  });
  it("URL adulterada abre sem filtros em vez de quebrar", () => {
    expect(parseView(new URLSearchParams("f=%7Bruim&p=<script>")).filters).toEqual([]);
    expect(parseView(new URLSearchParams("p=<script>")).period).toBeNull();
  });
});

describe("drill", () => {
  it("nível = campos consecutivos da trilha já filtrados", () => {
    const path = ["segmento", "cliente", "responsavel"];
    expect(drillLevel(path, [])).toBe(0);
    expect(drillLevel(path, [drill("segmento", "X")])).toBe(1);
    expect(drillLevel(path, [drill("cliente", "ACME")])).toBe(0); // pulou o primeiro nível
    expect(drillLevel(path, [drill("segmento", "X"), drill("cliente", "ACME")])).toBe(2);
  });
  it("filtro manual não conta como drill", () => {
    expect(drillLevel(["segmento"], [{ field: "segmento", op: "eq", value: "X", src: "manual" }])).toBe(0);
  });
  it("planOverrides regrupa pelo próximo nível e não mexe no que está no nível 0", () => {
    const widgets = [w({}), w({ id: "w2", type: "kpi", viz_config: {} })];
    expect(planOverrides(widgets, [], () => undefined).overrides).toEqual({});
    const p = planOverrides(widgets, [drill("segmento", "X")], () => undefined);
    expect(p.overrides).toEqual({ w1: { group_by: "cliente" } });
    expect(effectiveWidget(widgets[0], p.overrides.w1).viz_config).toMatchObject({ drill_field: "cliente" });
    expect((effectiveWidget(widgets[0], p.overrides.w1).query_config as { dimensions: string[] }).dimensions).toEqual(["cliente"]);
  });
  it("no último nível continua no último campo", () => {
    const f = [drill("segmento", "X"), drill("cliente", "A"), drill("responsavel", "R")];
    expect(planOverrides([w({})], f, () => undefined).overrides.w1).toEqual({ group_by: "responsavel" });
  });
  it("tabela de linhas (columns) não regrupa", () => {
    const t = w({ type: "table", query_config: { columns: ["a"] } });
    expect(planOverrides([t], [drill("segmento", "X")], () => undefined).overrides).toEqual({});
  });
  it("breadcrumb: voltar ao nível n mantém filtros manuais", () => {
    const m: AFilter = { field: "marca", op: "eq", value: "P", src: "manual" };
    const f = [drill("segmento", "X"), m, drill("cliente", "A")];
    expect(truncateDrill(f, 1)).toEqual([drill("segmento", "X"), m]);
    expect(truncateDrill(f, 0)).toEqual([m]);
  });
  it("addDrill troca o valor do mesmo campo e ignora repetição", () => {
    const f = addDrill([drill("segmento", "X")], { field: "segmento", op: "eq", value: "Y" });
    expect(f).toEqual([drill("segmento", "Y")]);
    expect(addDrill(f, { field: "segmento", op: "eq", value: "Y" })).toBe(f);
  });
});

describe("tempo", () => {
  it("intervalo de cada granularidade, com borda de mês/ano bissexto", () => {
    expect(timeRange("2026-03-01", "month")).toEqual(["2026-03-01", "2026-03-31"]);
    expect(timeRange("2024-02-01", "month")).toEqual(["2024-02-01", "2024-02-29"]);
    expect(timeRange("2026-04-01", "quarter")).toEqual(["2026-04-01", "2026-06-30"]);
    expect(timeRange("2026-01-01", "year")).toEqual(["2026-01-01", "2026-12-31"]);
    expect(timeRange("2026-12-30", "week")).toEqual(["2026-12-30", "2027-01-05"]);
    expect(timeRange("2026-05-09", "day")).toEqual(["2026-05-09", "2026-05-09"]);
  });
  it("desce ano > trimestre > mês > dia e para no dia", () => {
    expect(granAfter("year", 1)).toBe("quarter");
    expect(granAfter("month", 1)).toBe("day");
    expect(granAfter("month", 5)).toBe("day");
  });
  it("série temporal sobe a granularidade após clique no tempo", () => {
    const line = w({ id: "l", type: "line", query_config: { time: { granularity: "month" }, measures: [] }, viz_config: {} });
    const tf: AFilter = { field: "data", op: "between", value: ["2026-03-01", "2026-03-31"], src: "drill", time: true };
    const p = planOverrides([line], [tf], () => "data");
    expect(p.overrides.l).toEqual({ granularity: "day" });
    expect(p.gran.l).toBe("day");
  });
});
