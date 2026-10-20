# JARVIS

Inteligência local para Windows: percepção do computador, voz offline em português,
planejamento com execução **verificada**, memória pessoal com lembretes confiáveis e dois hubs —
o **JARVIS CORE** (cérebro neural em 3D) e o **TARDIS** (memória espacial navegável).
Cérebro principal: Ollama local.

- Instalação e uso: [`ULTRON/README_JARVIS.md`](ULTRON/README_JARVIS.md)
- Arquitetura e mapa de integração: [`ULTRON/ARCHITECTURE_JARVIS.md`](ULTRON/ARCHITECTURE_JARVIS.md)
- Mudanças: [`ULTRON/CHANGELOG_JARVIS.md`](ULTRON/CHANGELOG_JARVIS.md) ·
  desempenho: [`ULTRON/PERFORMANCE_REPORT.md`](ULTRON/PERFORMANCE_REPORT.md) ·
  voz: [`ULTRON/VOICE_DIAGNOSTICS.md`](ULTRON/VOICE_DIAGNOSTICS.md) ·
  testes: [`ULTRON/TEST_REPORT.md`](ULTRON/TEST_REPORT.md)

```
ULTRON\INSTALL_JARVIS.bat      instala (Python 3.11 + Ollama; não apaga nada)
ULTRON\START_JARVIS.bat        inicia o JARVIS CORE  (--stop, --status, --diagnose, --voice-test)
ULTRON\DIAGNOSTICO_JARVIS.bat  modo de diagnóstico (componentes ausentes, saúde, voz)
python ULTRON\TEST_JARVIS.py   testes
```

A pasta `ULTRON/` e o pacote Python `ultron` mantêm o nome da identidade anterior para
preservar dados, configurações e atalhos existentes. O projeto JARVIS original (anterior ao
ULTRON) está no histórico do Git: `git checkout 53e5a31 -- JARVIS`.
