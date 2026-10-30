# JARVIS / ULTRON — Segurança, integridade e recuperação

## Cópia de segurança deste repositório

A cópia de segurança anterior à continuação das Fases 7 e 8 está na branch:

`safety/backup-before-phase-7-8-20261029`

Commit do snapshot: `fe1d5c19755ade5728fcb5a9dbe2933258c9fe64`

Commit de origem: `d16c9d15734674abde8af6aa55900bf95f48391d`

Essa branch preserva o conteúdo versionado da branch de trabalho original e inclui este manifesto. A branch original não foi reescrita nem apagada.

## O que essa cópia contém

- Código-fonte Python do JARVIS/ULTRON.
- Firmware, simulador e protocolo do Noctário.
- Testes automatizados e ferramentas.
- Documentação, configurações de exemplo e scripts de instalação.

## O que não entra no snapshot Git

Por segurança e tamanho, esta cópia não inclui ambientes virtuais, caches, logs, modelos grandes de voz/IA, bancos de dados locais, configurações pessoais nem arquivos ZIP já empacotados. Esses dados podem conter memória pessoal, tokens ou credenciais e precisam ser copiados localmente de modo separado, para um disco externo ou pasta protegida.

Antes de qualquer reinstalação no Windows, feche o JARVIS normalmente e faça cópia de:
- `%LOCALAPPDATA%\ULTRON\ultron.sqlite3` e eventuais arquivos `-wal` / `-shm` (prefira o comando de backup interno do JARVIS para obter cópia consistente);
- `%LOCALAPPDATA%\ULTRON\settings.json` e `settings.ultron-backup.json`;
- `%LOCALAPPDATA%\ULTRON\backups\`;
- modelos locais em `assets\stt\` e `assets\voices\`;
- quaisquer gravações, imagens, exportações ou outros dados guardados fora do Git.

**Não envie bancos, configurações, chaves de API ou modelos privados para um repositório público.**

## Regras de recuperação

1. Não faça force-push nem apague a branch de segurança.
2. Faça as próximas alterações em branch separada.
3. Antes de atualizar a instalação Windows, use `ATUALIZAR_JARVIS.bat`, que solicita encerramento normal e backup do banco.
4. Guarde uma cópia externa do banco e das configurações antes de reinstalar ou restaurar.
5. No Noctário, mantenha rodas suspensas e botão físico de corte acessível durante ensaios de bancada.
6. A parada Bluetooth não substitui o corte físico da alimentação dos motores.

## Auditoria da cópia

A cópia é um snapshot versionado na branch mencionada, não um backup de dados locais nem uma imagem completa do computador. Confira a branch e o commit no GitHub antes de usá-la para recuperação.
