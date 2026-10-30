# JARVIS / ULTRON — Segurança, integridade e recuperação

## Snapshot de segurança no GitHub

A cópia de segurança anterior à continuação das Fases 7 e 8 está na branch:

`safety/backup-before-phase-7-8-20261029`

- Commit inicial do snapshot: `fe1d5c19755ade5728fcb5a9dbe2933258c9fe64`
- Commit de origem: `d16c9d15734674abde8af6aa55900bf95f48391d`
- Arquivos versionados preservados: **341**
- Soma de tamanho dos blobs: **333.174.052 bytes (317,7 MiB)**

O snapshot preserva a árvore Git completa do commit de origem, incluindo código-fonte, firmware, simulador, testes, documentação, modelos de voz/IA e o ZIP já rastreado no repositório. O manifesto verificável está em `SEGURANCA_BACKUP/MANIFEST.csv` na raiz do projeto.

## O que não está incluído

Um snapshot Git não inclui arquivos locais que nunca foram commitados ou que foram ignorados: ambientes virtuais, caches, logs locais, bancos de dados SQLite e arquivos WAL/SHM, configurações pessoais, credenciais do Windows, exportações e alterações locais não commitadas.

Esses dados precisam de uma cópia local separada, de preferência em disco externo ou pasta protegida. Use o comando de backup interno do JARVIS para obter uma cópia consistente do banco.

Antes de qualquer reinstalação no Windows, feche o JARVIS normalmente e faça cópia de:
- `%LOCALAPPDATA%\ULTRON\ultron.sqlite3` usando o recurso de backup do JARVIS (não copie o banco enquanto está aberto sem coordenar checkpoint/WAL);
- `%LOCALAPPDATA%\ULTRON\settings.json` e `settings.ultron-backup.json`;
- `%LOCALAPPDATA%\ULTRON\backups\`;
- modelos locais em `assets\stt\` e `assets\voices\`;
- gravações, imagens, exportações ou outros dados guardados fora do Git.

**Não envie bancos, configurações, chaves de API ou dados pessoais para um repositório público.**

## Regras de recuperação

1. Não faça force-push nem apague a branch de segurança.
2. Faça as próximas alterações em branch separada.
3. Antes de atualizar a instalação Windows, use `ATUALIZAR_JARVIS.bat`, que solicita encerramento normal e backup do banco.
4. Guarde uma cópia externa do banco e das configurações antes de reinstalar ou restaurar.
5. No Noctário, mantenha rodas suspensas e botão físico de corte acessível durante ensaios de bancada.
6. A parada Bluetooth não substitui o corte físico da alimentação dos motores.

## Limite de segurança

O snapshot é uma cópia versionada do repositório, não uma imagem completa do computador nem um backup de dados locais não versionados. Confira o commit de referência antes de usá-lo para recuperação.
