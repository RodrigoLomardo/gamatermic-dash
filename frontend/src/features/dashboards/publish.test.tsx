import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PublishControl } from "./PublishControl";

const wrap = (ui: JSX.Element) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

describe("PublishControl", () => {
  afterEach(() => vi.restoreAllMocks());

  it("painel fora do ar: editor vê 'Lançar' e não vê 'Copiar link'", () => {
    wrap(<PublishControl id="d1" name="Vendas" status="offline" canEdit />);
    expect(screen.getByText("Fora do ar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Lançar/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Copiar link/ })).toBeNull();
  });

  it("quem não edita não vê botões de lançar/retirar", () => {
    wrap(<PublishControl id="d1" name="Vendas" status="published" canEdit={false} />);
    expect(screen.getByText("No ar")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tirar do ar|Lançar/ })).toBeNull();
  });

  it("copia o link interno do painel e exige confirmação para tirar do ar", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    wrap(<PublishControl id="d1" name="Vendas" status="published" canEdit />);
    await userEvent.click(screen.getByRole("button", { name: /Copiar link de Vendas/ }));
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/dashboards/d1`);
    await userEvent.click(screen.getByRole("button", { name: /Copiar link de visualização de Vendas/ }));
    expect(writeText).toHaveBeenLastCalledWith(`${window.location.origin}/tv/painel/d1`);
    await userEvent.click(screen.getByRole("button", { name: "Tirar do ar" }));
    expect(fetchMock).not.toHaveBeenCalled(); // so confirma no modal
    await userEvent.click(screen.getAllByRole("button", { name: "Tirar do ar" }).at(-1)!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0][0])).toContain("/dashboards/d1/publication");
  });
});
