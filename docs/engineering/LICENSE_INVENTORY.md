# Inventário de licenças e recursos

Data: 15/11/2026. Gerado a partir do que está **instalado e travado**, não do que se pretende usar:

```text
python scripts/licenses/inventory.py      →  docs/engineering/licenses/{python,npm,rust}.csv
```

Este documento não é parecer jurídico. Ele registra os fatos (licença declarada por cada pacote), o que é
distribuído a quem e as obrigações que daí decorrem, para que a decisão sobre a licença do SAFRA (AD-17) seja
tomada pelo autor e pela instituição com os dados na mão. **Até essa decisão, nenhum instalador é publicado** — o
bloqueio está no código do Portal (`cms/releases.py`, `RELEASE_PUBLICATION_ENABLED = False`) e é conferido por
teste.

## 1. Números

| Ecossistema | Onde | Pacotes | Diretos | Licenças encontradas |
|---|---|---:|---:|---|
| Python | `backend/` (base, Assistant, Portal, com extras de teste e de produção) | 29 | 9 | MIT (14), BSD-3-Clause (6), BSD (2), Apache-2.0 (1), Apache-2.0 OR BSD-2-Clause (1), BSD-2-Clause (1), PSF-2.0 (1), MPL-2.0 (1), **LGPL-3.0-only (2)** |
| npm | `apps/admin` | 156 | 12 | MIT (107), Apache-2.0 (25), **MPL-2.0 (12)**, ISC (3), MIT-0 (2), BSD-2-Clause (2), BSD-3-Clause (2), BlueOak-1.0.0, CC0-1.0, 0BSD |
| Rust | `desktop/poc-tauri` | 471 | 5 | MIT e/ou Apache-2.0 (≈ 420), **Unicode-3.0 (18)**, **MPL-2.0 (7)**, Zlib, BSD-3-Clause, ISC, Unlicense (todas como opção, com MIT ao lado), LGPL-2.1 só como opção ao lado de MIT/Apache |

Nenhum pacote sem licença declarada, exceto o próprio `safra-poc-tauri` (o repositório ainda não tem licença).
Nenhuma licença AGPL, SSPL ou "não comercial" nas dependências da nova geração.

## 2. O que é distribuído, e a quem

A obrigação de uma licença costuma nascer da **distribuição**. Cada parte do SAFRA chega às pessoas de um jeito:

| Parte | Como chega | É distribuição? |
|---|---|---|
| Portal (Python no servidor) | ninguém recebe o programa; o servidor responde páginas | **não** (nenhuma dependência do Portal é AGPL) |
| Site público (HTML e CSS) | enviado ao navegador | sim, mas é código próprio |
| Painel administrativo (JavaScript compilado) | enviado ao navegador de quem administra | **sim**: inclui `react`, `react-dom` e `scheduler` (MIT) |
| Assistant (Python) e a casca do desktop | instalador baixado pela página de downloads | **sim**: tudo o que estiver no instalador |
| Ferramentas de desenvolvimento e de teste (Vite, Vitest, pytest, TypeScript…) | ficam com quem desenvolve | não |

### 2.1 Já resolvido nesta fase

**Painel administrativo.** A primeira compilação **não levava** o aviso de licença do React (MIT exige o aviso em
todas as cópias). Corrigido: a compilação gera `/admin/licencas-de-terceiros.txt` com o texto da licença de cada
biblioteca de produção, e cada script compilado começa indicando esse arquivo. O CI confere as duas coisas.

## 3. Dependências diretas

| Biblioteca | Versão | Licença | Uso | Distribuída? | Obrigações | Riscos | Alternativas |
|---|---|---|---|---|---|---|---|
| fastapi | 0.163.0 | MIT | API dos dois serviços | no instalador do Assistant | manter aviso | nenhum relevante | Starlette puro, aiohttp |
| pydantic | 2.14.3 | MIT | validação | idem | manter aviso | — | — |
| SQLAlchemy | 2.1.8 | MIT | acesso a dados | idem | manter aviso | — | `sqlite3` direto (só no Assistant) |
| alembic | 1.20.1 | MIT | migrações | idem | manter aviso | — | migrações próprias |
| uvicorn | 0.54.0 | BSD-3-Clause | servidor ASGI | idem | manter aviso; não usar o nome dos autores para endosso | — | hypercorn |
| Jinja2 | 3.1.6 | BSD (classificador do pacote) | HTML do site público | não (servidor) | — | — | — |
| psycopg + psycopg-binary | 3.3.9 | **LGPL-3.0-only** | PostgreSQL do Portal em produção | **não** (servidor) | nenhuma enquanto não houver distribuição; se um dia for distribuído, permitir a troca da biblioteca e oferecer o código dela | baixo | psycopg2 (LGPL), asyncpg (Apache-2.0) |
| react, react-dom (+ scheduler) | 19.3.1 | MIT | painel administrativo | **sim**, ao navegador | aviso de licença — **feito** | — | Preact (MIT) |
| vite, vitest, typescript, testing-library, jsdom, @types | ver CSV | MIT / Apache-2.0 | desenvolvimento | não | — | — | — |
| tauri, tauri-build, plugins de notificação e instância única | 2.12.5 / 2.7.4 / 2.8.0 / 2.5.5 | Apache-2.0 OR MIT | prova de conceito da casca | **sim, se adotada** | avisos de todas as 471 caixas; ver §5 | MPL-2.0 e Unicode-3.0 entre as transitivas | QtWebEngine (§6) |

## 4. A biblioteca de voz GPL-3.0

### 4.1 Fatos verificados

| Item | Valor | Fonte |
|---|---|---|
| Pacote | `piper-tts` 1.8.0 | metadados do pacote instalado no ambiente do legado |
| Licença | **GPL-3.0-or-later** (arquivo `COPYING` com o texto da GPL versão 3) | idem |
| Projeto | `github.com/OHF-voice/piper1-gpl` | campo `Home-page` dos metadados |
| Conteúdo nativo | módulo `espeakbridge` (biblioteca compilada) e a pasta `espeak-ng-data` | arquivos do pacote |
| Outra licença incluída | `LICENSE.g2pW-Apache-2.0` (componente para chinês) | arquivos do pacote |
| Como o legado usa | `from piper import PiperVoice`, **no mesmo processo** do assistente (`ULTRON/ultron/voice/tts.py`) | código |
| Voz `pt_BR-faber-medium` | o cartão do modelo indica conjunto de dados CC0; o repositório de vozes é marcado MIT | cartão do modelo no Hugging Face, consultado em 13/11/2026 |

A licença da biblioteca **espeak-ng** em si não está num arquivo separado dentro do pacote; a conferir no
projeto espeak-ng antes da distribuição.

### 4.2 O que isso significa

O Assistant novo ainda **não usa** o Piper (a voz é da Fase 6). A questão é o que fazer quando portar a voz.
Se o Assistant importar o `piper-tts` no mesmo processo e for **distribuído** num instalador, o conjunto
distribuído fica sujeito à GPL-3.0: quem recebe o instalador tem direito ao código-fonte correspondente de todo
o programa, sob termos compatíveis com a GPL.

| Opção | O que exige | Consequência |
|---|---|---|
| **A.** Licenciar o SAFRA Assistant como GPL-3.0-or-later | código-fonte do Assistant disponível a quem recebe o instalador; avisos | compatível com tudo o que está no inventário (MIT, BSD, Apache-2.0, PSF, MPL-2.0, LGPL); a voz atual continua; o Portal, que não é distribuído, pode ter outra licença |
| **B.** Piper como programa separado, chamado pelo Assistant | distribuir o Piper com a sua licença e o seu código; o Assistant fala com ele por processo, sem importar | o Assistant pode ter outra licença, desde que a fronteira entre os programas seja real; mais trabalho e um processo a mais |
| **C.** Trocar o mecanismo de voz | avaliação de alternativas (qualidade em português, licença do motor **e** da voz) | sem GPL na voz; risco de piorar a fala; a voz do Windows (SAPI) não exige distribuir vozes, mas soa pior |

**Recomendação técnica, para a decisão do autor e da instituição:** se o Piper for mantido, a opção A é a mais
simples e a mais coerente com um projeto acadêmico cujo código já é escrito para ser lido; a opção B fica como
saída se a instituição exigir outra licença. Nada foi removido: a decisão continua aberta (AD-17).

## 5. Casca em Tauri (se for adotada)

| Licença | Caixas | Obrigação ao distribuir o executável |
|---|---|---|
| MIT / Apache-2.0 (a maioria permite escolher) | ≈ 420 | reproduzir os avisos de licença; para Apache-2.0, também os arquivos NOTICE, se houver |
| MPL-2.0: `cssparser`, `cssparser-macros`, `selectors`, `dtoa-short`, `option-ext` | 7 | o código-fonte **desses arquivos** precisa estar disponível (sem alteração, basta indicar a versão de origem); não alcança o resto do programa |
| Unicode-3.0 (componentes ICU4X) | 18 | reproduzir o aviso |
| LGPL-2.1, só como **opção** ao lado de MIT/Apache (`r-efi`) | 2 | nenhuma: escolhe-se MIT/Apache |

No Windows, a casca usa o WebView2 já presente no sistema; ele não é redistribuído pelo SAFRA. Se o instalador
vier a incluir o instalador do WebView2, os termos da Microsoft para essa redistribuição precisam ser lidos.

## 6. Alternativa: casca em QtWebEngine

`PySide6-Essentials` e `PySide6-Addons` 6.8.3 declaram **LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only** (e licença
comercial). Na opção LGPL: o Qt deve ficar como biblioteca dinâmica que o usuário possa trocar, com o texto da
licença e acesso ao código do Qt usado. O QtWebEngine inclui o Chromium, com centenas de componentes de terceiros
cujos avisos precisam acompanhar a distribuição. O legado já usa PySide6.

## 7. Recursos que não são código

| Recurso | Situação |
|---|---|
| Fontes | **nenhum arquivo de fonte é distribuído**: o site e o painel usam pilhas de fontes do sistema |
| Ícones e símbolo do SAFRA | próprios (gerados por código neste repositório) |
| Imagens do site | só as enviadas pelo administrador; responsabilidade de quem envia |
| Modelos de reconhecimento de fala (Vosk, no legado) | **licença não verificada**: a página oficial dos modelos está fora da rede permitida nesta sessão |
| Voz `pt_BR-faber-medium` (legado) | ver §4.1 |
| three.js (só no legado) | MIT; não entra na nova geração |

## 8. Pendências antes de publicar qualquer instalador

1. Decidir a licença do SAFRA Assistant e da casca (AD-17), com base na §4.
2. Escolher a casca (AD-07) e gerar o inventário do instalador **real**, no Windows (algumas dependências só
   existem lá: `pywin32`, `keyring`, `tzdata`, `colorama` e as do áudio).
3. Conferir a licença dos modelos de fala e da biblioteca espeak-ng.
4. Gerar o arquivo de avisos do instalador a partir dos CSV, como já é feito para o painel.
5. Só então trocar `RELEASE_PUBLICATION_ENABLED` — por uma alteração de código registrada nas decisões.
