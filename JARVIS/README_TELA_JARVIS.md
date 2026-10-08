# JARVIS — Tela de Sessão

Esta atualização adiciona uma tela visual de bloqueio do JARVIS após o login do Windows.

## O que ela faz

- inicia automaticamente junto com a sessão do Windows;
- ocupa a tela inteira;
- usa o ícone `jarvis_deer.ico` como identidade visual;
- na primeira execução, pede para criar um PIN;
- nas próximas execuções, pede o PIN;
- somente depois da autenticação inicia `jarvis_hud.py`;
- o PIN é salvo apenas como hash SHA-256 com salt em `%LOCALAPPDATA%\JARVIS\lock.json`.

## Importante

Isto é um **bloqueio de sessão do JARVIS**, não uma substituição do mecanismo seguro de login/bloqueio do Windows. O Windows continua responsável pela tela segura de `Win + L`, Ctrl+Alt+Del e autenticação do sistema.

## Ativar

Dentro do `.venv`:

```powershell
python jarvis_lock_setup.py on
```

## Desativar

```powershell
python jarvis_lock_setup.py off
```

## Verificar

```powershell
python jarvis_lock_setup.py status
```

## Testar sem reiniciar

```powershell
python jarvis_lock.py
```

Na primeira execução, crie seu PIN.
