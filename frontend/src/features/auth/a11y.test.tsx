import { render } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router-dom";
import { WidgetCard } from "../widgets/WidgetCard";
import { LoginPage } from "./AuthPages";

async function violations(container: HTMLElement) {
  const r = await axe.run(container, { rules: { "color-contrast": { enabled: false } } }); // jsdom nao calcula contraste
  return r.violations.map((v) => `${v.id}: ${v.nodes.length}`);
}

describe("acessibilidade (axe)", () => {
  it("login sem violações", async () => {
    const { container } = render(<MemoryRouter><LoginPage /></MemoryRouter>);
    expect(await violations(container)).toEqual([]);
  });
  it("tabela de widget sem violações", async () => {
    const { container } = render(<WidgetCard widget={{ id: "w", type: "table", title: "Top", x: 0, y: 0, w: 4, h: 3, dataset_id: "d", query_config: {}, viz_config: { columns: [{ field: "a", label: "A" }] }, follows_global_period: true } as never}
      result={{ widget_id: "w", type: "table", data: [{ a: "1" }], previous: null, dataset_version: 1, data_as_of: null, generated_at: null, period: null, error: null }} />);
    expect(await violations(container)).toEqual([]);
  });
});
