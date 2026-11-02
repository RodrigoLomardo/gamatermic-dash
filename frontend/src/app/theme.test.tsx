import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeToggle } from "./ThemeToggle";
import { useColorMode } from "./theme";

describe("modo claro/escuro", () => {
  beforeEach(() => { localStorage.clear(); useColorMode.setState({ mode: "light" }); document.documentElement.dataset.mode = "light"; });

  it("alterna, aplica em <html> e persiste", async () => {
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("button", { name: "Ativar modo escuro" }));
    expect(document.documentElement.dataset.mode).toBe("dark");
    expect(localStorage.getItem("gama-color-mode")).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: "Ativar modo claro" }));
    expect(document.documentElement.dataset.mode).toBe("light");
  });
});
