"""ULTRON — agente computacional local-first.

O pacote é organizado por responsabilidade (ver ARCHITECTURE_REPORT.md):

    core/         Neural Core, Event Bus, estado global, runtime, lifecycle
    personality/  identidade, diálogo e estilo (separados da lógica)
    perception/   sensores e fusão de evidências
    world/        World Model persistente
    cognition/    contexto, intenção, raciocínio, decisão, planejamento, objetivos
    memory/       memórias de trabalho, episódica, semântica, procedural e preferências
    graph/        Neural Graph persistente (fonte do crescimento do cérebro visual)
    models/       cliente Ollama e roteador dinâmico de modelos
    skills/       capacidades executáveis com execute() e verify()
    agent/        execução, verificação, recuperação e autonomia
    voice/        microfone, STT, palavra de ativação, TTS
    network/      inteligência de rede local autorizada
    privacy/      modo local e monitor de conexões externas
    imagination/  conceitos, cenários, mundos, imagens e modo sonho
    audio/        identidade sonora procedural
    health/       monitor de saúde
    plugins/      arquitetura de plugins
    proactive/    inteligência proativa
    platform/     integrações específicas do sistema operacional
    hud/          Neural HUD (somente apresentação)
"""

__version__ = "1.0.0"
NAME = "ULTRON"
