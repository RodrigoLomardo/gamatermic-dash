import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { useState } from "react";
import { FilterBar } from "./FilterBar";
import { PeriodControl } from "./PeriodControl";
import type { FieldInfo } from "./hooks";
import type { AFilter } from "./state";
import type { PeriodSel } from "../dashboards/useDashboardData";

const fields = new Map<string, FieldInfo>([["cliente", { name: "cliente", label: "Cliente", data_type: "string", role: "dimension", datasetIds: ["d1"] }]]);
const initial: AFilter[] = [
  { field: "cliente", op: "in", value: ["ACME", "Beta", "Gama"], src: "manual" },
  { field: "segmento", op: "eq", value: "X", src: "drill" },
];

function Harness() {
  const [f, setF] = useState(initial);
  const [adding, setAdding] = useState(false);
  return <FilterBar id="d" filters={f} fields={fields} onChange={setF} adding={adding} onAddingChange={setAdding} />;
}

async function violations(container: HTMLElement) {
  const r = await axe.run(container, { rules: { "color-contrast": { enabled: false } } }); // jsdom nao calcula contraste
  return r.violations.map((v) => `${v.id}: ${v.nodes.length}`);
}

describe("FilterBar", () => {
  it("mostra só filtros manuais como chips (drill fica no breadcrumb) e resume vários valores", () => {
    render(<Harness />);
    const chip = screen.getByRole("button", { name: /editar filtro cliente/i });
    expect(chip).toHaveTextContent("ACME, Beta +1");
    expect(screen.queryByText("segmento")).not.toBeInTheDocument();
  });
  it("sem violações de acessibilidade (barra de filtros e período)", async () => {
    const { container } = render(<><Harness /><PeriodControl value={{ mode: "relative", preset: "this_month" }} onChange={() => {}} /></>);
    expect(await violations(container)).toEqual([]);
  });
  it("remover um chip preserva o filtro de drill", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: /remover filtro cliente/i }));
    await vi.waitFor(() => expect(screen.queryByRole("button", { name: /editar filtro cliente/i })).not.toBeInTheDocument());
  });
});

describe("PeriodControl", () => {
  it("marca o período atual e dispara a troca", async () => {
    const onChange = vi.fn();
    render(<PeriodControl value={{ mode: "relative", preset: "this_year" } as PeriodSel} onChange={onChange} />);
    const group = screen.getByRole("group", { name: "Período" });
    expect(within(group).getByRole("button", { name: "Ano" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(group).getByRole("button", { name: "Tudo" }));
    expect(onChange).toHaveBeenCalledWith({ mode: "relative", preset: "all" });
  });
  it("intervalo absoluto aparece no botão Outro", () => {
    render(<PeriodControl value={{ mode: "absolute", from: "2026-01-01", to: "2026-02-15" }} onChange={() => {}} />);
    expect(screen.getByRole("button", { name: "01/01/2026 – 15/02/2026" })).toHaveAttribute("aria-pressed", "true");
  });
});
