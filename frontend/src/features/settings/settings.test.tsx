import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsPage } from "./SettingsPage";

const BASE = { enabled: false, analysis_chat: true, model: "openai/gpt-oss-120b", updated_at: null,
  models: [{ id: "openai/gpt-oss-120b", label: "GPT-OSS 120B" }, { id: "openai/gpt-oss-20b", label: "GPT-OSS 20B" }] };

describe("Configurações → IA", () => {
  afterEach(() => vi.restoreAllMocks());

  it("envia a chave só ao salvar, nunca a exibe de volta e testa a conexão", async () => {
    const sent: any[] = [];
    let state = { ...BASE, api_key: { configured: false, last4: null as string | null } };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const json = (o: unknown) => new Response(JSON.stringify(o), { status: 200, headers: { "Content-Type": "application/json" } });
      if (url.endsWith("/settings/ai") && init?.method === "PUT") {
        const b = JSON.parse(String(init.body)); sent.push(b);
        state = { ...state, enabled: b.enabled, model: b.model, api_key: { configured: true, last4: "WXYZ" } };
        return json(state);
      }
      if (url.endsWith("/settings/ai/test")) return json({ ok: true, model: state.model, model_available: true, latency_ms: 123, error: null });
      return json(state);
    });
    render(<QueryClientProvider client={new QueryClient()}><SettingsPage /></QueryClientProvider>);
    expect(await screen.findByRole("tab", { name: "IA (Groq)" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("button", { name: "Testar conexão" })).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Chave de API"), "gsk_abcdefghijklmnopqrstWXYZ");
    await userEvent.selectOptions(screen.getByLabelText("Modelo"), "openai/gpt-oss-20b");
    await userEvent.click(screen.getByLabelText(/IA ativa/));
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]).toEqual({ enabled: true, model: "openai/gpt-oss-20b", api_key: "gsk_abcdefghijklmnopqrstWXYZ", analysis_chat: true });
    expect(await screen.findByText(/termina em WXYZ/)).toBeInTheDocument();
    expect(screen.getByLabelText("Chave de API")).toHaveValue(""); // campo limpo apos salvar

    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(sent).toHaveLength(2));
    expect(sent[1].api_key).toBeUndefined(); // em branco = mantem a chave

    await userEvent.click(screen.getByRole("button", { name: "Testar conexão" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Conexão OK com openai/gpt-oss-20b (123 ms)");
  });
});
