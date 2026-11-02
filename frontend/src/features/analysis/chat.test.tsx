import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { ChatPanel, applyToView } from "./ChatPanel";
import { EMPTY_VIEW } from "./state";

const post = vi.fn();
vi.mock("@/shared/api/http", async (orig) => ({ ...(await orig<typeof import("@/shared/api/http")>()), post: (...a: unknown[]) => post(...a), get: vi.fn() }));
vi.mock("@/app/auth", () => ({ useAuth: (sel: (s: { can: (p: string) => boolean }) => unknown) => sel({ can: () => false }) }));

const wrap = (ui: React.ReactNode) => <QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>{ui}</QueryClientProvider>;
const out = (over = {}) => ({ action: "explain_unsupported", message: "Projeção não é calculada.", interpretation: [], notes: [], suggestions: ["Faturamento por mês?"], summary: "", widget: null, result: null, apply: null, ...over });

beforeEach(() => { post.mockReset(); sessionStorage.clear(); });

describe("applyToView", () => {
  it("troca o filtro manual do mesmo campo, mantém drill e aplica o período", () => {
    const v = { ...EMPTY_VIEW, filters: [{ field: "cliente", op: "eq" as const, value: "A", src: "manual" as const }, { field: "segmento", op: "eq" as const, value: "S", src: "drill" as const }] };
    const n = applyToView(v, { period: { mode: "absolute", from: "2026-01-01", to: "2026-03-31" }, filters: [{ field: "cliente", op: "in", value: ["B", "C"] }] });
    expect(n.filters.map((f) => [f.field, f.src, f.value])).toEqual([["segmento", "drill", "S"], ["cliente", "manual", ["B", "C"]]]);
    expect(n.period).toEqual({ mode: "absolute", from: "2026-01-01", to: "2026-03-31" });
  });
  it("sem período na resposta mantém o atual", () => {
    const v = { ...EMPTY_VIEW, period: { mode: "relative" as const, preset: "this_year" } };
    expect(applyToView(v, { period: null, filters: [] }).period).toEqual(v.period);
  });
});

describe("ChatPanel", () => {
  it("envia a pergunta com histórico e contexto da tela e mostra a resposta com sugestões", async () => {
    post.mockResolvedValueOnce(out());
    const { container } = render(wrap(<ChatPanel dashId="d1" view={{ ...EMPTY_VIEW, filters: [{ field: "cliente", op: "eq", value: "ACME", src: "manual" }] }} onApply={() => {}} onClose={() => {}} />));
    await userEvent.type(screen.getByLabelText("Sua pergunta"), "projeção até o fim do ano{Enter}");
    expect(await screen.findByText("Projeção não é calculada.")).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith("/dashboards/d1/analysis/chat", { message: "projeção até o fim do ano", history: [], view: { period: null, filters: [{ field: "cliente", op: "eq", value: "ACME" }] } });
    // a sugestão vira a próxima pergunta, e a resposta anterior entra no histórico
    post.mockResolvedValueOnce(out({ message: "Ok", suggestions: [] }));
    await userEvent.click(screen.getByRole("button", { name: "Faturamento por mês?" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect((post.mock.calls[1][1] as { history: unknown[] }).history).toHaveLength(2);
    expect(await axe.run(container, { rules: { "color-contrast": { enabled: false } } }).then((r) => r.violations.map((v) => v.id))).toEqual([]);
  });
  it("erro do servidor vira mensagem no chat, sem derrubar a tela", async () => {
    post.mockRejectedValueOnce(new Error("A Groq respondeu com erro (503)."));
    render(wrap(<ChatPanel dashId="d1" view={EMPTY_VIEW} onApply={() => {}} onClose={() => {}} />));
    await userEvent.type(screen.getByLabelText("Sua pergunta"), "oi{Enter}");
    expect(await screen.findByText("A Groq respondeu com erro (503).")).toBeInTheDocument();
  });
});
