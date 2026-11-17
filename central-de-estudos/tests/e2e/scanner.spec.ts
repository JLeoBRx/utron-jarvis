import { expect, test, type Page } from '@playwright/test';
import { completeOnboarding, expectCropAlignedWithImage, futureDate, trackConsoleErrors } from './helpers';
import { notebookPng } from './fixtures/images';

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = trackConsoleErrors(page);
  await page.goto('/');
  await completeOnboarding(page);
});

test.afterEach(() => {
  expect(consoleErrors, 'erros no console do navegador').toEqual([]);
});

const photo = (name: string, variant: number) => ({ name, mimeType: 'image/png', buffer: notebookPng(600, 800, variant) });

async function pagesInOrder(page: Page): Promise<string[]> {
  // endereço (blob:) da prévia identifica cada página independentemente da posição
  return page.getByTestId('scanner-page').evaluateAll((items) => items.map((li) => li.querySelector('img')?.getAttribute('src') ?? ''));
}

test('fluxo completo pela galeria: editar, reordenar, excluir, adicionar, organizar e salvar', async ({ page }) => {
  // começa dentro de uma prova → disciplina e prova preenchidas automaticamente
  await page.goto('/provas');
  await page.getByRole('button', { name: 'Nova prova' }).first().click();
  const examDialog = page.getByRole('dialog', { name: 'Nova prova' });
  await examDialog.getByLabel('Disciplina').selectOption({ label: 'Física 2' });
  await examDialog.getByLabel('Nome da avaliação').fill('Avaliação 2');
  await examDialog.getByLabel('Data').fill(futureDate(4));
  await examDialog.getByRole('button', { name: 'Cadastrar prova' }).click();
  await page.getByRole('link', { name: /^Materiais/ }).click();
  await page.getByRole('link', { name: 'Fotografar caderno' }).click();
  await expect(page).toHaveURL(/\/scanner\?disciplina=.+&prova=.+/);

  await page.getByLabel('Escolher fotos da galeria').setInputFiles([photo('p1.png', 0), photo('p2.png', 1), photo('p3.png', 2)]);
  await expect(page.getByText('3 páginas prontas')).toBeVisible({ timeout: 30_000 });
  const cards = page.getByTestId('scanner-page');
  await expect(cards).toHaveCount(3);
  // detecção automática da folha aplicou o recorte
  await expect(cards.getByText('recortada')).toHaveCount(3);

  // editar a página 1: girar, P&B e brilho
  await page.getByRole('button', { name: 'Editar página 1' }).first().click();
  const editor = page.getByRole('dialog', { name: 'Editar página 1 de 3' });
  await expect(editor.getByTestId('editor-result')).toBeVisible({ timeout: 15_000 });
  await editor.getByRole('button', { name: 'Girar para a direita' }).click();
  await editor.getByRole('radio', { name: 'P&B' }).click();
  await editor.getByRole('radio', { name: 'Recorte' }).click();
  await expect(editor.getByTestId('crop-overlay')).toBeVisible();
  await expectCropAlignedWithImage(page);
  const handle = editor.getByRole('slider', { name: 'Canto superior esquerdo' });
  await handle.focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowDown');
  await editor.getByRole('button', { name: 'Aplicar' }).click();
  await expect(page.getByText('3 páginas prontas')).toBeVisible({ timeout: 15_000 });

  // reordenar: página 2 vai para a primeira posição
  const before = await pagesInOrder(page);
  await page.getByRole('button', { name: 'Mover página 2 para antes' }).click();
  await expect.poll(() => pagesInOrder(page)).toEqual([before[1], before[0], before[2]]);

  // excluir a página 3 e adicionar outra
  await page.getByRole('button', { name: 'Excluir página 3' }).click();
  await page.getByRole('dialog', { name: 'Excluir esta página?' }).getByRole('button', { name: 'Excluir página' }).click();
  await expect(cards).toHaveCount(2);
  await page.getByLabel('Escolher fotos da galeria').setInputFiles([photo('p4.png', 3)]);
  await expect(page.getByText('3 páginas prontas')).toBeVisible({ timeout: 30_000 });

  // revisar: todas as páginas visíveis + organização já preenchida
  await page.getByRole('button', { name: /Revisar e salvar/ }).click();
  await expect(page.getByTestId('review-page')).toHaveCount(3);
  await expect(page.getByLabel('Disciplina')).not.toHaveValue('');
  await expect(page.getByLabel('Prova relacionada')).not.toHaveValue('');
  await page.getByLabel('Nome ou assunto do conteúdo').fill('Cinemática e velocidade média');
  await page.getByRole('button', { name: 'Salvar caderno' }).click();

  await expect(page.getByRole('heading', { name: 'Caderno salvo!' })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText('3 páginas guardadas')).toBeVisible();
  await page.getByRole('link', { name: 'Ver o caderno salvo' }).click();

  // visualização: páginas na ordem, original preservado, status da IA honesto
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Cinemática e velocidade média');
  await expect(page.getByText('Aguardando leitura por IA')).toBeVisible();
  const pages = page.getByTestId('scan-page');
  await expect(pages).toHaveCount(3);
  await expect(pages.first().getByRole('img')).toBeVisible();
  await page.getByRole('radio', { name: 'Original' }).click();
  await expect(pages.first().getByRole('img', { name: 'Página 1 (original)' })).toBeVisible();
  const originalWidth = await pages.first().getByRole('img').evaluate((img: HTMLImageElement) => img.naturalWidth);
  expect(originalWidth).toBe(600); // a foto original é a enviada, intocada

  // persistência + aparece na aba Materiais da prova
  await page.reload();
  await expect(page.getByTestId('scan-page')).toHaveCount(3);
  await page.getByRole('link', { name: 'Avaliação 2' }).click();
  await expect(page.getByRole('list', { name: 'Materiais' }).getByText('Cinemática e velocidade média')).toBeVisible();
});

test('rascunho: fotos não se perdem ao fechar ou recarregar a página', async ({ page }) => {
  await page.goto('/scanner');
  await page.getByLabel('Escolher fotos da galeria').setInputFiles([photo('a.png', 0), photo('b.png', 1)]);
  await expect(page.getByText('2 páginas prontas')).toBeVisible({ timeout: 30_000 });
  await page.reload();
  await expect(page.getByText('Rascunho recuperado:')).toBeVisible();
  await expect(page.getByTestId('scanner-page')).toHaveCount(2);
  await expect(page.getByText('2 páginas prontas')).toBeVisible({ timeout: 30_000 });

  await page.getByRole('button', { name: 'Descartar rascunho' }).click();
  await page.getByRole('dialog', { name: 'Descartar o rascunho?' }).getByRole('button', { name: 'Descartar' }).click();
  await expect(page.getByRole('button', { name: 'Abrir câmera' })).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('scanner-page')).toHaveCount(0);
});

test('exige disciplina antes de salvar e recusa arquivos que não são imagem', async ({ page }) => {
  await page.goto('/scanner');
  await page.getByLabel('Escolher fotos da galeria').setInputFiles([
    { name: 'documento.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') },
    photo('ok.png', 0),
  ]);
  await expect(page.getByText(/documento\.pdf: Formato não aceito/)).toBeVisible();
  await expect(page.getByText('1 página pronta')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: /Revisar e salvar/ }).click();
  await page.getByRole('button', { name: 'Salvar caderno' }).click();
  await expect(page.getByText('Selecione a disciplina.')).toBeVisible();
});
