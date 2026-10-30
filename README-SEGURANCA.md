# JARVIS / ULTRON — Snapshot de segurança

- Repositório: JLeoBRx/utron-jarvis
- Branch de origem: `claude/adoring-brahmagupta-vcejpt`
- Commit de origem: `d16c9d15734674abde8af6aa55900bf95f48391d`
- Commit inicial do snapshot: `fe1d5c19755ade5728fcb5a9dbe2933258c9fe64`
- Arquivos versionados no snapshot: **341**
- Soma dos tamanhos dos blobs: **333.174.052 bytes (317,7 MiB)**

## O que está preservado

A branch foi criada a partir do commit de origem completo e mantém toda a árvore versionada daquele commit. Isso inclui o código-fonte, firmware, simulador, testes, documentação, modelos Vosk/Piper e o arquivo `JARVIS_FINAL.zip` que já estavam rastreados no Git.

O arquivo `SEGURANCA_BACKUP/MANIFEST.csv` na branch de trabalho lista o caminho, o SHA do blob Git, o tamanho e o modo dos 341 arquivos preservados. O manifesto permite conferir cada objeto do snapshot.

## O que não é coberto por um snapshot Git

Arquivos locais não versionados/ignorados não são incluídos: ambientes virtuais, caches, logs locais, bancos SQLite e seus arquivos WAL/SHM, configurações pessoais, credenciais do Windows, arquivos exportados e alterações que nunca foram commitadas.

Para proteger os dados pessoais do JARVIS, use o recurso interno de backup do banco e faça uma cópia local separada das configurações e dos modelos instalados. Não envie esses dados privados para o repositório público.

## Recuperação

Para consultar ou recuperar o estado exato, use o commit inicial do snapshot acima; a branch de segurança foi criada para manter esse histórico. Não force push nem apague essa branch.
