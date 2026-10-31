import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { AiCreatePage } from "./AiCreatePage";
import { pack } from "./layout";

const DS = { id: "ds1", name: "Vendas (pedidos)", row_count: 10, sector_id: "s1" };
const preview = (data: unknown[]) => ({ widget_id: "x", type: "kpi", data, previous: null, dataset_version: 1, data_as_of: null, generated_at: null, period: null, error: null });
const P = (id: string, type: string, title: string, w = 3, h = 3) => ({
  id, type, title, rationale: `por que ${title}`, dataset_id: "ds1", query_config: { measures: [{ agg: "count", alias: "qtd" }] },
  viz_config: type === "table" ? { columns: [{ field: "qtd", label: "Qtd" }] } : { format: "integer" }, follows_global_period: true, w, h,
  preview: preview([{ qtd: "7" }]),
});
const OUT = { explanation: "Três visões.", proposals: [P("a", "kpi", "Pedidos"), P("b", "kpi", "Ticket"), P("c", "table", "Tabela", 6, 4)], discarded: [{ title: "X", reason: "Campo inexistente" }],
  usage: { model: "openai/gpt-oss-120b", prompt_tokens: 10, completion_tokens: 5 } };

type Call = { url: string; method: string; body: any };
function mockApi(available = true) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input); const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body });
    const json = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json" } });
    if (url.endsWith("/ai/status")) return json({ available, model: available ? "openai/gpt-oss-120b" : null });
    if (url.endsWith("/datasets")) return json([DS]);
    if (url.endsWith("/ai/dashboard-proposals")) return json(OUT);
    if (url.endsWith("/dashboards") && method === "POST") return json({ id: "d9", widgets: [] }, 201);
    if (url.includes("/dashboards/d9/widgets")) return json({ id: "d9" }, 201);
    return json({});
  });
  return calls;
}

const renderPage = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={["/dashboards/nova/ia"]}>
      <Routes>
        <Route path="/dashboards/nova/ia" element={<AiCreatePage />} />
        <Route path="/dashboards/:id/editar" element={<p>editor aberto</p>} />
      </Routes>
    </MemoryRouter>
  </QueryClientProvider>,
);

describe("pack (grade de 12 colunas)", () => {
  it("preenche a linha e quebra quando não cabe", () => {
    const r = pack([{ w: 3, h: 3 }, { w: 8, h: 4 }, { w: 6, h: 4 }, { w: 6, h: 4 }]);
    expect(r.map(({ x, y }) => [x, y])).toEqual([[0, 0], [3, 0], [0, 4], [6, 4]]);
  });
});

describe("Criar com IA", () => {
  beforeEach(() => useAuth.setState({ user: { permissions: { "dashboard:create": "all", "dataset:query": "all" } } as never }));
  afterEach(() => vi.restoreAllMocks());

  it("sem IA ativa explica e oferece criar sem IA", async () => {
    mockApi(false);
    renderPage();
    expect(await screen.findByText(/ainda não está ativo/)).toBeInTheDocument();
    expect(screen.getByText(/Peça a um administrador/)).toBeInTheDocument();
  });

  it("gera, deixa desmarcar e cria o painel só com os gráficos aceitos", async () => {
    const calls = mockApi();
    renderPage();
    await userEvent.selectOptions(await screen.findByLabelText("Dataset"), "ds1");
    await userEvent.type(screen.getByLabelText(/Pedido/), "pedidos e ticket");
    await userEvent.click(screen.getByRole("button", { name: "Gerar sugestões" }));
    expect(await screen.findByText("Três visões.")).toBeInTheDocument();
    expect(screen.getByText(/1 sugestão\(ões\) descartada/)).toBeInTheDocument();
    const gen = calls.find((c) => c.url.endsWith("/ai/dashboard-proposals"))!;
    expect(gen.body).toMatchObject({ dataset_id: "ds1", prompt: "pedidos e ticket", default_period: "last_12_months" });

    await userEvent.click(screen.getByLabelText(/Usar “Ticket”/));
    await userEvent.click(screen.getByRole("button", { name: "Criar painel com 2 gráficos" }));
    expect(await screen.findByText("editor aberto")).toBeInTheDocument();
    const widgets = calls.filter((c) => c.url.includes("/dashboards/d9/widgets")).map((c) => c.body);
    expect(widgets.map((w) => w.title)).toEqual(["Pedidos", "Tabela"]);
    expect(widgets.map((w) => [w.x, w.y])).toEqual([[0, 0], [3, 0]]);
    const dash = calls.find((c) => c.url.endsWith("/dashboards") && c.method === "POST")!;
    expect(dash.body).toMatchObject({ sector_id: "s1", default_period: "last_12_months", name: "pedidos e ticket" });
  });

  it("nenhum aceito: cria painel em branco", async () => {
    const calls = mockApi();
    renderPage();
    await userEvent.selectOptions(await screen.findByLabelText("Dataset"), "ds1");
    await userEvent.type(screen.getByLabelText(/Pedido/), "qualquer coisa");
    await userEvent.click(screen.getByRole("button", { name: "Gerar sugestões" }));
    await userEvent.click(await screen.findByRole("button", { name: "Nenhum" }));
    await userEvent.click(screen.getByRole("button", { name: "Começar em branco" }));
    await waitFor(() => expect(screen.getByText("editor aberto")).toBeInTheDocument());
    expect(calls.some((c) => c.url.includes("/widgets"))).toBe(false);
  });

  it("tela sem violações de acessibilidade", async () => {
    mockApi();
    const { container } = renderPage();
    await screen.findByLabelText("Dataset");
    const r = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(r.violations.map((v) => v.id)).toEqual([]);
  });
});
