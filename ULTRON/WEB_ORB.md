# JARVIS WEB ORB — a ORBE do seu JARVIS no navegador

Uma página escura com **só a ORBE**. Ela não tem inteligência, memória nem chaves: é a presença remota da
**matriz-mãe** (o computador onde o JARVIS roda). Tudo o que você digita ou fala no site vai para o MESMO
NeuralCore, com a mesma memória, as mesmas ferramentas, o mesmo executor e as mesmas autorizações.

```
CELULAR / NAVEGADOR ──HTTPS/WSS──▶ GATEWAY (seu servidor) ◀──WSS (conexão de SAÍDA)── AGENTE ─▶ NEURALCORE (seu PC)
```

* O computador **não abre porta nenhuma** (nem no roteador): o agente sai para o gateway.
* O gateway não guarda conversas nem a memória pessoal: só dispositivos pareados (hash do token), pareamentos e
  um registro de atividades remotas (tipo, dispositivo, IP, tamanho).
* SQLite, Ollama, terminal e portas locais do computador **não** ficam expostos.

## O que está pronto e testado

| Parte | Onde | Verificado |
|---|---|---|
| Gateway (HTTPS/WSS atrás do proxy, sessões por cookie HttpOnly/Secure/SameSite=Strict, CSRF, origem conferida, limites de tentativas, CSP estrita, auditoria) | `gateway/jarvis_gateway/` | `tests/test_web_orb.py` com o gateway real em 127.0.0.1 |
| Agente da matriz-mãe (saída, reconexão automática, MESMO núcleo) | `ultron/remote/agent.py` | idem, com um NeuralCore real |
| Site da ORBE (estados reais, conversa, interromper, autorização, microfone, voz, ULTRON, desconexão) | `gateway/jarvis_gateway/static/` | Chromium (Playwright) em tamanho de celular: pareamento pelo link do QR, conversa respondida pelo núcleo, ULTRON vindo da matriz-mãe, "MATRIZ-MÃE DESCONECTADA" |
| Pareamento por QR/código com confirmação NO computador, lista e revogação | CONFIGURAÇÕES › REDE REMOTA | teste de interface (Qt) |
| Imagem Docker (usuário sem privilégios, sistema de arquivos somente leitura, HEALTHCHECK) | `gateway/Dockerfile` | construída e executada: `healthy` |
| Compose com HTTPS automático (Caddy + Let's Encrypt) | `gateway/docker-compose.yml`, `gateway/Caddyfile` | sintaxe validada; o HTTPS real depende do seu domínio |

**Não publicado.** Não existe URL pública: publicar exige um servidor e um domínio seus (abaixo). Nada aqui afirma
que a ORBE está no ar.

## O que depende de você

1. **Um servidor** com Docker (qualquer VPS Linux pequena serve) e as portas 80/443 abertas **no servidor**.
2. **Um domínio** (ou subdomínio) com registro DNS do tipo A/AAAA apontando para o servidor.
3. **O segredo de inscrição** — gerado no servidor; o hash fica lá, o texto vai uma vez para o seu PC.

## Publicar (no servidor)

```bash
git clone <seu repositório> jarvis && cd jarvis/ULTRON
cp gateway/.env.example gateway/.env            # preencha JARVIS_DOMAIN e JARVIS_PUBLIC_URL
docker compose -f gateway/docker-compose.yml --env-file gateway/.env run --rm gateway python -m jarvis_gateway hash-secret
#   → guarde o SEGREDO (vai para o PC) e cole JARVIS_ENROLL_SECRET_HASH=... no .env (ou no cofre da hospedagem)
docker compose -f gateway/docker-compose.yml --env-file gateway/.env up -d --build
curl https://orb.seudominio.com/healthz        # {"ok": true, "matriz": false, ...}
```

## Ligar o computador (matriz-mãe)

1. JARVIS › CONFIGURAÇÕES › **REDE REMOTA (ORBE WEB)** › *Endereço do gateway*: `https://orb.seudominio.com`.
2. **INSCREVER NO GATEWAY…** e cole o segredo (o JARVIS troca por um token guardado no cofre do Windows).
3. Marque **Conectar a matriz-mãe ao gateway**. O estado passa a "CONECTADO".
4. **PAREAR DISPOSITIVO**: aparece um QR Code e um código (válidos por ~5 min). Leia com o celular (ou abra o site e
   digite o código). O computador pergunta se você autoriza aquele dispositivo — só então ele entra.
5. Para tirar um dispositivo: selecione na lista e **REVOGAR SELECIONADO** (a sessão cai na hora).

## Segurança aplicada

* Tokens aleatórios (só o SHA-256 no banco); segredo de inscrição em scrypt; inscrição nova invalida a anterior.
* Sessão do dispositivo: cookie HttpOnly + Secure + SameSite=Strict, validade configurável (30 dias), revogável.
* WebSocket e pedidos que mudam algo só da própria origem; CSRF por "double submit" no encerramento de sessão.
* Limites: inscrição 5/15 min por IP; pareamento 10/10 min por IP e 5 erros por código; 20 mensagens/min e 6 áudios/min
  por dispositivo; tamanho máximo de texto e áudio.
* CSP sem scripts de terceiros nem `unsafe-inline`; `frame-ancestors 'none'`; HSTS com HTTPS.
* Autorizações: o celular responde pedidos comuns; **categorias sensíveis, apagar dados e risco alto só no computador**.
* O site não contém chaves de API nem endereços internos (teste automático).

## Atualizar e voltar atrás

* **Atualizar**: `git pull && docker compose -f gateway/docker-compose.yml --env-file gateway/.env up -d --build`.
* **Rollback**: `git checkout <commit anterior>` e o mesmo `up -d --build` (o volume `gateway-data` — dispositivos e
  auditoria — é preservado). Para recomeçar do zero os pareamentos, apague só esse volume.
* **Parar**: `docker compose -f gateway/docker-compose.yml down` (os volumes ficam).
* **Backup**: o volume `gateway-data` (`/data/gateway.sqlite3`) tem só dispositivos e auditoria; a memória pessoal
  continua no seu computador, com o backup do JARVIS.

## Desenvolvimento local (sem domínio)

```bash
cd ULTRON/gateway && pip install -r requirements.txt
python -m jarvis_gateway hash-secret          # anote o SEGREDO (vai para o JARVIS) e o hash exibido
export JARVIS_PUBLIC_URL=http://127.0.0.1:8080 JARVIS_DEV_INSECURE=1
export JARVIS_ENROLL_SECRET_HASH='scrypt$...'  # o hash exibido acima
python -m jarvis_gateway
```

`JARVIS_DEV_INSECURE` só é aceito com endereço local; fora dele o gateway exige HTTPS e recusa iniciar.
