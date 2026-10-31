import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth } from "@/app/auth";
import type { Widget } from "../widgets/types";
import { AiWidgetsPanel, mainDataset } from "./AiWidgetsPanel";

const DS = [{ id: "a", name: "Propostas" }, { id: "v", name: "Vendas" }] as never[];
const W = (id: string, ds: string, y = 0, h = 3) => ({ id, dataset_id: ds, type: "kpi", title: id, x: 0, y, w: 3, h, query_config: {}, viz_config: {}, follows_global_period: true }) as Widget;
const P = (id: string, title: string, w = 6, h = 4) => ({
  id, type: "kpi", title, rationale: "r", dataset_id: "v", query_config: { measures: [{ agg: "count", alias: "qtd" }] }, viz_config: { format: "integer" },
  follows_global_period: true, w, h, preview: { widget_id: id, type: "kpi", data: [{ qtd: "3" }], previous: null, dataset_version: 1, data_as_of: null, generated_at: null, period: null, error: null },
});

describe("mainDataset", () => {
  it("escolhe o dataset mais usado pelos widgets do painel", () => {
    expect(mainDataset([W("1", "v"), W("2", "v"), W("3", "a")], DS as never)).toBe("v");
    expect(mainDataset([], DS as never)).toBe("a");
  });
});

describe("Gráficos com IA no editor", () => {
  beforeEach(() => useAuth.setState({ user: { permissions: { "dataset:query": "all" } } as never }));
  afterEach(() => vi.restoreAllMocks());

  it("gera com o dataset do painel, não repete e adiciona só os marcados abaixo dos atuais", async () => {
    const calls: { url: string; body: any; headers: any }[] = [];
    let version = 7;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined, headers: init?.headers });
      const json = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json" } });
      if (url.endsWith("/ai/status")) return json({ available: true, model: "m" });
      if (url.endsWith("/ai/dashboard-proposals")) return json({ explanation: "", proposals: [P("p1", "Novo A"), P("p2", "Novo B")], discarded: [{ title: "Faturamento", reason: "Já existe um gráfico igual no painel." }], layout_changes: [], usage: { model: "m", prompt_tokens: 1, completion_tokens: 1 } });
      if (url.includes("/dashboards/d1/widgets")) { version += 1; return json({ id: "d1", version, widgets: [] }, 201); }
      return json({});
    });
    const onAdded = vi.fn();
    render(<QueryClientProvider client={new QueryClient()}>
      <AiWidgetsPanel dashboardId="d1" widgets={[W("w1", "v", 0, 3), W("w2", "v", 3, 4)]} version={7} defaultPeriod="this_month" datasets={DS as never} onAdded={onAdded} onConflict={() => {}} />
    </QueryClientProvider>);
    expect(await screen.findByLabelText("Dados")).toHaveValue("v");
    await userEvent.type(screen.getByLabelText(/Que gráficos/), "mais gráficos");
    await userEvent.click(screen.getByRole("button", { name: "Gerar gráficos" }));
    expect(await screen.findByText(/1 sugestão\(ões\) descartada/)).toBeInTheDocument();
    const gen = calls.find((c) => c.url.endsWith("/ai/dashboard-proposals"))!;
    expect(gen.body).toMatchObject({ dataset_id: "v", dashboard_id: "d1", default_period: "this_month" });

    await userEvent.click(screen.getByLabelText("Usar “Novo A”"));
    await userEvent.click(screen.getByRole("button", { name: "Adicionar 1 gráfico ao painel" }));
    await waitFor(() => expect(onAdded).toHaveBeenCalledWith(expect.objectContaining({ version: 8 }), 1, 0));
    const added = calls.filter((c) => c.url.includes("/widgets"));
    expect(added.map((c) => c.body.title)).toEqual(["Novo B"]);
    expect(added[0].body).toMatchObject({ x: 0, y: 7 }); // abaixo do ultimo widget (y 3 + h 4)
    expect(added[0].headers["If-Match"]).toBe('"7"');
  });

  it("mostra as mudanças de layout sugeridas, a prévia, e aplica o layout antes de inserir o novo ao lado", async () => {
    const calls: { url: string; method: string; body: any }[] = [];
    let version = 3;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input); const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const json = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json" } });
      if (url.endsWith("/ai/status")) return json({ available: true, model: "m" });
      if (url.endsWith("/ai/dashboard-proposals")) return json({ explanation: "", discarded: [], usage: { model: "m", prompt_tokens: 1, completion_tokens: 1 },
        proposals: [{ ...P("p1", "Por projeto"), x: 6, y: 0, w: 6, h: 4 }],
        layout_changes: [{ widget_id: "big", title: "Evolução", type: "line", before: { x: 0, y: 0, w: 12, h: 4 }, after: { x: 0, y: 0, w: 6, h: 4 }, reason: "abre espaço ao lado", compact: false }] });
      version += 1;
      return json({ id: "d1", version, widgets: [] }, method === "POST" ? 201 : 200);
    });
    const onAdded = vi.fn();
    render(<QueryClientProvider client={new QueryClient()}>
      <AiWidgetsPanel dashboardId="d1" widgets={[{ ...W("big", "v", 0, 4), type: "line", w: 12 }]} version={3} defaultPeriod="this_month" datasets={DS as never} onAdded={onAdded} onConflict={() => {}} />
    </QueryClientProvider>);
    await userEvent.type(await screen.findByLabelText(/Que gráficos/), "barras ao lado");
    await userEvent.click(screen.getByRole("button", { name: "Gerar gráficos" }));
    expect(await screen.findByText("Mudanças sugeridas no layout")).toBeInTheDocument();
    expect(screen.getByText("abre espaço ao lado")).toBeInTheDocument();
    expect(screen.getByText(/1 gráfico\(s\) novo\(s\), 1 ajustado/)).toBeInTheDocument();
    // recusar a mudanca: o novo desce para nao sobrepor e nada no painel muda
    await userEvent.click(screen.getByLabelText(/Ajustar “Evolução”/));
    expect(screen.getByText(/1 gráfico\(s\) novo\(s\), 0 ajustado/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/Ajustar “Evolução”/));
    await userEvent.click(screen.getByRole("button", { name: "Adicionar 1 gráfico e ajustar 1" }));
    await waitFor(() => expect(onAdded).toHaveBeenCalledWith(expect.anything(), 1, 1));
    const writes = calls.filter((c) => c.url.includes("/dashboards/d1/"));
    expect(writes.map((c) => c.method)).toEqual(["PUT", "POST"]);
    expect(writes[0].body.items).toEqual([{ id: "big", x: 0, y: 0, w: 6, h: 4 }]);
    expect(writes[1].body).toMatchObject({ title: "Por projeto", x: 6, y: 0, w: 6, h: 4 });
  });
});

