import { render, screen } from "@testing-library/react";
import { WidgetCard } from "./WidgetCard";
import type { Widget, WidgetResult } from "./types";

const w = (over: Partial<Widget>): Widget => ({
  id: "w1", type: "kpi", title: "Faturamento", x: 0, y: 0, w: 3, h: 3, dataset_id: "d", query_config: {}, viz_config: { format: "currency" }, follows_global_period: true, ...over,
} as Widget);
const res = (over: Partial<WidgetResult>): WidgetResult => ({
  widget_id: "w1", type: "kpi", data: [], previous: null, dataset_version: 1, data_as_of: null, generated_at: null, period: null, error: null, ...over,
});

describe("WidgetCard", () => {
  it("KPI mostra valor em BRL e variação vs período anterior", () => {
    render(<WidgetCard widget={w({})} result={res({ data: [{ total: "150" }], previous: [{ total: "100" }] })} />);
    expect(screen.getByText("Faturamento")).toBeInTheDocument();
    expect(screen.getByText(/R\$\s150/)).toBeInTheDocument();
    expect(screen.getByText(/▲ 50,0%/)).toBeInTheDocument();
  });
  it("erro de um widget é isolado e exibe mensagem", () => {
    render(<WidgetCard widget={w({})} result={res({ error: { code: "unknown_field", message: "Campo inexistente" } })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Campo inexistente");
  });
  it("tabela formata colunas e permite drill-down por clique", async () => {
    const onDrill = vi.fn();
    render(<WidgetCard widget={w({ type: "table", viz_config: { drill_field: "cliente", columns: [{ field: "cliente", label: "Cliente" }, { field: "valor", label: "Valor", format: "currency" }] } })}
      result={res({ type: "table", data: [{ cliente: "ACME", valor: "1234.5" }] })} onDrill={onDrill} />);
    expect(screen.getByText(/R\$\s1\.235/)).toBeInTheDocument();
    screen.getByText("ACME").click();
    expect(onDrill).toHaveBeenCalledWith("cliente", "ACME");
  });
  it("carregando mostra esqueleto acessível", () => {
    render(<WidgetCard widget={w({})} />);
    expect(document.querySelector("[aria-busy=true]")).toBeTruthy();
  });
});
