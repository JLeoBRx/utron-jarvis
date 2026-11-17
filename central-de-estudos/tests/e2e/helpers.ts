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

/**
 * Data futura (YYYY-MM-DD) a N dias de "hoje" no fuso do NAVEGADOR dos testes
 * (America/Sao_Paulo, ver playwright.config.ts) — não no fuso do servidor.
 */
export const TEST_TIMEZONE = 'America/Sao_Paulo';

export function futureDate(days: number): string {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: TEST_TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const [y, m, d] = today.split('-').map(Number);
  return new Date(Date.UTC(y!, m! - 1, d! + days)).toISOString().slice(0, 10);
}
