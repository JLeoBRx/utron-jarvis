# FASE 13 — HOLOGRAPHIC HUD

Nesta revisão, o elemento central da HUD foi realmente substituído.

## Alteração visual

O antigo núcleo circular/reator central deixou de ser o elemento principal e foi substituído por um **avatar humanoide holográfico** em wireframe:

- cabeça com malha holográfica;
- olhos e geometria facial minimalista;
- pescoço, ombros, tórax e braços articulados;
- mãos e pontos de articulação;
- reator luminoso no peito;
- linhas de projeção e scanlines;
- partículas e halo holográfico;
- plataforma circular de projeção;
- animação contínua ligada ao estado real do JARVIS;
- resposta visual à energia, voz/microfone e estado operacional.

O restante da HUD permanece preservado.

## Importante

O avatar é uma camada visual. Ele não cria novas permissões, não executa comandos por conta própria e não altera as regras de segurança do agente.

A validação realizada nesta versão foi sintática (`py_compile`). A aparência final deve ser conferida executando o projeto no Windows com PySide6.
