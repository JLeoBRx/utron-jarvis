// Gateway HTTP mínimo que imita o Kong do Supabase para o ambiente LOCAL de teste.
//   /auth/v1/*    → GoTrue    (127.0.0.1:54331)
//   /rest/v1/*    → PostgREST (127.0.0.1:54332)
//   /storage/v1/* → Storage   (127.0.0.1:54333)
// Também responde CORS para o navegador (testes E2E).
import http from 'node:http';

const PORT = Number(process.env.GATEWAY_PORT ?? 54321);
const routes = [
  { prefix: '/auth/v1', port: 54331 },
  { prefix: '/rest/v1', port: 54332 },
  { prefix: '/storage/v1', port: 54333 },
];

function cors(res, req) {
  res.setHeader('Access-Control-Allow-Origin', req.headers.origin ?? '*');
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD');
  res.setHeader(
    'Access-Control-Allow-Headers',
    req.headers['access-control-request-headers'] ??
      'authorization,apikey,content-type,x-client-info,prefer,range,accept-profile,content-profile,x-upsert,cache-control',
  );
  res.setHeader('Access-Control-Expose-Headers', 'content-range,content-length,content-type,x-total-count');
  res.setHeader('Access-Control-Max-Age', '600');
}

function handler(req, res) {
  cors(res, req);
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }
  const route = routes.find((r) => req.url?.startsWith(r.prefix));
  if (!route) {
    res.writeHead(404, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ message: 'rota não encontrada' }));
    return;
  }
  const path = req.url.slice(route.prefix.length) || '/';
  const headers = { ...req.headers, host: `127.0.0.1:${route.port}` };
  // Como o Kong: se não houver Authorization, usa a apikey como Bearer.
  if (!headers.authorization && headers.apikey) headers.authorization = `Bearer ${headers.apikey}`;
  const upstream = http.request(
    { host: '127.0.0.1', port: route.port, path, method: req.method, headers },
    (up) => {
      const outHeaders = { ...up.headers };
      delete outHeaders['access-control-allow-origin'];
      res.writeHead(up.statusCode ?? 502, outHeaders);
      up.pipe(res);
    },
  );
  upstream.on('error', (err) => {
    res.writeHead(502, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ message: `upstream indisponível: ${err.message}` }));
  });
  req.pipe(upstream);
}

/** Inicia o gateway; resolve com o servidor (para encerrar nos testes). */
export function startGateway(port = PORT) {
  return new Promise((resolve, reject) => {
    const server = http.createServer(handler);
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  await startGateway();
  console.log(`gateway Supabase local em http://127.0.0.1:${PORT}`);
}
