// Sobe/derruba o Supabase LOCAL de teste (Docker) e aplica as migrações.
//   node scripts/supabase-local.mjs up      → sobe serviços + aplica migrações
//   node scripts/supabase-local.mjs down    → derruba (mantém dados)
//   node scripts/supabase-local.mjs reset   → derruba apagando dados e sobe de novo
// O gateway HTTP (porta 54321) é iniciado separadamente: `npm run supabase:local:gateway`
// (os testes de banco o iniciam automaticamente).
import { execSync } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const stackDir = join(root, 'tests', 'supabase-local');
const sh = (cmd, cwd = stackDir) => execSync(cmd, { cwd, stdio: 'inherit' });

async function waitFor(url, label, timeoutMs = 120_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      /* ainda subindo */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`${label} não respondeu em ${timeoutMs / 1000}s (${url})`);
}

async function up() {
  sh('node keys.mjs');
  sh('docker compose up -d --wait');
  await waitFor('http://127.0.0.1:54331/health', 'Auth (GoTrue)');
  await waitFor('http://127.0.0.1:54333/status', 'Storage');
  sh('node scripts/apply-migrations.mjs', root);
  console.log('Supabase local pronto. Gateway: npm run supabase:local:gateway (porta 54321).');
}

const command = process.argv[2] ?? 'up';
if (command === 'up') await up();
else if (command === 'down') sh('docker compose down');
else if (command === 'reset') {
  sh('docker compose down -v');
  await up();
} else {
  console.error(`Comando desconhecido: ${command}`);
  process.exit(1);
}
