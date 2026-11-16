import { defineConfig, devices } from '@playwright/test';

/**
 * Testes de ponta a ponta.
 *  - projeto "local":    app sem Supabase (IndexedDB) — sempre executado;
 *  - projeto "supabase": app conectado ao Supabase LOCAL de teste (Docker).
 *    Ative com E2E_SUPABASE=1 após `npm run supabase:local:up`.
 */
const withSupabase = process.env.E2E_SUPABASE === '1';
const ANON_KEY = process.env.E2E_SUPABASE_ANON_KEY ?? '';

export default defineConfig({
  testDir: 'tests/e2e',
  outputDir: 'tests/e2e/.artifacts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  timeout: 45_000,
  expect: { timeout: 8_000 },
  use: {
    trace: 'off',
    screenshot: 'only-on-failure',
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
  },
  projects: [
    { name: 'local', testMatch: /local\.spec\.ts/, use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:5173' } },
    { name: 'mobile', testMatch: /mobile\.spec\.ts/, use: { ...devices['Pixel 7'], baseURL: 'http://127.0.0.1:5173' } },
    ...(withSupabase
      ? [{ name: 'supabase', testMatch: /supabase\.spec\.ts/, use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:5174' } }]
      : []),
  ],
  webServer: [
    { command: 'npx vite --port 5173 --strictPort', url: 'http://127.0.0.1:5173', reuseExistingServer: true, timeout: 60_000 },
    ...(withSupabase
      ? [
          {
            command: 'node tests/supabase-local/gateway.mjs',
            url: 'http://127.0.0.1:54321/auth/v1/health',
            reuseExistingServer: true,
            timeout: 30_000,
          },
          {
            command: 'npx vite --port 5174 --strictPort',
            url: 'http://127.0.0.1:5174',
            reuseExistingServer: true,
            timeout: 60_000,
            env: { VITE_SUPABASE_URL: 'http://127.0.0.1:54321', VITE_SUPABASE_PUBLISHABLE_KEY: ANON_KEY },
          },
        ]
      : []),
  ],
});
