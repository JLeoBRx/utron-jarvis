import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { completeOnboarding, futureDate, trackConsoleErrors } from './helpers';

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = trackConsoleErrors(page);
  await page.goto('/');
});

test.afterEach(() => {
  expect(consoleErrors, 'erros no console do navegador').toEqual([]);
});

async function createExam(page: Page, subject: string, title: string, days = 5) {
  await page.goto('/disciplinas');
  await page.getByRole('link', { name: subject, exact: true }).click();
  await expect(page.getByRole('heading', { name: subject, level: 1 })).toBeVisible();
  await page.getByRole('button', { name: 'Nova prova' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Nova prova' });
  await dialog.getByLabel('Nome da avaliação').fill(title);
  await dialog.getByLabel('Data').fill(futureDate(days));
  await dialog.getByLabel('Horário').fill('10:00');
  await dialog.getByRole('radio', { name: 'Alta' }).click();
  await dialog.getByRole('button', { name: 'Cadastrar prova' }).click();
  await expect(page).toHaveURL(/\/provas\/[0-9a-f-]+\/conteudos$/);
  await expect(page.getByRole('heading', { name: title, level: 1 })).toBeVisible();
}

test('onboarding valida o ano letivo e cadastra as 20 disciplinas oficiais', async ({ page }) => {
  await page.getByRole('button', { name: 'Começar' }).click();
  await expect(page.getByText('Informe o nome do ano letivo.')).toBeVisible();

  await page.getByRole('button', { name: 'Conferir a lista' }).click();
  await expect(page.getByText('INT.12845')).toBeVisible();
  await expect(page.getByText('código a confirmar')).toBeVisible();

  await completeOnboarding(page, { name: 'Estudante' });
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Estudante');
  await expect(page.getByRole('link', { name: /^Disciplinas 20/ })).toBeVisible();
  await expect(page.getByText('Você ainda não cadastrou provas')).toBeVisible();

  await page.getByRole('navigation', { name: 'Menu principal' }).getByRole('link', { name: 'Disciplinas' }).click();
  await expect(page.locator('section[aria-labelledby="grupo-formacao_geral"] a[href^="/disciplinas/"]')).toHaveCount(13);
  await expect(page.locator('section[aria-labelledby="grupo-formacao_tecnica"] a[href^="/disciplinas/"]')).toHaveCount(7);

  const mci = page.locator('div.sc', { has: page.getByRole('link', { name: 'Máquinas e Comandos Industriais' }) });
  await expect(mci.getByText('Código a confirmar')).toBeVisible();

  // Busca ignora acentos: "fisica" encontra "Física 2" e "Educação Física 2".
  await page.getByLabel('Buscar disciplinas').fill('fisica');
  await expect(page.locator('main a[href^="/disciplinas/"]')).toHaveCount(2);
  await expect(page.getByRole('link', { name: 'Física 2', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Educação Física 2' })).toBeVisible();
  await page.getByLabel('Buscar disciplinas').fill('INT.12853');
  await expect(page.locator('main a[href^="/disciplinas/"]')).toHaveCount(1);
  await expect(page.getByRole('link', { name: 'Sistemas Digitais' })).toBeVisible();
});

test('cria prova e conteúdos, atualiza o progresso e os dados persistem após recarregar', async ({ page }) => {
  await completeOnboarding(page);
  await createExam(page, 'Física 2', 'Avaliação 2', 5);
  await expect(page.getByText('Em 5 dias')).toBeVisible();

  await page.getByRole('button', { name: 'adicionar vários de uma vez' }).click();
  await page.getByLabel('Adicionar conteúdos cobrados').fill('- Cinemática\n- Velocidade média\n- Movimento uniforme');
  await page.getByRole('button', { name: 'Adicionar 3' }).click();
  const list = page.getByRole('list', { name: 'Conteúdos da prova' });
  await expect(list.getByRole('listitem')).toHaveCount(3);

  await page.getByRole('button', { name: /^Status de "Cinemática"/ }).click();
  await page.getByRole('menuitemradio', { name: 'Dominado' }).click();
  await expect(page.getByRole('button', { name: /^Status de "Cinemática": Dominado/ })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: 'Preparação da prova' })).toHaveAttribute('aria-valuenow', '33');

  await page.reload();
  await expect(list.getByRole('listitem')).toHaveCount(3);
  await expect(page.getByRole('progressbar', { name: 'Preparação da prova' })).toHaveAttribute('aria-valuenow', '33');

  // Status da prova
  await page.getByRole('link', { name: 'Visão geral' }).click();
  await expect(page.getByText('Próximos passos')).toBeVisible();
  await page.getByRole('button', { name: 'Não iniciada' }).click();
  await page.getByRole('menuitemradio', { name: 'Em preparação' }).click();
  await expect(page.getByText('Status: Em preparação.')).toBeVisible();

  // Dashboard reflete a prova
  await page.getByRole('navigation', { name: 'Menu principal' }).getByRole('link', { name: 'Dashboard' }).click();
  await expect(page.getByText('Próximas provas')).toBeVisible();
  await expect(page.getByRole('link', { name: /Avaliação 2/ }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: /^Próximas avaliações 1/ })).toBeVisible();
  await expect(page.getByLabel('Progresso geral', { exact: true })).toHaveText('33%');

  // Lista de provas com filtros
  await page.getByRole('navigation', { name: 'Menu principal' }).getByRole('link', { name: 'Provas' }).click();
  await expect(page.getByRole('heading', { name: 'Provas', level: 1 })).toBeVisible();
  await expect(page.getByRole('main').getByRole('link', { name: /Avaliação 2/ })).toBeVisible();
  await page.getByLabel('Filtrar por status').selectOption('em_revisao');
  await expect(page.getByText('Nenhuma prova encontrada')).toBeVisible();
  await page.getByRole('button', { name: 'Limpar' }).click();
  await expect(page.getByRole('main').getByRole('link', { name: /Avaliação 2/ })).toBeVisible();
});

test('formulário de prova mostra erros de validação', async ({ page }) => {
  await completeOnboarding(page);
  await page.getByRole('button', { name: 'Nova prova' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Nova prova' });
  await dialog.getByRole('button', { name: 'Cadastrar prova' }).click();
  await expect(dialog.getByText('Selecione a disciplina.')).toBeVisible();
  await expect(dialog.getByText('Informe o nome da avaliação.')).toBeVisible();
  await expect(dialog).toBeVisible();
});

test('excluir prova exige confirmação digitada e preserva a disciplina', async ({ page }) => {
  await completeOnboarding(page);
  await createExam(page, 'Química 2', 'Prova bimestral');
  await page.getByLabel('Adicionar conteúdos cobrados').fill('Estequiometria');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('list', { name: 'Conteúdos da prova' }).getByRole('listitem')).toHaveCount(1);

  await page.getByRole('button', { name: 'Mais ações' }).click();
  await page.getByRole('menuitem', { name: 'Excluir prova…' }).click();
  const dialog = page.getByRole('dialog', { name: /Excluir "Prova bimestral"/ });
  await expect(dialog.getByText('1 conteúdo')).toBeVisible();
  const confirm = dialog.getByRole('button', { name: 'Excluir prova' });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel(/Para confirmar, digite/).fill('Prova bimestral');
  await confirm.click();
  await expect(page.getByText('Prova excluída.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Química 2', level: 1 })).toBeVisible();
  await expect(page.getByText('Você ainda não cadastrou provas nesta disciplina.')).toBeVisible();
});

test('edita disciplina (professor e código) e arquiva', async ({ page }) => {
  await completeOnboarding(page);
  await page.goto('/disciplinas');
  await page.getByRole('link', { name: 'Máquinas e Comandos Industriais' }).click();
  await page.getByRole('button', { name: 'Editar', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Editar disciplina' });
  await dialog.getByLabel('Professor(a)').fill('Prof. Exemplo');
  await dialog.getByRole('button', { name: 'Salvar alterações' }).click();
  await expect(page.getByText('Professor(a): Prof. Exemplo')).toBeVisible();
  await expect(page.getByText('Código a confirmar')).toBeVisible();

  await page.getByRole('button', { name: 'Mais ações' }).click();
  await page.getByRole('menuitem', { name: 'Arquivar disciplina' }).click();
  await expect(page.getByText('Disciplina arquivada.')).toBeVisible();
  await page.goto('/disciplinas');
  await expect(page.getByRole('link', { name: 'Máquinas e Comandos Industriais' })).toHaveCount(0);
  await page.getByLabel(/Mostrar arquivadas/).check();
  await expect(page.getByRole('link', { name: 'Máquinas e Comandos Industriais' })).toBeVisible();
});

test('tema e menu recolhido são preferências persistentes', async ({ page }) => {
  await completeOnboarding(page);
  await expect(page.locator('html')).toHaveClass(/dark/);
  await page.getByRole('button', { name: 'Alternar tema claro/escuro' }).first().click();
  await expect(page.locator('html')).not.toHaveClass(/dark/);

  await page.getByRole('button', { name: 'Recolher menu' }).click();
  await expect(page.getByRole('button', { name: 'Expandir menu' })).toHaveAttribute('aria-expanded', 'false');

  await page.reload();
  await expect(page.locator('html')).not.toHaveClass(/dark/);
  await expect(page.getByRole('button', { name: 'Expandir menu' })).toBeVisible();
});

test('backup: exporta JSON com todas as disciplinas', async ({ page }) => {
  await completeOnboarding(page);
  await page.goto('/configuracoes#dados');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar backup (JSON)' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^central-de-estudos-backup-.*\.json$/);
  const backup = JSON.parse(readFileSync((await download.path())!, 'utf8'));
  expect(backup.app).toBe('central-de-estudos');
  expect(backup.counts.subjects).toBe(20);
  expect(backup.counts.academic_years).toBe(1);
});

test('módulos futuros informam a fase, sem ações simuladas', async ({ page }) => {
  await completeOnboarding(page);
  await page.goto('/biblioteca');
  await expect(page.getByText('Chega na Fase 3')).toBeVisible();
  await expect(page.getByText('nenhuma função aqui é simulada', { exact: false })).toBeVisible();
  await page.goto('/rota-que-nao-existe');
  await expect(page.getByText('Página não encontrada')).toBeVisible();
});

test('restaura um backup na tela de início (migração entre navegadores/contas)', async ({ page, browser }) => {
  await completeOnboarding(page);
  await createExam(page, 'Biologia 2', 'Avaliação de genética');
  await page.getByLabel('Adicionar conteúdos cobrados').fill('Leis de Mendel');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('list', { name: 'Conteúdos da prova' }).getByRole('listitem')).toHaveCount(1);
  await page.goto('/configuracoes#dados');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar backup (JSON)' }).click();
  const backupPath = (await (await downloadPromise).path())!;

  // Outro navegador (banco vazio): restaura o backup pela tela de início.
  const context = await browser.newContext();
  const other = await context.newPage();
  const otherErrors = trackConsoleErrors(other);
  await other.goto('/');
  await expect(other.getByRole('heading', { name: 'Bem-vindo à Central de Estudos' })).toBeVisible();
  await other.getByLabel('Arquivo de backup').setInputFiles(backupPath);
  await expect(other.getByText(/Backup restaurado/)).toBeVisible();
  await expect(other.getByRole('link', { name: /^Disciplinas 20/ })).toBeVisible();
  await other.goto('/provas');
  await other.getByRole('main').getByRole('link', { name: /Avaliação de genética/ }).click();
  await other.getByRole('navigation', { name: 'Seções da prova' }).getByRole('link', { name: /^Conteúdos/ }).click();
  await expect(other.getByText('Leis de Mendel')).toBeVisible();
  expect(otherErrors).toEqual([]);
  await context.close();
});
