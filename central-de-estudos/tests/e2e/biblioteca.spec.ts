import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { completeOnboarding, futureDate, trackConsoleErrors } from './helpers';
import { minimalDocx, minimalPdf, notebookPng } from './fixtures/images';

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = trackConsoleErrors(page);
  await page.goto('/');
  await completeOnboarding(page);
});

test.afterEach(() => {
  expect(consoleErrors, 'erros no console do navegador').toEqual([]);
});

async function openUpload(page: Page) {
  await page.goto('/biblioteca');
  await page.getByRole('button', { name: 'Enviar arquivos' }).first().click();
  return page.getByRole('dialog', { name: 'Enviar materiais' });
}

async function createExam(page: Page, subject: string, title: string) {
  await page.goto('/provas');
  await page.getByRole('button', { name: 'Nova prova' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Nova prova' });
  await dialog.getByLabel('Disciplina').selectOption({ label: subject });
  await dialog.getByLabel('Nome da avaliação').fill(title);
  await dialog.getByLabel('Data').fill(futureDate(6));
  await dialog.getByRole('button', { name: 'Cadastrar prova' }).click();
  await expect(page.getByRole('heading', { name: title, level: 1 })).toBeVisible();
  return page.url().replace(/\/conteudos$/, '');
}

test('envia PDF, DOCX, PPTX e imagem; recusa formato inválido; filtra e busca', async ({ page }) => {
  const dialog = await openUpload(page);
  await dialog.getByLabel('Arquivos para enviar').setInputFiles([
    { name: 'Aula 3 - Cinemática.pdf', mimeType: 'application/pdf', buffer: minimalPdf('Aula 3') },
    { name: 'resumo.docx', mimeType: '', buffer: minimalDocx() },
    { name: 'slides.pptx', mimeType: 'application/octet-stream', buffer: Buffer.from('PK fake pptx') },
    { name: 'quadro.png', mimeType: 'image/png', buffer: notebookPng(300, 400) },
    { name: 'programa.exe', mimeType: 'application/x-msdownload', buffer: Buffer.from('MZ') },
  ]);
  await expect(dialog.getByText('Formato não aceito', { exact: false })).toBeVisible();
  await dialog.getByRole('button', { name: 'Remover programa.exe da lista' }).click();

  await dialog.getByRole('button', { name: 'Enviar 4 arquivos' }).click();
  await expect(dialog.getByText('Selecione a disciplina.')).toBeVisible();
  await dialog.getByLabel('Disciplina').selectOption({ label: 'Física 2' });
  await dialog.getByLabel('Categoria').selectOption('slides');
  await dialog.getByLabel('Origem').fill('Professor');
  await dialog.getByRole('button', { name: 'Enviar 4 arquivos' }).click();
  await expect(page.getByText('4 materiais enviados.')).toBeVisible();
  await expect(dialog).toBeHidden();

  const list = page.getByRole('list', { name: 'Materiais' });
  await expect(list.getByRole('listitem')).toHaveCount(4);
  await expect(list.getByText('Aula 3 - Cinemática')).toBeVisible();

  await page.getByLabel('Filtrar por tipo').selectOption('imagens');
  await expect(list.getByRole('listitem')).toHaveCount(1);
  await page.getByLabel('Filtrar por tipo').selectOption({ label: 'Todos os tipos' });
  await page.getByLabel('Buscar materiais').fill('cinematica');
  await expect(list.getByRole('listitem')).toHaveCount(1);

  // persistência após recarregar
  await page.reload();
  await expect(page.getByRole('list', { name: 'Materiais' }).getByRole('listitem')).toHaveCount(1);
});

test('visualiza PDF, DOCX e imagem; baixa o arquivo original', async ({ page }) => {
  const dialog = await openUpload(page);
  await dialog.getByLabel('Arquivos para enviar').setInputFiles([
    { name: 'apostila.pdf', mimeType: 'application/pdf', buffer: minimalPdf('Apostila') },
    { name: 'texto.docx', mimeType: '', buffer: minimalDocx('Resumo de Física: velocidade média') },
    { name: 'foto.png', mimeType: 'image/png', buffer: notebookPng(300, 400) },
  ]);
  await dialog.getByLabel('Disciplina').selectOption({ label: 'Química 2' });
  await dialog.getByRole('button', { name: 'Enviar 3 arquivos' }).click();
  await expect(page.getByText('3 materiais enviados.')).toBeVisible();

  await page.getByRole('link', { name: /apostila/ }).click();
  const pdf = page.getByTestId('pdf-viewer');
  await expect(pdf.getByText('1 página')).toBeVisible();
  await expect(pdf.locator('canvas')).toHaveCount(1);
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Baixar' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('apostila.pdf');
  expect(readFileSync((await download.path())!).subarray(0, 5).toString()).toBe('%PDF-');

  await page.goto('/biblioteca');
  await page.getByRole('link', { name: /texto/ }).click();
  await expect(page.getByTestId('docx-viewer').getByText('Resumo de Física: velocidade média')).toBeVisible();

  await page.goto('/biblioteca');
  await page.getByRole('link', { name: /foto/ }).click();
  const img = page.getByRole('img', { name: 'foto' });
  await expect(img).toBeVisible();
  expect(await img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBe(300);
});

test('substituir arquivo preserva o original nas versões anteriores', async ({ page }) => {
  const dialog = await openUpload(page);
  await dialog.getByLabel('Arquivos para enviar').setInputFiles({ name: 'lista.pdf', mimeType: 'application/pdf', buffer: minimalPdf('Lista v1') });
  await dialog.getByLabel('Disciplina').selectOption({ label: 'Matemática 2' });
  await dialog.getByRole('button', { name: 'Enviar' }).click();
  await page.getByRole('link', { name: /lista/ }).click();

  await page.getByRole('button', { name: 'Mais ações' }).click();
  await page.getByRole('menuitem', { name: 'Substituir arquivo…' }).click();
  await page.getByLabel('Novo arquivo para substituir').setInputFiles({ name: 'lista-corrigida.pdf', mimeType: 'application/pdf', buffer: minimalPdf('Lista v2') });
  const confirm = page.getByRole('dialog', { name: 'Substituir o arquivo?' });
  await expect(confirm.getByText('não será apagado')).toBeVisible();
  await confirm.getByRole('button', { name: 'Substituir' }).click();
  await expect(page.getByText(/A versão anterior foi preservada/)).toBeVisible();

  const versions = page.getByRole('list', { name: 'Versões anteriores' });
  await expect(versions.getByRole('listitem')).toHaveCount(1);
  await expect(versions.getByText('lista.pdf')).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await versions.getByRole('button', { name: 'Baixar versão 1' }).click();
  const original = readFileSync((await (await downloadPromise).path())!).toString('latin1');
  expect(original).toContain('Lista v1');
  await expect(page.getByText('lista-corrigida.pdf')).toBeVisible();
});

test('links: vídeo do YouTube incorporado e exclusão com confirmação', async ({ page }) => {
  await page.goto('/biblioteca');
  await page.getByRole('button', { name: 'Adicionar link' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Adicionar link' });
  await dialog.getByLabel('Endereço (URL)').fill('youtube.com/watch?v=abc');
  await dialog.getByLabel('Nome').fill('Vídeo-aula de velocidade média');
  await dialog.getByLabel('Disciplina').selectOption({ label: 'Física 2' });
  await dialog.getByRole('button', { name: 'Adicionar link' }).click();
  await expect(dialog.getByText(/começando com https/)).toBeVisible();
  await dialog.getByLabel('Endereço (URL)').fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ');
  await dialog.getByRole('button', { name: 'Adicionar link' }).click();
  await expect(page.getByText('Link adicionado à biblioteca.')).toBeVisible();

  await page.getByRole('link', { name: /Vídeo-aula/ }).click();
  await expect(page.locator('iframe[src*="youtube-nocookie.com/embed/dQw4w9WgXcQ"]')).toBeVisible();

  await page.getByRole('button', { name: 'Mais ações' }).click();
  await page.getByRole('menuitem', { name: 'Excluir material…' }).click();
  await page.getByRole('dialog', { name: /Excluir/ }).getByRole('button', { name: 'Excluir definitivamente' }).click();
  await expect(page.getByText('Material excluído.')).toBeVisible();
  await expect(page).toHaveURL(/\/biblioteca$/);
  await expect(page.getByText('Envie os materiais para começar a construir seu resumo.')).toBeVisible();
});

test('materiais de uma prova não aparecem em outra (sem misturar avaliações)', async ({ page }) => {
  const prova1 = await createExam(page, 'História 2', 'Avaliação 1');
  const prova2 = await createExam(page, 'História 2', 'Avaliação 2');

  await page.goto(`${prova1}/materiais`);
  await page.getByRole('button', { name: 'Enviar arquivos' }).click();
  const dialog = page.getByRole('dialog', { name: 'Enviar materiais' });
  // disciplina e prova vêm preenchidas pelo contexto
  await expect(dialog.getByLabel('Disciplina')).toHaveValue(/.+/);
  await expect(dialog.getByLabel('Prova relacionada')).not.toHaveValue('');
  await dialog.getByLabel('Arquivos para enviar').setInputFiles({ name: 'revolucao.pdf', mimeType: 'application/pdf', buffer: minimalPdf() });
  await dialog.getByRole('button', { name: 'Enviar' }).click();
  await expect(page.getByText('1 material enviado.')).toBeVisible();
  await expect(page.getByRole('list', { name: 'Materiais' }).getByText('revolucao')).toBeVisible();

  await page.goto(`${prova2}/materiais`);
  await expect(page.getByText('Envie os materiais para começar a construir seu resumo.')).toBeVisible();
  await expect(page.getByText('revolucao')).toHaveCount(0);
});
