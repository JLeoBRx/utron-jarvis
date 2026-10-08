# J.A.R.V.I.S. — Fase 12: HUD Cinemático

Esta fase transforma a interface em uma camada visual cinematográfica ligada ao estado real do núcleo.

## O que foi adicionado

- Moldura técnica dinâmica nos quatro cantos da HUD.
- Retícula central discreta sincronizada com a animação do núcleo.
- Linha de varredura independente do fundo.
- Indicadores `SYSTEM`, `CORE`, `PERCEPTION` e `VERIFICATION`.
- Barra de atividade baseada no estado/nível de áudio real disponível.
- Flash visual curto quando o estado do JARVIS muda.
- Sequência visual de inicialização de 0 a 100% durante os primeiros segundos.
- A camada é transparente para o mouse e não intercepta comandos.
- A camada desaparece automaticamente quando a HUD está minimizada.

## Integração

A nova `CinematicOverlay` fica dentro da HUD existente. Ela não executa ações e não inventa telemetria: apenas representa dados que já existem no backend e no estado da interface.

O ponto de entrada continua:

```text
python main.py
```

## Limite desta fase

A fase melhora a interface. Ela não transforma, por si só, o JARVIS em um agente irrestrito nem concede novas permissões de controle do Windows.
