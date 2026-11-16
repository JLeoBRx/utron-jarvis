// Gera (ou lê) as chaves JWT do Supabase local de TESTE.
// NUNCA use estas chaves em produção — servem apenas ao ambiente local descartável.
import { createHmac } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

export const JWT_SECRET = 'central-de-estudos-local-test-secret-not-for-production-0001';

function b64url(input) {
  return Buffer.from(typeof input === 'string' ? input : JSON.stringify(input))
    .toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
}

export function signJwt(payload, secret = JWT_SECRET) {
  const header = b64url({ alg: 'HS256', typ: 'JWT' });
  const body = b64url(payload);
  const sig = createHmac('sha256', secret).update(`${header}.${body}`).digest('base64')
    .replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${header}.${body}.${sig}`;
}

const iat = 1700000000;
const exp = 2200000000;
export const ANON_KEY = signJwt({ role: 'anon', iss: 'supabase-local', iat, exp });
export const SERVICE_ROLE_KEY = signJwt({ role: 'service_role', iss: 'supabase-local', iat, exp });

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const env = [
    `POSTGRES_PASSWORD=local-test-password`,
    `JWT_SECRET=${JWT_SECRET}`,
    `ANON_KEY=${ANON_KEY}`,
    `SERVICE_ROLE_KEY=${SERVICE_ROLE_KEY}`,
    '',
  ].join('\n');
  writeFileSync(join(dirname(fileURLToPath(import.meta.url)), '.env'), env);
  console.log('tests/supabase-local/.env gerado');
}
