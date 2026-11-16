# Autenticação e sessões do SAFRA Portal

Data: 15/11/2026. Código: `backend/portal/src/safra_portal/auth/` e `backend/foundation/src/safra_foundation/passwords.py`.

## 1. Conferência com a OWASP

Fonte: *Password Storage Cheat Sheet*, OWASP Cheat Sheet Series, arquivo
`cheatsheets/Password_Storage_Cheat_Sheet.md` do repositório oficial `github.com/OWASP/CheatSheetSeries`
(ramo `master`), lido em 15/11/2026. O endereço `cheatsheetseries.owasp.org` estava fora da rede permitida no
ambiente de desenvolvimento; o repositório é a fonte do mesmo texto.

| Ponto | O que a fonte diz | O que o Portal faz | Situação |
|---|---|---|---|
| Algoritmo | Argon2id em primeiro lugar; "se Argon2id não estiver disponível, use scrypt" | **scrypt**, da biblioteca padrão do Python (sem dependência nativa nova) | conforme, como segunda opção recomendada |
| Parâmetros do scrypt | mínimo N=2^17 (128 MiB), r=8, p=1; ou combinações equivalentes (2^16/8/2, 2^15/8/3…) | **N=2^17, r=8, p=1**, 32 bytes de resumo | conforme (exatamente a primeira opção) |
| Sal | único e aleatório por senha | 16 bytes de `secrets.token_bytes` por senha | conforme |
| Armazenamento dos parâmetros | guardar algoritmo e custo junto do resumo, para conviver com custos diferentes | `scrypt$N$r$p$sal$resumo` | conforme |
| Aumento do custo | refazer o resumo na próxima entrada bem-sucedida | `needs_rehash` refaz na entrada se os parâmetros mudaram | conforme |
| Senhas muito longas | risco de negação de serviço | senha limitada a 256 caracteres; no máximo dois cálculos simultâneos | conforme |
| Comparação | — | `hmac.compare_digest` (tempo constante) | — |
| Pimenta (*pepper*) | opcional, defesa adicional | **não usada** | decisão: sem segredo extra para guardar nesta fase; reavaliar na publicação |

Por que não Argon2id: exigiria uma dependência nativa nova (`argon2-cffi`) nos dois sistemas operacionais; o scrypt
com o custo recomendado está na biblioteca padrão. A troca futura é possível sem invalidar senhas, porque o
formato guarda o algoritmo.

Custo medido no contêiner (4 CPUs Xeon 2,3 GHz): cerca de 0,3 s por cálculo. No ambiente de teste o custo é
reduzido de propósito (N=2^10) para a suíte não demorar; um teste confere que fora dele vale o custo documentado.

## 2. Política

| Item | Valor | Onde |
|---|---|---|
| Senha mínima | 12 caracteres (máximo 256) | `passwords.check_policy` |
| Conta nova | nasce **sem senha**; quem cria recebe uma vez um código de uso único para o dono definir a própria senha | `POST /users` |
| Primeiro administrador | só por comando no servidor (`safra-portal create-admin`); a senha é digitada no terminal | `api/cli.py` |
| Contas padrão | **nenhuma** | teste `test_a_fresh_portal_has_no_account_at_all` |
| Falha de entrada | mensagem única ("E-mail ou senha incorretos."), mesmo custo de tempo, para conta inexistente, inativa, sem senha ou bloqueada | `AuthService.login` |
| Limite por endereço | 10 tentativas em 5 minutos (configurável) | `SAFRA_PORTAL_LOGIN_ATTEMPTS_PER_IP` |
| Bloqueio da conta | após 5 falhas seguidas: 15 min, dobrando a cada nova falha, até 24 h | `LOCKOUT_THRESHOLD`, `LOCKOUT_MINUTES` |
| Sessão | *token* de 256 bits; banco guarda só o SHA-256; *cookie* `safra_portal_session` com `HttpOnly`, `SameSite=Strict`, `Path=/admin` e `Secure` quando o site é HTTPS | `auth/service.py`, `api/admin.py` |
| Prazos | 30 min sem uso; 12 h no total, mesmo em uso | `SESSION_IDLE_MINUTES`, `SESSION_ABSOLUTE_HOURS` |
| Anti-CSRF | código aleatório por sessão, exigido no cabeçalho `X-CSRF-Token` de todo pedido que altera; `Origin` conferido | `auth/deps.py` |
| Saída | revoga a sessão no servidor e apaga o *cookie* | `POST /auth/logout` |
| Sessões | listadas e encerráveis pelo próprio dono | `GET/DELETE /sessions` |
| Troca de senha | exige a senha atual; encerra as outras sessões | `POST /auth/password` |
| Recuperação | código de uso único, 30 min, só resumo no banco; gerar outro invalida o anterior; usar encerra todas as sessões e desbloqueia a conta; 5 tentativas por endereço em 15 min | `create_recovery_token`, `recover` |
| Rebaixar ou desativar | vale no pedido seguinte; desativar encerra as sessões; o último administrador ativo não pode ser rebaixado nem desativado | `update_user` |
| Limpeza | sessões e códigos vencidos há mais de um dia são apagados ao iniciar | `purge_expired` |
| Auditoria | entradas, falhas, bloqueios, saídas, trocas e recuperações; nunca a senha nem o código | `cms/audit.py` |

## 3. Testes

`backend/portal/tests/test_auth.py` (20 casos), `test_authorization.py` (10 casos), `backend/foundation/tests/
test_security_primitives.py` e as etapas de entrada e saída do teste de ponta a ponta no navegador.
