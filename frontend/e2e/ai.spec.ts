import { expect, test } from "@playwright/test";
import { ADMIN, login } from "./helpers";

// Exige a Groq falsa (e2e/fake-groq.mjs) e a API com GAMA_GROQ_BASE_URL apontando para ela. Nunca chama a Groq real.
test.skip(!ADMIN.password || !process.env.E2E_FAKE_GROQ, "defina E2E_ADMIN_PASSWORD e E2E_FAKE_GROQ=1 (ver README)");

test("configura a IA, gera sugestões e cria o painel só com as aceitas", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Configurações" }).click();
  await page.getByLabel("Chave de API").fill("gsk_e2e_chave_de_teste_0001");
  await page.getByLabel(/IA ativa/).check();
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText(/termina em 0001/)).toBeVisible();
  await expect(page.getByLabel("Chave de API")).toHaveValue("");
  await page.getByRole("button", { name: "Testar conexão" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Conexão OK" })).toBeVisible();

  await page.getByRole("link", { name: "Dashboards" }).click();
  await page.getByRole("button", { name: "Criar com IA" }).click();
  const vendas = await page.getByRole("option", { name: /^Vendas \(pedidos\)/ }).getAttribute("value");
  await page.getByLabel("Dataset", { exact: true }).selectOption(vendas!);
  await page.getByLabel(/Pedido/).fill("faturamento por mês e top clientes");
  await page.getByRole("button", { name: "Gerar sugestões" }).click();
  await expect(page.getByText("Sugestões para Vendas (pedidos).")).toBeVisible();
  await expect(page.getByText(/1 sugestão\(ões\) descartada/)).toBeVisible(); // campo inventado nao passa
  const boxes = page.getByRole("checkbox", { name: /^Usar/ });
  await expect(boxes).toHaveCount(4);
  await page.getByLabel("Usar “Registros”").uncheck();
  const name = `Painel IA ${Date.now()}`;
  await page.getByLabel("Nome do painel").fill(name);
  await page.getByRole("button", { name: "Criar painel com 3 gráficos" }).click();
  await expect(page.getByRole("heading", { name: `Editor — ${name}` })).toBeVisible();
  await expect(page.getByRole("button", { name: "Editar" })).toHaveCount(3);
});

test("lista de dashboards oferece criar com e sem IA", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Dashboards" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Novo dashboard" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Criar com IA" })).toBeVisible();
});

test("no editor, gera gráficos com IA para o painel sem repetir os existentes", async ({ page }) => {
  await login(page);
  // painel novo a cada execucao: o teste nao depende do que rodadas anteriores deixaram
  await page.goto("/dashboards/nova");
  await page.getByLabel("Nome").fill(`IA no editor ${Date.now()}`);
  await page.getByRole("button", { name: "Criar e editar" }).click();
  await expect(page.getByRole("heading", { name: /^Editor —/ })).toBeVisible();
  const dialog = page.getByRole("dialog", { name: "Gráficos com IA" });
  const generate = async () => {
    await page.getByRole("button", { name: "Gráficos com IA" }).click();
    const vendas = await dialog.getByRole("option", { name: /^Vendas \(pedidos\)/ }).getAttribute("value");
    await dialog.getByLabel("Dados").selectOption(vendas!);
    await dialog.getByLabel(/Que gráficos/).fill("gráficos de faturamento");
    await dialog.getByRole("button", { name: "Gerar gráficos" }).click();
    await expect(dialog.getByRole("button", { name: "Nenhum" })).toBeVisible();
  };

  await generate();
  await expect(dialog.getByRole("checkbox", { name: /^Usar/ })).toHaveCount(4);
  await dialog.getByRole("button", { name: "Nenhum" }).click();
  await dialog.getByLabel("Usar “Valor por mês”").check();
  await dialog.getByRole("button", { name: "Adicionar 1 gráfico ao painel" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("1 gráfico(s) adicionado(s) no painel.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Editar" })).toHaveCount(1);

  // de novo: o que ja esta no painel nao volta como sugestao, e a IA propoe abrir espaco ao lado do grafico largo
  await page.getByRole("button", { name: "Gráficos com IA" }).click();
  await expect(dialog.getByRole("option", { name: /Vendas \(pedidos\) \(do painel\)/ })).toBeAttached();
  await dialog.getByLabel(/Que gráficos/).fill("gráficos de faturamento");
  await dialog.getByRole("button", { name: "Gerar gráficos" }).click();
  await expect(dialog.getByRole("checkbox", { name: /^Usar/ })).toHaveCount(3);
  await expect(dialog.getByLabel("Usar “Valor por mês”")).toHaveCount(0);
  await dialog.getByText(/descartada\(s\)/).click();
  await expect(dialog.getByText("Valor por mês: Mostra a mesma informação de “Valor por mês”.")).toBeVisible();
  await expect(dialog.getByText("Mudanças sugeridas no layout")).toBeVisible();
  await expect(dialog.getByText("8×4 em (0, 0) → 4×4 em (0, 0)")).toBeVisible();
  await dialog.getByRole("button", { name: "Nenhum" }).click();
  await dialog.getByRole("checkbox", { name: /^Usar “Top / }).check();
  await dialog.getByRole("button", { name: "Adicionar 1 gráfico e ajustar 1" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("1 gráfico(s) adicionado(s) e 1 ajustado(s) no painel.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Editar" })).toHaveCount(2);
});

test("no editor, redimensionar até abaixo do tamanho completo mostra a visão compacta e salva sozinho", async ({ page }) => {
  await login(page);
  await page.goto("/dashboards/nova");
  await page.getByLabel("Nome").fill(`Redimensionar ${Date.now()}`);
  await page.getByRole("button", { name: "Criar e editar" }).click();
  await page.getByRole("button", { name: "+ Widget" }).click();
  const modal = page.getByRole("dialog", { name: "Novo widget" });
  await modal.getByLabel("Tipo").selectOption("bar");
  await modal.getByRole("button", { name: "Salvar widget" }).click();
  const card = page.locator(".react-grid-item").first();
  await expect(card.locator("article")).toHaveAttribute("data-view", "full");
  const handle = card.locator(".react-resizable-handle");
  const hb = (await handle.boundingBox())!;
  const cb = (await card.boundingBox())!;
  // puxa o canto ate ~2x2 (coluna ~ largura/6 do card de 6 colunas)
  await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
  await page.mouse.down();
  await page.mouse.move(cb.x + cb.width / 3, cb.y + 150, { steps: 12 });
  await expect(card.locator("article")).toHaveAttribute("data-view", "compact"); // troca ao vivo, antes de soltar
  await page.mouse.up();
  await expect(page.getByRole("status").filter({ hasText: "Layout salvo" })).toBeVisible();
  await page.reload();
  await expect(page.locator(".react-grid-item").first().locator("article")).toHaveAttribute("data-view", "compact");
  await expect(page.getByText("compacta", { exact: true })).toBeVisible();
});
