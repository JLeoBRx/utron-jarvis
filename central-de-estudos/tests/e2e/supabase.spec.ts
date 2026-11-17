import { expect, test } from '@playwright/test';
import { completeOnboarding, futureDate, trackConsoleErrors } from './helpers';
import { minimalPdf, notebookPng } from './fixtures/images';

/**
 * Fluxo completo no MODO NUVEM contra o Supabase local (Auth + PostgREST + RLS).
 * Requer: npm run supabase:local:up  e  E2E_SUPABASE=1.
 */
test('cadastro, onboarding, prova persistida no banco e novo login', async ({ page }) => {
  const errors = trackConsoleErrors(page);
  // Nenhuma requisição pode falhar por falta de permissão (401/403) ou erro do servidor (5xx).
  const failed: string[] = [];
  page.on('response', (res) => {
    const status = res.status();
    if (status === 401 || status === 403 || status >= 500) failed.push(`${status} ${res.request().method()} ${res.url()}`);
  });
  const email = `e2e-${Date.now()}@central.local`;
  const password = 'senha-forte-123';

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Entrar na Central de Estudos' })).toBeVisible();
  await page.getByRole('radio', { name: 'Criar conta' }).click();
  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Senha').fill('curta');
  await page.getByRole('button', { name: 'Criar conta' }).last().click();
  await expect(page.getByText('A senha precisa ter pelo menos 8 caracteres.')).toBeVisible();
  await page.getByLabel('Senha').fill(password);
  await page.getByRole('button', { name: 'Criar conta' }).last().click();

  await completeOnboarding(page, { year: '2026' });
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByText('Modo local')).toHaveCount(0);

  await page.goto('/disciplinas');
  await page.getByRole('link', { name: 'Sistemas Digitais' }).click();
  await page.getByRole('button', { name: 'Nova prova' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Nova prova' });
  await dialog.getByLabel('Nome da avaliação').fill('Avaliação 3');
  await dialog.getByLabel('Data').fill(futureDate(10));
  await dialog.getByRole('button', { name: 'Cadastrar prova' }).click();
  await expect(page.getByRole('heading', { name: 'Avaliação 3', level: 1 })).toBeVisible();
  await page.getByLabel('Adicionar conteúdos cobrados').fill('Flip-flops');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('list', { name: 'Conteúdos da prova' }).getByRole('listitem')).toHaveCount(1);

  // Biblioteca na nuvem: arquivo no bucket privado do Supabase Storage
  await page.getByRole('link', { name: /^Materiais/ }).click();
  await page.getByRole('button', { name: 'Enviar arquivos' }).click();
  const upload = page.getByRole('dialog', { name: 'Enviar materiais' });
  await upload.getByLabel('Arquivos para enviar').setInputFiles({ name: 'contadores.pdf', mimeType: 'application/pdf', buffer: minimalPdf('Contadores') });
  await upload.getByRole('button', { name: 'Enviar' }).click();
  await expect(page.getByText('1 material enviado.')).toBeVisible();
  await page.getByRole('list', { name: 'Materiais' }).getByText('contadores').click();
  await expect(page.getByTestId('pdf-viewer').locator('canvas')).toHaveCount(1);

  // Scanner na nuvem: fotos originais + tratadas no Storage
  await page.goto('/scanner');
  await page.getByLabel('Escolher fotos da galeria').setInputFiles({ name: 'pagina.png', mimeType: 'image/png', buffer: notebookPng(600, 800) });
  await expect(page.getByText('1 página pronta')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: /Revisar e salvar/ }).click();
  await page.getByLabel('Disciplina').selectOption({ label: 'Sistemas Digitais' });
  await page.getByLabel('Nome ou assunto do conteúdo').fill('Flip-flops JK');
  await page.getByRole('button', { name: 'Salvar caderno' }).click();
  await expect(page.getByRole('heading', { name: 'Caderno salvo!' })).toBeVisible({ timeout: 60_000 });
  await page.getByRole('link', { name: 'Ver o caderno salvo' }).click();
  await expect(page.getByTestId('scan-page').getByRole('img')).toBeVisible();

  // Sair e entrar novamente: dados vêm do banco
  await page.getByRole('button', { name: 'Sair da conta' }).click();
  await expect(page.getByRole('heading', { name: 'Entrar na Central de Estudos' })).toBeVisible();
  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Senha').fill('senha-errada-1');
  await page.getByRole('button', { name: 'Entrar' }).last().click();
  await expect(page.getByText('E-mail ou senha incorretos.')).toBeVisible();
  await page.getByLabel('Senha').fill(password);
  await page.getByRole('button', { name: 'Entrar' }).last().click();

  await expect(page.getByRole('link', { name: /^Disciplinas 20/ })).toBeVisible();
  await page.goto('/provas');
  await expect(page.getByRole('main').getByRole('link', { name: /Avaliação 3/ })).toBeVisible();
  await page.goto('/biblioteca');
  await expect(page.getByRole('list', { name: 'Materiais' }).getByRole('listitem')).toHaveCount(2);
  await page.getByRole('link', { name: /Flip-flops JK/ }).click();
  await expect(page.getByTestId('scan-page').getByRole('img')).toBeVisible();
  // Login com credenciais inválidas gera um 400 esperado no console; os demais erros não são aceitos.
  expect(errors.filter((e) => !e.includes('400'))).toEqual([]);
  expect(failed).toEqual([]);
});
