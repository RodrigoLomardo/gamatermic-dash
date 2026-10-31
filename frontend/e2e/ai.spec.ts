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
  await expect(page.getByRole("button", { name: "Nova dashboard" })).toBeVisible();
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
  await expect(page.getByText("1 gráfico(s) adicionado(s) ao painel.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Editar" })).toHaveCount(1);

  // de novo: o que ja esta no painel nao volta como sugestao; agora o dataset do painel vem pre-selecionado
  await page.getByRole("button", { name: "Gráficos com IA" }).click();
  await expect(dialog.getByRole("option", { name: /Vendas \(pedidos\) \(do painel\)/ })).toBeAttached();
  await dialog.getByLabel(/Que gráficos/).fill("gráficos de faturamento");
  await dialog.getByRole("button", { name: "Gerar gráficos" }).click();
  await expect(dialog.getByRole("checkbox", { name: /^Usar/ })).toHaveCount(3);
  await expect(dialog.getByLabel("Usar “Valor por mês”")).toHaveCount(0);
  await dialog.getByText(/descartada\(s\)/).click();
  await expect(dialog.getByText("Valor por mês: Já existe um gráfico igual no painel.")).toBeVisible();
});
