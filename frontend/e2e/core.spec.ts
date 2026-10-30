import { expect, test } from "@playwright/test";
import { ADMIN, login } from "./helpers";

test.skip(!ADMIN.password, "defina E2E_ADMIN_PASSWORD");

test("login, dashboard com dados reais e drill-down", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: /Vendas - Visão Geral/ }).click();
  await expect(page.getByText("Faturamento no mês")).toBeVisible();
  await expect(page.getByRole("img", { name: /Faturamento - últimos 12 meses/ })).toBeVisible();
  await page.getByRole("combobox", { name: "Período" }).selectOption("last_12_months");
  await expect(page.getByText(/Dados de/).first()).toBeVisible();
});

test("pareamento de TV com dois contextos, revogação devolve a TV ao pareamento", async ({ browser }) => {
  const tvCtx = await browser.newContext(); const tv = await tvCtx.newPage();
  const admCtx = await browser.newContext(); const adm = await admCtx.newPage();
  await tv.goto("/tv");
  const code = (await tv.getByLabel("Código de pareamento").textContent())!.trim();
  await login(adm);
  await adm.goto(`/admin/devices?code=${code}`);
  const name = `TV e2e ${Date.now()}`;
  await adm.getByLabel("Nome da TV").fill(name);
  await adm.getByRole("button", { name: "Aprovar" }).click();
  await expect(tv.getByText("Vendas - Visão Geral").first()).toBeVisible({ timeout: 15_000 });
  adm.once("dialog", (d) => d.accept());
  await adm.getByRole("row", { name: new RegExp(name) }).getByRole("button", { name: "Revogar" }).click();
  await expect(tv.getByText("Parear esta TV")).toBeVisible({ timeout: 30_000 });
});

test("TV offline mantém o último dado visível", async ({ browser }) => {
  const ctx = await browser.newContext(); const page = await ctx.newPage();
  await login(page);
  await page.goto("/dashboards");
  await page.getByRole("link", { name: /Vendas/ }).first().click();
  const id = page.url().split("/").pop()!;
  await page.goto(`/tv/preview/${id}`);
  await expect(page.getByText("Faturamento no mês")).toBeVisible();
  await ctx.setOffline(true);
  await expect(page.getByText("Faturamento no mês")).toBeVisible(); // último dado permanece
});

test("visual da TV em 1920x1080", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } }); const page = await ctx.newPage();
  await login(page);
  await page.goto("/dashboards");
  await page.getByRole("link", { name: /Vendas/ }).first().click();
  const id = page.url().split("/").pop()!;
  await page.goto(`/tv/preview/${id}`);
  await page.waitForTimeout(2500);
  await expect(page).toHaveScreenshot("tv-1080.png", { maxDiffPixelRatio: 0.08 });
});
