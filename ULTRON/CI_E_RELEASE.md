# CI e preparação da entrega

O workflow `.github/workflows/jarvis-validation.yml` valida a suíte Python em 3.11 e 3.13, executa o teste C++ do núcleo do Noctário e produz um ZIP candidato da aplicação.

## Artefato

Quando o workflow terminar com sucesso, o ZIP fica nos artefatos do GitHub Actions, com retenção de 30 dias. Os artefatos dos jobs Python são independentes. O build ainda precisa passar pelo validador `tools/build_release.py --check`.

## Dependências de voz

O JARVIS usa `sounddevice` como backend principal de microfone/áudio. PyAudio não é necessário para a instalação padrão e foi removido das dependências obrigatórias porque requer headers nativos PortAudio em Linux e não é necessário quando sounddevice está disponível. A compatibilidade com instalações que tenham PyAudio continua opcional, caso instalado manualmente.

## Limites da validação CI

- O teste C++ de host não substitui compilação real do projeto PlatformIO para ESP32.
- Os testes Qt são executados no modo offscreen de Linux; não verificam bandeja, microfone, drivers, GPU ou scripts BAT em Windows.
- O artefato é candidato de software; não comprova validação do robô físico.
