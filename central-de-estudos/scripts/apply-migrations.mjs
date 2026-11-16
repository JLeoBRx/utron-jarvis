// Aplica as migrações de supabase/migrations em um PostgreSQL (Supabase local de
// teste ou qualquer instância), registrando-as em supabase_migrations.schema_migrations
// (mesma tabela usada pela Supabase CLI). Migrações já aplicadas são ignoradas.
//
// Uso: DATABASE_URL=postgres://... node scripts/apply-migrations.mjs
import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import pg from 'pg';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dir = join(root, 'supabase', 'migrations');
const url = process.env.DATABASE_URL ?? 'postgresql://postgres:local-test-password@127.0.0.1:54322/postgres';

const client = new pg.Client({ connectionString: url });
await client.connect();
try {
  await client.query(`
    create schema if not exists supabase_migrations;
    create table if not exists supabase_migrations.schema_migrations (
      version text primary key, statements text[], name text
    );`);
  const { rows } = await client.query('select version from supabase_migrations.schema_migrations');
  const applied = new Set(rows.map((r) => r.version));
  const files = readdirSync(dir).filter((f) => f.endsWith('.sql')).sort();
  for (const file of files) {
    const [version, ...rest] = file.replace(/\.sql$/, '').split('_');
    if (applied.has(version)) {
      console.log(`= ${file} (já aplicada)`);
      continue;
    }
    const sql = readFileSync(join(dir, file), 'utf8');
    await client.query('begin');
    try {
      await client.query(sql);
      await client.query(
        'insert into supabase_migrations.schema_migrations (version, name, statements) values ($1, $2, $3)',
        [version, rest.join('_'), [sql]],
      );
      await client.query('commit');
      console.log(`+ ${file}`);
    } catch (error) {
      await client.query('rollback');
      console.error(`x ${file}: ${error.message}`);
      process.exitCode = 1;
      break;
    }
  }
  await client.query("notify pgrst, 'reload schema'");
} finally {
  await client.end();
}
