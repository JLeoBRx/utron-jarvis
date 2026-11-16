import { expect, test, type Page } from '@playwright/test';
import { completeOnboarding, futureDate, trackConsoleErrors } from './helpers';

/** Garante que a página não tem rolagem horizontal (layout cabe na tela). */
async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, 'largura excedente em px').toBeLessThanOrEqual(0);
}

test('layout de celular: menu lateral em gaveta, sem rolagem horizontal', async ({ page }) => {
  const errors = trackConsoleErrors(page);
  await page.goto('/');
  await completeOnboarding(page);
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-dashboard.png', fullPage: true });

  // Menu lateral fica escondido e abre como gaveta
  await expect(page.getByRole('navigation', { name: 'Menu principal' })).toBeHidden();
  await page.getByRole('button', { name: 'Abrir menu' }).click();
  const drawer = page.getByRole('dialog', { name: 'Menu' });
  await drawer.getByRole('link', { name: 'Disciplinas' }).click();
  await expect(drawer).toBeHidden();
  await expect(page.getByRole('heading', { name: 'Disciplinas', level: 1 })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-disciplinas.png' });

  // Cadastro de prova pelo celular
  await page.getByRole('link', { name: 'Matemática 2' }).click();
  await page.getByRole('button', { name: 'Nova prova' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Nova prova' });
  await dialog.getByLabel('Nome da avaliação').fill('Avaliação 1');
  await dialog.getByLabel('Data').fill(futureDate(2));
  await dialog.getByRole('button', { name: 'Cadastrar prova' }).click();
  await expect(page.getByRole('heading', { name: 'Avaliação 1', level: 1 })).toBeVisible();
  await page.getByLabel('Adicionar conteúdos cobrados').fill('Funções');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('list', { name: 'Conteúdos da prova' }).getByRole('listitem')).toHaveCount(1);
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-prova.png', fullPage: true });

  // As abas rolam dentro do próprio contêiner, não a página
  await page.getByRole('link', { name: 'Desempenho' }).click();
  await expect(page).toHaveURL(/\/desempenho$/);
  await expectNoHorizontalScroll(page);
  expect(errors).toEqual([]);
});
