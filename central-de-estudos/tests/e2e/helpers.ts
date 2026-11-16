import { expect, type Page } from '@playwright/test';

/** Falha o teste se a página registrar erros no console. */
export function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

/** Conclui o onboarding (ano letivo + 20 disciplinas oficiais). */
export async function completeOnboarding(page: Page, opts: { name?: string; year?: string } = {}) {
  await expect(page.getByRole('heading', { name: 'Bem-vindo à Central de Estudos' })).toBeVisible();
  if (opts.name) await page.getByLabel('Como você quer ser chamado(a)?').fill(opts.name);
  await page.getByLabel('Ano letivo').fill(opts.year ?? '2026');
  await page.getByRole('button', { name: 'Começar' }).click();
  await expect(page.getByText('20 disciplinas cadastradas')).toBeVisible();
}

/** Data futura (YYYY-MM-DD) a N dias de hoje, no fuso local. */
export function futureDate(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
