# SAFRA

Plataforma inteligente local para Windows (antes chamada JARVIS): entende pedidos em português por voz ou
texto, responde com voz sintetizada e um holograma 3D com sincronização labial, guarda a memória pessoal num
banco local, acompanha tarefas no ambiente virtual TARDIS e executa ações no computador sob permissões,
autorizações e verificação. Cérebro principal: Ollama local. Objeto do TCC técnico em Desenvolvimento de
Sistemas (conclusão prevista para 2027).

- Instalação e uso: [`ULTRON/README_JARVIS.md`](ULTRON/README_JARVIS.md)
- Documentação técnica e acadêmica (TCC, relatório técnico, arquitetura, requisitos, testes, cronograma):
  [`ULTRON/docs/README.md`](ULTRON/docs/README.md)
- Mudanças: [`ULTRON/CHANGELOG_JARVIS.md`](ULTRON/CHANGELOG_JARVIS.md)

```
ULTRON\INSTALL_SAFRA.bat      instala (Python 3.11 + Ollama; não apaga nada)   = INSTALL_JARVIS.bat
ULTRON\START_SAFRA.bat        inicia o SAFRA (--console, --stop, --status, --diagnose, --voice-test)   = START_JARVIS.bat
ULTRON\DIAGNOSTICO_SAFRA.bat  diagnóstico (componentes ausentes, saúde, voz)   = DIAGNOSTICO_JARVIS.bat
python ULTRON\TEST_JARVIS.py   testes
```

A pasta `ULTRON/`, o pacote Python `ultron`, a pasta de dados `%LOCALAPPDATA%\ULTRON` e os nomes antigos dos
scripts são mantidos para preservar dados, configurações e atalhos existentes. O projeto JARVIS original
(anterior às reconstruções) está no histórico do Git: `git checkout 53e5a31 -- JARVIS`.
