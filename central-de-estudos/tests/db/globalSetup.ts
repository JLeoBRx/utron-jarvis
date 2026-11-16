import type { Server } from 'node:http';
// @ts-expect-error — módulo JS sem tipos (ambiente de teste)
import { startGateway } from '../supabase-local/gateway.mjs';

let server: Server | undefined;

export async function setup() {
  try {
    server = (await startGateway(54321)) as Server;
  } catch (error) {
    // Porta ocupada: provavelmente o gateway já está rodando (npm run supabase:local:gateway).
    if ((error as NodeJS.ErrnoException).code !== 'EADDRINUSE') throw error;
  }
}

export async function teardown() {
  await new Promise<void>((resolve) => (server ? server.close(() => resolve()) : resolve()));
}
