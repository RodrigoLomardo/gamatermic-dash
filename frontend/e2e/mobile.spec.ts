import { expect, test } from "@playwright/test";
import { ADMIN, login } from "./helpers";

test.skip(!ADMIN.password, "defina E2E_ADMIN_PASSWORD");

test("dashboard utilizável em 360 px (sem rolagem horizontal)", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: /Vendas - Visão Geral/ }).click();
  await expect(page.getByText("Faturamento no mês").first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
