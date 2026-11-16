"""Perfis de inteligência e roteamento por tarefa — lógica PURA (sem rede, sem Qt, sem banco).

O roteador de modelos pergunta aqui "para ESTA tarefa, com ESTE perfil e com O QUE EXISTE AGORA, qual modelo?".
A resposta (``Route``) diz o alvo, o motivo em português e se o uso é pago — o roteador é quem conversa com os
provedores, pede autorização no primeiro uso pago e registra o consumo.

Perfis (CONFIGURAÇÕES > INTELIGÊNCIA):

* LOCAL       — só Ollama. Nada sai do computador.
* HÍBRIDO     — local no dia a dia e em todo conteúdo pessoal; nuvem (se permitida) para raciocínio pesado e
                planejamento.
* AVANÇADO    — nuvem para o que não for trivial; local para cumprimentos, conteúdo pessoal e sem internet.
* ECONÔMICO   — local sempre que existir; nuvem só como reserva quando o local estiver indisponível, com o
                modelo rápido (mais barato).
* PRIVACIDADE — só local, sem pesquisa na internet, nada pessoal sai do computador em nenhuma hipótese.

Regras que valem para TODOS os perfis:

* conteúdo sensível (senhas, tokens, documentos, dados bancários ou de saúde) nunca vai para a nuvem;
* contexto pessoal — tarefas com ferramentas (resultados de arquivos e programas locais) e análises da TARDIS
  (memória pessoal) — só vai para a nuvem com ``cloud_share_memory`` ligado (padrão: desligado);
* capturas de tela/imagens só vão para a nuvem com ``cloud_images`` ligado (padrão: desligado);
* nuvem só quando o provedor está realmente pronto (chave, modelo, modo de privacidade, permissão de modelos
  externos) e dentro do limite mensal — caso contrário, local, com o motivo dito na resposta;
* sem modelo local e sem nuvem permitida, a rota é ``none`` (indisponível) — nunca uma resposta inventada.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

PROFILE_KEYS = ("local", "hibrido", "avancado", "economico", "privacidade")
PROFILE_LABELS = {"local": "LOCAL", "hibrido": "HÍBRIDO", "avancado": "AVANÇADO", "economico": "ECONÔMICO",
                  "privacidade": "PRIVACIDADE"}
PROFILE_HELP = {
    "local": "Só modelos locais (Ollama). Nada sai do computador.",
    "hibrido": "Local no dia a dia e em todo conteúdo pessoal; nuvem, se permitida, para raciocínio pesado e "
               "planejamento.",
    "avancado": "Nuvem para o que não for trivial; local para conversa rápida, conteúdo pessoal e quando não há "
                "internet.",
    "economico": "Local sempre que existir; nuvem só como reserva, com o modelo rápido (mais barato).",
    "privacidade": "Só local, sem pesquisa na internet; nada pessoal sai do computador.",
}
CLOUD_PROFILES = frozenset({"hibrido", "avancado", "economico"})

# alvos possíveis de uma rota
LOCAL_FAST, LOCAL_ROBUST, CLOUD_FAST, CLOUD_ROBUST, NONE = ("local_fast", "local_robust", "cloud_fast",
                                                             "cloud_robust", "none")
TARGET_LABELS = {LOCAL_FAST: "modelo local rápido", LOCAL_ROBUST: "modelo local robusto",
                 CLOUD_FAST: "nuvem (modelo rápido)", CLOUD_ROBUST: "nuvem (modelo robusto)", NONE: "nenhum modelo"}

PURPOSES = ("conversa", "planejamento", "agente", "visao", "tardis", "imaginacao")

_REASONING = re.compile(
    r"\b(explique|explica|por que|porque|compare|comparar|analise|analisar|avalie|calcule|demonstre|prove|"
    r"estrategia|arquitetura|projete|planeje|otimiz\w*|algoritmo|codigo|programa\w*|depure|debug|refator\w*|"
    r"diferenca entre|vantagens|desvantagens|passo a passo|resuma|resumo|traduza|redija|escreva um)\b")
_TRIVIAL = re.compile(r"^(oi|ola|bom dia|boa tarde|boa noite|obrigad\w*|valeu|tudo bem|beleza|ok|certo|"
                      r"quem e voce|como voce esta)\b")
_SENSITIVE = re.compile(
    r"\b(senha|password|token|chave (de )?api|api key|segredo|cpf|rg|cnh|passaporte|cartao (de credito)?|"
    r"cvv|conta bancaria|agencia|pix|saldo|extrato|salario|imposto de renda|diagnostico medico|exame|"
    r"receita medica|remedio|doenca|prontuario|endereco residencial)\b")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


@dataclass
class Assessment:
    """O que a tarefa exige (estimado do pedido, sem chamar modelo nenhum)."""

    purpose: str = "conversa"
    complexity: float = 0.3          # 0 = trivial · 1 = raciocínio pesado
    sensitive: bool = False
    images: bool = False
    tools: bool = False
    context_chars: int = 0
    signals: list = field(default_factory=list)
    personal: bool = False           # depende de memória pessoal, arquivos ou resultados de ferramentas locais

    @property
    def level(self) -> str:
        return "alta" if self.complexity >= 0.6 else "média" if self.complexity >= 0.3 else "baixa"

    def to_dict(self) -> dict:
        return {"purpose": self.purpose, "complexity": round(self.complexity, 2), "level": self.level,
                "sensitive": self.sensitive, "personal": self.personal, "images": self.images, "tools": self.tools,
                "context_chars": self.context_chars, "signals": list(self.signals)}


def assess(text: str, *, purpose: str = "conversa", images: bool = False, tools: bool = False,
           context_chars: int = 0) -> Assessment:
    """Complexidade, sensibilidade e tipo da tarefa a partir do pedido do usuário."""
    folded = fold(text)
    words = len(folded.split())
    signals: list[str] = []
    score = 0.2
    if purpose in ("planejamento", "tardis"):
        score += 0.45
        signals.append(purpose)
    elif purpose == "agente" or tools:
        score += 0.2
        signals.append("ferramentas")
    elif purpose == "imaginacao":
        score += 0.25
        signals.append("criativo")
    reasoning = {m.group(0) for m in _REASONING.finditer(folded)}
    if reasoning:                                     # cada pedido de raciocínio a mais pesa (até três)
        score += 0.3 + 0.15 * min(2, len(reasoning) - 1)
        signals.append("raciocínio")
    if words > 60:
        score += 0.2
        signals.append("pedido longo")
    elif words > 25:
        score += 0.1
    if folded.count("?") > 1:
        score += 0.1
        signals.append("várias perguntas")
    if "```" in text or re.search(r"\bdef |\bclass |\bfunction\b|;\s*$", text, re.MULTILINE):
        score += 0.2
        signals.append("código")
    if context_chars > 6000:
        score += 0.1
        signals.append("contexto grande")
    if _TRIVIAL.match(folded.strip()) and words <= 6:
        score = 0.05
        signals = ["trivial"]
    sensitive = bool(_SENSITIVE.search(folded))
    if sensitive:
        signals.append("conteúdo sensível")
    if images:
        signals.append("imagem")
    personal = bool(tools or purpose in ("agente", "tardis"))
    if personal:
        signals.append("contexto pessoal")
    return Assessment(purpose if purpose in PURPOSES else "conversa", max(0.0, min(1.0, score)), sensitive,
                      images, tools, context_chars, signals, personal)


@dataclass
class Availability:
    """O que existe AGORA (lido do Ollama, do provedor e do livro de consumo — nunca presumido)."""

    local_fast: bool = False
    local_robust: bool = False
    cloud_ready: bool = False
    cloud_blocked: str = "nuvem não configurada"
    within_budget: bool = True
    budget_reason: str = ""
    cloud_images: bool = False
    share_personal: bool = False


@dataclass
class Route:
    target: str
    reason: str
    paid: bool = False
    profile: str = "local"
    assessment: Assessment | None = None
    notes: list = field(default_factory=list)       # o que o usuário precisa saber (ex.: por que não foi à nuvem)

    @property
    def local(self) -> bool:
        return self.target in (LOCAL_FAST, LOCAL_ROBUST)

    @property
    def cloud(self) -> bool:
        return self.target in (CLOUD_FAST, CLOUD_ROBUST)

    def to_dict(self) -> dict:
        return {"target": self.target, "label": TARGET_LABELS.get(self.target, self.target), "reason": self.reason,
                "paid": self.paid, "profile": self.profile, "notes": list(self.notes),
                "assessment": self.assessment.to_dict() if self.assessment else None}


def effective_profile(settings) -> str:
    """O perfil escolhido; sem escolha, o comportamento anterior: OpenAI escolhida → AVANÇADO, senão LOCAL."""
    chosen = str(getattr(settings, "intelligence_profile", "") or "")
    if chosen in PROFILE_KEYS:
        return chosen
    return "avancado" if getattr(settings, "ai_provider", "ollama") == "openai" else "local"


def _local(a: Assessment, av: Availability, profile: str, reason: str, notes: list) -> Route:
    heavy = a.complexity >= 0.6
    if heavy and av.local_robust:
        return Route(LOCAL_ROBUST, reason + "; tarefa de complexidade alta → modelo local robusto", False, profile,
                     a, notes)
    if av.local_fast:
        if heavy:
            notes.append("nenhum modelo local robusto instalado (ex.: ollama pull qwen2.5:7b)")
        return Route(LOCAL_FAST, reason, False, profile, a, notes)
    if av.local_robust:
        return Route(LOCAL_ROBUST, reason + "; só o modelo robusto está instalado", False, profile, a, notes)
    return Route(NONE, reason + "; nenhum modelo local disponível", False, profile, a, notes)


def decide(a: Assessment, profile: str, av: Availability) -> Route:
    """A rota para esta tarefa. Determinística: as mesmas entradas dão sempre a mesma resposta."""
    profile = profile if profile in PROFILE_KEYS else "local"
    notes: list[str] = []
    no_local = not (av.local_fast or av.local_robust)
    # 1) o que NUNCA vai para a nuvem
    if profile in ("local", "privacidade"):
        return _local(a, av, profile, f"perfil {PROFILE_LABELS[profile]}: só modelos locais", notes)
    if a.sensitive:
        return _local(a, av, profile, "conteúdo sensível: fica no computador", notes)
    if a.personal and not av.share_personal:
        return _local(a, av, profile, "contexto pessoal (memória, arquivos ou ferramentas): fica no computador",
                      notes)
    if a.images and not av.cloud_images:
        return _local(a, av, profile, "imagem/captura de tela: fica no computador (envio à nuvem desligado)",
                      notes)
    # 2) a nuvem está mesmo disponível?
    cloud_ok = av.cloud_ready and av.within_budget
    if not cloud_ok:
        why = av.budget_reason if av.cloud_ready else av.cloud_blocked
        route = _local(a, av, profile, f"nuvem indisponível ({why})", notes)
        return route
    # 3) cada perfil com nuvem
    if profile == "economico":
        if not no_local:
            return _local(a, av, profile, "perfil ECONÔMICO: local primeiro", notes)
        return Route(CLOUD_FAST, "perfil ECONÔMICO: nenhum modelo local disponível → nuvem, modelo rápido",
                     True, profile, a, notes)
    if profile == "hibrido":
        if a.complexity >= 0.6:
            return Route(CLOUD_ROBUST, f"perfil HÍBRIDO: complexidade {a.level} → nuvem", True, profile, a, notes)
        if no_local:
            return Route(CLOUD_FAST, "perfil HÍBRIDO: nenhum modelo local disponível → nuvem, modelo rápido",
                         True, profile, a, notes)
        return _local(a, av, profile, f"perfil HÍBRIDO: complexidade {a.level} → local", notes)
    # avançado
    if a.complexity >= 0.6:
        return Route(CLOUD_ROBUST, f"perfil AVANÇADO: complexidade {a.level} → nuvem, modelo robusto", True,
                     profile, a, notes)
    if a.complexity > 0.1 or no_local:
        return Route(CLOUD_FAST, f"perfil AVANÇADO: complexidade {a.level} → nuvem, modelo rápido", True, profile,
                     a, notes)
    return _local(a, av, profile, "perfil AVANÇADO: pedido trivial → local (mais rápido)", notes)
