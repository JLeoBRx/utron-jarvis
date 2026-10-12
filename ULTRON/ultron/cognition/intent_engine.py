"""INTENT ENGINE — transforma um COMMAND em INTENT.

1. Automação do usuário por frase exata (memória procedural);
2. caminho rápido por regras em português (preservadas e ampliadas do roteador do JARVIS):
   resposta imediata, sem modelo, para comandos diretos;
3. caso contrário, a intenção fica para o modelo local (conversa, pergunta ou objetivo
   aberto), que decide via ferramentas ou plano.

Inferir intenção nunca executa nada.
"""
from __future__ import annotations

import datetime
import re
import unicodedata
from typing import Any, Callable

from .types import Intent

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]

_UNITS = {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
          "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14,
          "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19}
_TENS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
         "oitenta": 80, "noventa": 90}

CANCEL_WORDS = {"cancelar", "cancela", "cancele", "pare", "parar", "para", "para tudo", "pare tudo", "abortar",
                "aborta", "esquece", "silencio", "chega", "interromper", "interrompa", "pode parar", "pode cancelar",
                "pare agora", "para agora", "chega disso"}

CONNECTORS_RE = re.compile(r"\b(e depois|depois disso|em seguida|e entao|e logo apos|primeiro\b.*\bdepois)\b")
GOAL_VERBS_RE = re.compile(r"\b(prepare|prepara|configure|configura|organize|organiza|investigue|investiga|"
                           r"resolva|resolve|corrija|corrige|conserte|automatize|monte|planeje)\b")

FORBIDDEN_GOALS = re.compile(
    r"(desativ\w*|desliga\w*|burl\w*|contorn\w*|bypass)\W+(?:\w+\W+){0,3}(defender|antiv[ií]rus|firewall|uac|"
    r"monitoramento|seguran[cç]a do windows)|"
    r"\b(hacke\w*|invad\w*|invas[aã]o|keylogger|roub\w*\s+(senha|credencia)|quebr\w*\s+senha|"
    r"senha do (wi-?fi|wifi) do vizinho|exploit\w*|ransomware|malware|phishing|ddos|"
    r"intercept\w*\s+(tr[aá]fego|pacotes|senhas)|sniff\w*)", re.I)


def norm(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").lower())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(value.split())


def pt_number(text: str) -> int | None:
    match = re.search(r"\b(\d{1,3})\b", text)
    if match:
        return int(match.group(1))
    total = None
    for word in text.split():
        if word == "cem":
            return 100
        if word in _TENS:
            total = (total or 0) + _TENS[word]
        elif word in _UNITS:
            total = (total or 0) + _UNITS[word]
    return total


def strip_wake(raw: str, wake_words: tuple = ("ultron",)) -> str:
    text = str(raw or "").strip()
    pattern = r"^(?:(?:ok|ei|oi|ola|olá)\s+)?(?:" + "|".join(re.escape(w) for w in wake_words) + r")(?:[,;:]\s*|\s+|$)"
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()


def _intent(kind: str, text: str, **kw: Any) -> Intent:
    kw.setdefault("confidence", 0.95)
    return Intent(kind, text, **kw)


def _cmd(raw_text: str, skill_name: str, /, **args: Any) -> Intent:
    return _intent("command", raw_text, skill=skill_name, args=args)


class IntentEngine:
    def __init__(self, *, automations: Callable[[str], dict | None] | None = None,
                 wake_words: Callable[[], tuple] | None = None,
                 recent_topic: Callable[[], dict | None] | None = None):
        self._automations = automations
        self._wake_words = wake_words or (lambda: ("ultron",))
        self._recent_topic = recent_topic or (lambda: None)     # assunto recente ("anote essa ideia", "disso")

    # ------------------------------------------------------------ API
    def classify(self, raw: str) -> Intent:
        body = strip_wake(raw, tuple(self._wake_words()))
        t = norm(body).strip(" .!?")
        if not t:
            return _intent("response", body, response="Estou ouvindo.", reason="vazio")
        if FORBIDDEN_GOALS.search(t):
            return _intent("response", body, response="Não. Isso envolve contornar proteções ou invadir sistemas, "
                                                       "e eu não executo esse tipo de ação.",
                           reason="objetivo proibido")
        if t in CANCEL_WORDS:
            return _intent("cancel", body)
        if self._automations is not None:
            found = self._automations(body)
            if found:
                return _intent("command", body, skill=found["skill"], args=found["arguments"], source="automation",
                               entities={"automation": found["name"]})
        if CONNECTORS_RE.search(t):
            return _intent("goal", body, goal=body, confidence=0.75, reason="pedido com várias etapas")
        intent = self._rules(body, t)
        if intent is not None:
            return intent
        if GOAL_VERBS_RE.search(t):
            return _intent("goal", body, goal=body, confidence=0.7, reason="objetivo aberto")
        return _intent("unknown", body, confidence=0.0)

    # ------------------------------------------------------------ regras
    def _rules(self, raw: str, t: str) -> Intent | None:
        for rule in (self._secondbrain_rules, self._time_rules, self._control_rules, self._power_rules,
                     self._network_rules,
                     self._system_rules, self._project_rules, self._imagination_rules, self._memory_rules,
                     self._vision_rules, self._file_rules, self._web_rules, self._window_rules, self._app_rules,
                     self._media_rules, self._input_rules):
            intent = rule(raw, t)
            if intent is not None:
                return intent
        return None

    def _time_rules(self, raw, t):
        if re.search(r"\bque horas\b|\bhora atual\b", t):
            return _intent("response", raw, response=f"São {datetime.datetime.now():%H:%M}.")
        if re.search(r"\bque dia\b|\bdata de hoje\b|\bque data\b", t):
            d = datetime.date.today()
            return _intent("response", raw, response=f"Hoje é {DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}.")
        if re.search(r"o que (voce )?(pode|consegue|sabe) fazer|\bajuda\b|\bcomandos\b", t):
            return _intent("response", raw, template="help", response="")
        return None

    def _control_rules(self, raw, t):
        if re.search(r"\b(ativ\w*|lig\w*|habilit\w*)\b.*\b(observa\w*|visao da tela|monitoramento da tela)\b", t):
            return _intent("control", raw, args={"screen_observation": True})
        if re.search(r"\b(desativ\w*|deslig\w*|desabilit\w*|pare de)\b.*\b(observa\w*|visao da tela|monitoramento da tela|olhar a tela)\b", t):
            return _intent("control", raw, args={"screen_observation": False})
        if re.search(r"\b(ativ\w*|lig\w*|entr\w*)\b.*\bmodo (local|privado|privacidade)\b", t):
            return _intent("control", raw, args={"privacy_mode": "local"})
        if re.search(r"\bmodo (sonho|sonhar)\b|\bcomece a sonhar\b|\bsonhe\b", t):
            return _intent("dream", raw)
        if re.search(r"\bfal\w* (mais )?(devagar|lento|pausadamente)\b|\bmais devagar\b", t):
            return _intent("control", raw, args={"speech_speed_delta": -0.1})
        if re.search(r"\bfal\w* (mais )?(rapido|depressa)\b|\bmais rapido\b", t):
            return _intent("control", raw, args={"speech_speed_delta": 0.1})
        if re.search(r"\bfal\w* mais alto\b|\b(aument\w*|suba) (o volume|a altura) da (sua )?voz\b|\bvoz mais alta\b", t):
            return _intent("control", raw, args={"voice_volume_delta": 0.1})
        if re.search(r"\bfal\w* mais baixo\b|\b(diminu\w*|abaix\w*) (o volume|a altura) da (sua )?voz\b|\bvoz mais baixa\b", t):
            return _intent("control", raw, args={"voice_volume_delta": -0.1})
        if re.search(r"\b(silencio|fique quieto|nao fale)\b", t):
            return _intent("control", raw, args={"mute_voice": True})
        if re.search(r"\b(pode falar|volte a falar|ative a voz)\b", t):
            return _intent("control", raw, args={"mute_voice": False})
        return None

    # ------------------------------------------------------------ second brain
    def _topic(self) -> dict | None:
        """{"text", "record_id"}: a última fala livre do usuário ou o último registro tocado."""
        try:
            topic = self._recent_topic()
        except Exception:
            return None
        if not topic or not topic.get("text"):
            return None
        return {"text": " ".join(str(topic["text"]).split())[:300], "record_id": topic.get("record_id")}

    def _secondbrain_rules(self, raw, t):
        r = raw.strip().rstrip(".!")
        if re.search(r"\b(abr\w*|mostr\w*|exib\w*)\b.*\b(segundo cerebro|second brain|hub 2|hub dois)\b", t):
            return _intent("control", raw, args={"open_view": "second_brain"})
        if re.search(r"\b(abr\w*|mostr\w*)\b.*\b(central de )?notificacoes\b", t):
            return _intent("control", raw, args={"open_view": "second_brain", "section": "notifications"})
        # adiar lembrete: "adie o lembrete por 15 minutos", "soneca de 10 minutos"
        if re.search(r"\b(adi[ea]\w*|posterg\w*|soneca|me lembre de novo|lembre de novo)\b", t) and \
                re.search(r"\b(lembrete|aviso|alarme|isso|minutos?|horas?|min)\b", t):
            amount = pt_number(t)
            if re.search(r"\bmeia hora\b", t) and amount is None:
                minutes = 30
            elif re.search(r"\bhoras?\b", t):
                minutes = (amount or 1) * 60
            else:
                minutes = amount or 10
            return _cmd(raw, "secondbrain.snooze", minutes=max(1, min(1440, minutes)))
        # perguntas respondidas só com dados salvos
        if re.search(r"\b(minhas|quais (sao )?(as )?minhas|as)\s+prioridades\b|\bo que (eu )?tenho (para|pra) "
                     r"(hoje|amanha)\b|\bminha agenda\b|\bagenda (de hoje|de amanha|da semana)\b|"
                     r"\bo que tenho (hoje|amanha)\b|\bproximos (compromissos|lembretes)\b|\bmeus (compromissos|"
                     r"lembretes|projetos)\b|\bquais (sao )?(os )?meus projetos\b|"
                     r"\b(o que|quais tarefas|que tarefas)\b.*\b(preciso|tenho que|falta|faltam|devo)\b.*"
                     r"\b(terminar|fazer|entregar|concluir|resolver)\b.*\bsemana\b|"
                     r"\b(o que|que tarefas?|quais tarefas?|tenho algo|tem algo|ha algo|alguma coisa)\b.*"
                     r"\b(atrasad\w*|vencid\w*|em atraso)\b|\bo que (eu )?atrasei\b|"
                     r"\b(quais|que|minhas)\s+ideias\b|\b(quais|que)\s+(tarefas|registros|itens)?\s*dependem\b|"
                     r"\b(o que|que)\s+(eu\s+)?(havia|tinha|ja)?\s*decid\w*\s+(sobre|para|quanto a)\b|"
                     r"\bo que (eu )?(anotei|registrei|salvei|guardei)\b|"
                     r"\b(procure|busque|pesquise)\b.*\b(nas (minhas )?notas|no segundo cerebro|no second brain|"
                     r"nos (meus )?registros)\b|\bo que (preciso|tenho que) revisar\b", t):
            return _cmd(raw, "secondbrain.query", question=r[:400])
        # concluir
        done = re.match(r"(?i)^(?:marque|marca|marcar)\s+(?:a\s+tarefa\s+|o\s+estudo\s+|o\s+prazo\s+|a\s+|o\s+)?"
                        r"(.+?)\s+como\s+(?:feit[oa]|conclu[ií]d[oa]|pront[oa]|terminad[oa]|finalizad[oa])$", r) or \
            re.match(r"(?i)^(?:conclua|concluir|finalize|finalizar|termine|complete|conclui|terminei|finalizei)\s+"
                     r"(?:a\s+|o\s+)?(?:tarefa|estudo|prazo|rotina)\s+(.+)$", r)
        if done:
            return _cmd(raw, "secondbrain.complete", ref=done.group(1).strip()[:200])
        delete = re.match(r"(?i)^(?:apague|apaga|exclua|exclui|remova|remove|delete)\s+(definitivamente\s+)?"
                          r"(?:a|o)\s+(?:tarefa|nota|ideia|compromisso|lembrete|estudo|prazo|rotina|registro|anota[cç][aã]o)"
                          r"\s+(.+?)(\s+definitivamente|\s+para sempre|\s+permanentemente)?$", r)
        if delete:
            permanent = bool(delete.group(1) or delete.group(3))
            return _cmd(raw, "secondbrain.delete", ref=delete.group(2).strip()[:200], permanent=permanent)
        restore = re.match(r"(?i)^(?:restaure|restaura|recupere|recupera)\s+(?:a|o)\s+(?:tarefa|nota|ideia|"
                           r"compromisso|estudo|prazo|registro)\s+(.+?)(?:\s+da lixeira)?$", r) or \
            re.match(r"(?i)^(?:restaure|restaura|recupere|recupera)\s+(.+?)\s+da lixeira$", r)
        if restore:
            return _cmd(raw, "secondbrain.restore", ref=restore.group(1).strip()[:200])
        archive = re.match(r"(?i)^(?:arquive|arquiva|arquivar)\s+(?:a|o)\s+(?:tarefa|nota|ideia|projeto|compromisso|"
                           r"estudo|prazo|registro)\s+(.+)$", r)
        if archive:
            return _cmd(raw, "secondbrain.archive", ref=archive.group(1).strip()[:200])
        relate = re.match(r"(?i)^(?:a\s+)?tarefa\s+(.+?)\s+depende\s+d[aeo]\s+(?:tarefa\s+)?(.+)$", r)
        if relate:
            return _cmd(raw, "secondbrain.relate", source=relate.group(1).strip()[:200],
                        target=relate.group(2).strip()[:200], type="depends_on")
        # registrar
        reminder = re.match(r"^(?:por favor\s+)?(?:me lembr[ea]|lembr[ea][- ]me|me avis[ea]|avis[ea][- ]me|"
                            r"crie (?:um )?lembrete|novo lembrete|lembrete)\b", t)
        if reminder:
            args: dict = {"text": r[:600], "remind": True}
            if re.search(r"\b(disso|disto|daquilo)\b", t) and len(re.sub(r"\b(disso|disto|daquilo)\b", "", t).split()) <= 8:
                topic = self._topic()
                if topic and topic["record_id"]:
                    args["record"] = topic["record_id"]
                elif topic:
                    args["title"] = topic["text"][:200]
            return _cmd(raw, "secondbrain.capture", **args)
        kind_match = re.match(r"^(?:por favor\s+)?(?:anote|anota|anotar|registre|registra|registrar|salve|salva|guarde|guarda|"
                              r"crie|cria|criar|adicione|adiciona|adicionar|nova|novo|tive uma|tenho uma)\s+"
                              r"(?:(?:a|o|uma|um|essa|esta|esse|este|minha|meu|nova|novo|mais uma)\s+)*"
                              r"(ideia|nota|tarefa|estudo|prazo|rotina|contato|decisao)\b", t)
        if kind_match:
            kind = {"ideia": "idea", "nota": "note", "tarefa": "task", "estudo": "study", "prazo": "deadline",
                    "rotina": "routine", "contato": "person", "decisao": "note"}[kind_match.group(1)]
            rest = t[kind_match.end():].strip(" :,.")
            args = {"text": r[:600], "kind": kind}
            if not rest or re.fullmatch(r"(?:que (?:eu )?(?:falei|disse|tive))|(?:dela|disso|disto)", rest):
                topic = self._topic()
                if topic and not topic["record_id"]:
                    args = {"text": topic["text"][:600], "kind": kind}
            return _cmd(raw, "secondbrain.capture", **args)
        event = re.match(r"^(?:por favor\s+)?(?:marque|marca|marcar|agende|agenda|agendar)\s+(?:uma?\s+)?"
                         r"(reuniao|compromisso|consulta|evento|encontro|call|aula|entrevista|visita)?\b", t)
        if event and not re.search(r"\bcomo (feit|conclu|pront)", t):
            return _cmd(raw, "secondbrain.capture", text=r[:600], kind="event")
        jot = re.match(r"^(?:anote|anota|registre|registra)\s+(?:que\s+)?(.+)$", t)
        if jot and re.search(r"\b(hoje|amanha|depois de amanha|segunda|terca|quarta|quinta|sexta|sabado|domingo|"
                             r"\d{1,2}/\d{1,2}|\d{1,2}h|as \d{1,2}|dia \d{1,2}|semana que vem|proxima semana|"
                             r"ate (o fim|sexta|segunda|amanha))\b", jot.group(1)):
            return _cmd(raw, "secondbrain.capture", text=r[:600])
        return None

    def _power_rules(self, raw, t):
        if re.search(r"cancel\w* (o )?(desligamento|reinicio)", t):
            return _cmd(raw, "system.power", action="cancel")
        if re.search(r"\b(desligar|desliga|desligue) (o )?(computador|pc)\b", t):
            return _cmd(raw, "system.power", action="shutdown")
        if re.search(r"\b(reiniciar|reinicia|reinicie) (o )?(computador|pc)\b", t):
            return _cmd(raw, "system.power", action="restart")
        if re.search(r"\b(suspender|suspenda|hibernar|hiberne)\b", t):
            return _cmd(raw, "system.power", action="sleep")
        if re.search(r"sair da (conta|sessao)|fazer logoff|encerrar (a )?sessao", t):
            return _cmd(raw, "system.power", action="logoff")
        if re.fullmatch(r"(bloquear|bloqueie|bloqueia)( (o )?(computador|pc|tela|sessao))?", t):
            return _cmd(raw, "system.lock")
        radio = re.search(r"\b(ligar|liga|ligue|ativar|ativa|ative|desligar|desliga|desligue|desativar|desativa|desative)\b"
                          r".*?\b([wu]i[ -]?fi|[wu]ai[ -]?fai|bluetooth|blutuf\w*|modo aviao)", t)
        if radio:
            verb, what = radio.groups()
            kind = "airplane" if "aviao" in what else ("bluetooth" if what.startswith(("blue", "blut")) else "wifi")
            state = "off" if verb.startswith(("deslig", "desativ")) else "on"
            return _cmd(raw, "system.radio", radio=kind, state=state)
        if re.search(r"\bbrilho\b", t):
            level = pt_number(t)
            if re.search(r"\bmaxim[oa]\b", t):
                return _cmd(raw, "system.brightness", action="set", level=100)
            if re.search(r"\bminim[oa]\b", t):
                return _cmd(raw, "system.brightness", action="set", level=5)
            if level is not None:
                return _cmd(raw, "system.brightness", action="set", level=max(5, min(100, level)))
            if re.search(r"aument|\bsub[ae]\b|mais (alto|claro)|maior", t):
                return _cmd(raw, "system.brightness", action="up")
            if re.search(r"diminu|abaix|reduz|mais (baixo|escuro)|menor", t):
                return _cmd(raw, "system.brightness", action="down")
            return _intent("response", raw, response="Diga o nível. Por exemplo: brilho em cinquenta por cento.")
        if re.search(r"\bbateria\b|status do sistema|situacao do sistema|estado do sistema", t):
            return _cmd(raw, "system.status")
        return None

    def _network_rules(self, raw, t):
        if re.search(r"\b(export\w*|gere|gerar|salve|salvar)\b.*\b(relatorio|inventario|lista)\b.*\b(rede|dispositivos)\b", t):
            fmt = "csv" if "csv" in t else ("json" if "json" in t else "md")
            return _cmd(raw, "network.export", format=fmt)
        if re.search(r"\b(list\w*|quais|mostr\w*|exib\w*|me (diga|fale)|relacione)\b.*\bdispositivos\b.*\brede\b|"
                     r"quem (esta|ta) (na|conectado (a|na)) (minha )?rede|dispositivos (conectados|presentes) (a|na) "
                     r"(minha )?rede|inventario da rede", t):
            return _cmd(raw, "network.devices", status="present")
        if re.search(r"\b(abr\w*|acess\w*)\b.*\b(pagina|painel|interface)\b.*\b(roteador|modem|gateway)\b|"
                     r"\b(abr\w*|acess\w*) (o )?(roteador|modem)\b", t):
            return _cmd(raw, "network.open_admin")
        if re.search(r"\b(escane\w*|varr\w*|scan\w*|mape\w*|descobr\w*|procur\w*|atualiz\w*)\b.*\b(rede|dispositivos)\b|"
                     r"quem (esta|ta) (na|conectado)|dispositivos\b.*\brede\b", t):
            return _cmd(raw, "network.scan")
        if re.search(r"\b(diagnost\w*|test\w*|verifi\w*)\b.*\b(rede|internet|conexao|conectividade)\b|"
                     r"internet (esta |ta )?(lenta|caindo|fora)|sem internet|rede (esta |ta )?(lenta|instavel)", t):
            return _cmd(raw, "network.diagnose")
        ping = re.match(r"^(?:faca um |fazer |de um )?ping (?:no |na |em |para )?([\w.\-:]+)$", t)
        if ping:
            return _cmd(raw, "network.ping", host=ping.group(1))
        if re.search(r"dispositivos (conhecidos|registrados)|lista de dispositivos", t):
            return _cmd(raw, "network.devices", status="all")
        if re.search(r"\b(qual|quais|meu|minha|mostre?|informe)\b.*\b(ip|gateway|dns|rede|wi-?fi|mac)\b|"
                     r"\b(status|estado|informacoes) da rede\b|como esta a rede", t):
            return _cmd(raw, "network.status")
        return None

    def _system_rules(self, raw, t):
        if re.search(r"\b(saude|health)\b|como voce esta|status do ultron|diagnostico (do ultron|interno)", t):
            return _cmd(raw, "diagnostics.health")
        if re.search(r"relatorio do (sistema|computador)|uso de (cpu|memoria|processador)|desempenho do (pc|computador)|"
                     r"como esta o (computador|pc)", t):
            return _cmd(raw, "diagnostics.system_report")
        if re.search(r"\bprocessos\b.*\b(pesados|ativos|rodando|consumindo)|o que esta consumindo", t):
            sort = "memory" if re.search(r"memoria|ram", t) else "cpu"
            return _cmd(raw, "diagnostics.processes", sort=sort)
        if re.search(r"\b(perifericos|dispositivos conectados|dispositivos usb)\b", t):
            return _cmd(raw, "devices.list")
        if re.search(r"\b(camera|webcam)s?\b.*\b(conectad|disponive|tem|ha)", t):
            return _cmd(raw, "devices.list", category="camera")
        if re.search(r"\bmicrofones?\b.*\b(conectad|disponive|tem|ha)", t):
            return _cmd(raw, "devices.list", category="microphone")
        return None

    def _project_rules(self, raw, t):
        name = None
        match = re.search(r"\bprojeto\s+([\w.\-]+(?:\s+[A-Z][\w.\-]+)?)", raw)
        if match and norm(match.group(1)) not in ("de", "do", "da", "que", "atual", "aberto"):
            name = match.group(1)
        if re.search(r"\b(prepar\w*)\b.*\bprojeto\b", t):
            return _intent("goal", raw, template="prepare_project", goal=f"Preparar projeto {name or ''}".strip(),
                           entities={"project": name})
        if re.search(r"\b(rod\w*|execut\w*|inici\w*)\b.*\bprojeto\b", t):
            return _intent("goal", raw, template="run_project", goal=f"Executar projeto {name or ''}".strip(),
                           entities={"project": name})
        if re.search(r"\b(abr\w*)\b.*\bprojeto\b", t):
            return _intent("goal", raw, template="open_project", goal=f"Abrir projeto {name or ''}".strip(),
                           entities={"project": name})
        if re.search(r"\bdependencias\b.*\bprojeto\b|\bprojeto\b.*\bdependencias\b", t):
            return _intent("goal", raw, template="check_project", goal=f"Verificar dependências do projeto {name or ''}".strip(),
                           entities={"project": name})
        return None

    def _imagination_rules(self, raw, t):
        if re.search(r"\b(gere|gerar|crie|criar|desenhe|desenhar|faca|fazer)\b.*\b(imagem|ilustracao|desenho|figura)\b", t):
            subject = re.sub(r"(?i)^.*?\b(imagem|ilustração|ilustracao|desenho|figura)\b\s*(de|do|da|dos|das)?\s*", "", raw)
            return _intent("image", raw, entities={"subject": subject.strip() or raw})
        if re.search(r"\b(crie|criar|construa|construir|invente|inventar)\b.*\bmundo\b", t):
            return _intent("world", raw, entities={"idea": raw})
        if re.search(r"\b(explor\w*|aprofund\w*|entr\w* n[oa]|detalh\w*)\b.*\b(mundo|cidade|continente|pais|distrito|"
                     r"predio|edificio|sala|objeto|regiao)\b", t) or \
                re.match(r"^(explore|explorar|explora|aprofunde|aprofundar|visite|visitar|entre (em|no|na)|"
                         r"volte (um nivel|para cima)|suba um nivel)\b", t):
            return _intent("explore", raw, entities={"target": raw})
        if re.search(r"^e se\b|\b(cenario|cenarios|simule|simular|simulacao|alternativas|ramificacoes|opcoes para)\b", t):
            return _intent("scenario", raw, entities={"idea": raw})
        if re.search(r"^(imagine|imagina|conceba|invente)\b|\b(imagine|imagina) (um|uma|como)\b", t):
            return _intent("imagination", raw, entities={"idea": raw})
        return None

    def _memory_rules(self, raw, t):
        store = re.match(r"(?i)^(?:lembre(?:-se)?|lembra|anote|guarde|memorize|registre)\s+(?:que|de que|disso:?)?\s*(.+)$", raw.strip())
        if store and not re.search(r"\b(me lembre|lembre-me|lembrar de mim)\b", t):
            fact = store.group(1).strip().rstrip(".")
            parts = re.split(r"\s+(?:é|e|são|sao|fica|ficam|está|esta)\s+", fact, maxsplit=1)
            subject = parts[0][:80] if len(parts) == 2 else " ".join(fact.split()[:6])[:80]
            return _intent("memory_store", raw, skill="memory.remember", args={"subject": subject, "fact": fact[:600]})
        recall = re.search(r"(?:o que (?:voce )?(?:lembra|sabe|registrou) (?:sobre|de|do|da)|voce lembra (?:de|do|da|que)?)\s+(.+)", t)
        if recall:
            return _intent("memory_recall", raw, skill="memory.recall", args={"query": recall.group(1)[:200]})
        forget = re.match(r"^(?:esqueca|esquecer|apague a memoria|remova a memoria)\s+(?:sobre|de|do|da|que)?\s*(.+)$", t)
        if forget:
            return _intent("command", raw, skill="memory.forget", args={"subject": forget.group(1)[:80]})
        if re.search(r"\b(listar?|quais (sao )?(as )?)\s*automacoes\b", t):
            return _cmd(raw, "automation.list")
        delete = re.match(r"^(?:remova|remover|apague|apagar|exclua|excluir) a automacao\s+(.+)$", t)
        if delete:
            return _cmd(raw, "automation.delete", name=delete.group(1)[:60])
        return None

    def _vision_rules(self, raw, t):
        if re.search(r"\b(leia|ler)\b.*\b(texto da tela|tela)\b|\bocr\b", t):
            return _cmd(raw, "vision.read_text")
        if re.search(r"o que (tem|ha|esta|aparece) na (minha )?tela|\b(analise|analisa|veja|olhe|observe|descreva)\b.*\btela\b|"
                     r"\bo que voce (ve|esta vendo)\b", t):
            return _cmd(raw, "vision.inspect_screen", question=raw[:300])
        if re.search(r"captura de tela|\bprint\b|screenshot|tire uma foto da tela", t):
            return _cmd(raw, "vision.screenshot")
        click = re.match(r"(?i)^(?:clique|clica|clicar) (?:no|na|em|sobre o|sobre a)\s+(?:botao|botão|link|campo|menu)?\s*['\"]?(.+?)['\"]?$", raw.strip())
        if click:
            return _cmd(raw, "vision.click_element", description=click.group(1)[:200])
        return None

    def _file_rules(self, raw, t):
        r = raw.strip()
        m = re.match(r"^(?:abrir|abre|abra)\s+(?:a\s+)?pasta\s+(.+)$", r, re.I)
        if m:
            return _cmd(raw, "fs.open", path=m.group(1).strip())
        m = re.match(r"^(?:abrir|abre|abra)\s+(?:o\s+)?arquivo\s+(.+)$", r, re.I)
        if m:
            return _cmd(raw, "fs.open", path=m.group(1).strip())
        m = re.match(r"^(?:criar|crie|cria)\s+(?:uma?\s+)?pasta\s+(.+)$", r, re.I)
        if m:
            return _cmd(raw, "fs.create_folder", path=m.group(1).strip())
        m = re.match(r"^(?:criar|crie|cria)\s+(?:um\s+)?arquivo\s+(.+?)(?:\s+com\s+(?:o\s+)?(?:conteudo|conteúdo|texto)\s+(.+))?$", r, re.I)
        if m:
            args = {"path": m.group(1).strip()}
            if m.group(2):
                args["content"] = m.group(2)
            return _cmd(raw, "fs.create_file", **args)
        m = re.match(r"^renomear\s+(.+?)\s+para\s+(.+)$", r, re.I)
        if m:
            return _cmd(raw, "fs.move", source=m.group(1).strip(), destination=m.group(2).strip())
        m = re.match(r"^(?:mover|mova)\s+(?:o\s+|a\s+)?(?:arquivo|pasta)\s+(.+?)\s+para\s+(.+)$", r, re.I)
        if m:
            return _cmd(raw, "fs.move", source=m.group(1).strip(), destination=m.group(2).strip())
        m = re.match(r"^(?:copiar|copie|copia)\s+(?:o\s+|a\s+)?(?:arquivo|pasta)\s+(.+?)\s+para\s+(.+)$", r, re.I)
        if m:
            return _cmd(raw, "fs.copy", source=m.group(1).strip(), destination=m.group(2).strip())
        m = re.match(r"^(?:excluir|exclua|apagar|apague|deletar|delete)\s+(?:o\s+|a\s+)?(?:arquivo|pasta)\s+(.+)$", r, re.I)
        if m:
            return _cmd(raw, "fs.delete", path=m.group(1).strip())
        m = re.match(r"^(?:procurar|procure|pesquisar|pesquise|buscar|busque|encontre|localize)\s+(?:o\s+|a\s+)?(?:arquivo|pasta)\s+(.+?)(?:\s+em\s+(.+))?$", r, re.I)
        if m:
            args = {"name": m.group(1).strip()}
            if m.group(2):
                args["root"] = m.group(2).strip()
            return _cmd(raw, "fs.search", **args)
        m = re.match(r"^(?:leia|ler|mostre)\s+(?:o\s+)?(?:conteudo do\s+|conteúdo do\s+)?arquivo\s+(.+)$", r, re.I)
        if m:
            return _cmd(raw, "fs.read_text", path=m.group(1).strip())
        return None

    def _web_rules(self, raw, t):
        r = raw.strip()
        m = re.match(r"^(?:abrir|abre|abra)\s+(?:o\s+|a\s+)?site\s+(.+)$", r, re.I)
        if m:
            return _cmd(raw, "web.open_url", url=m.group(1).strip())
        m = re.match(r"^(?:abrir|abre|abra)\s+(?:o\s+|a\s+)?(https?://\S+|www\.\S+)$", r, re.I)
        if m:
            return _cmd(raw, "web.open_url", url=m.group(1))
        m = re.match(r"^(?:abrir|abre|abra)\s+(?:o\s+|a\s+)?(google|youtube)(?:\.com)?$", t)
        if m:
            return _cmd(raw, "web.open_url", url=f"https://www.{m.group(1)}.com")
        m = re.match(r"^(?:pesquisar|pesquise|pesquisa|procurar|procure|buscar|busque)\s+(?:(?:por|sobre)\s+)?(.+)$", r, re.I)
        if m:
            query = m.group(1).strip()
            site = "youtube" if norm(query).endswith(" no youtube") else "google"
            query = re.sub(r"\s+no\s+(?:youtube|google)\s*$", "", query, flags=re.I).strip()
            return _cmd(raw, "web.search", query=query, site=site)
        return None

    def _window_rules(self, raw, t):
        if re.search(r"\b(fechar|fecha|feche)\s+(?:(?:a|esta|essa)\s+)?janela\b", t):
            return _cmd(raw, "window.close")
        if re.search(r"\b(minimizar|minimize|minimiza)\s+(a\s+)?janela\b", t):
            return _cmd(raw, "window.state", action="minimize")
        if re.search(r"\b(maximizar|maximize|maximiza)\s+(a\s+)?janela\b", t):
            return _cmd(raw, "window.state", action="maximize")
        if re.search(r"\b(restaurar|restaure)\s+(a\s+)?janela\b", t):
            return _cmd(raw, "window.state", action="restore")
        if re.search(r"minimizar tudo|mostrar (a )?area de trabalho", t):
            return _cmd(raw, "window.show_desktop")
        if re.search(r"trocar (de )?janela|proxima janela", t):
            return _cmd(raw, "input.press_key", key="alt+tab")
        m = re.match(r"^(?:ir|va|vá|mudar|mude|alternar|alterne|trocar|troque)\s+para\s+(?:o\s+|a\s+)?(.+)$", t)
        if m:
            return _cmd(raw, "window.switch", target=m.group(1))
        return None

    def _app_rules(self, raw, t):
        m = re.match(r"^(?:abrir|abre|abra|iniciar|inicie|inicia|lancar|lance|executar|execute)\s+"
                     r"(?:(?:o|a|um|uma|aplicativo|app|programa)\s+)*(.+?)(?:\s+(?:na|no|em)\s+(.+))?$", raw.strip(), re.I)
        if m:
            name = m.group(1).strip()
            if norm(name) in ("google", "youtube"):
                return None
            args = {"name": name}
            if m.group(2) and re.search(r"[\\/:]", m.group(2)):
                args["path"] = m.group(2).strip()
            elif m.group(2):
                args["name"] = f"{name} {m.group(2)}".strip()
            return _cmd(raw, "app.open", **args)
        m = re.match(r"^(?:fechar|fecha|feche|encerrar|encerre)\s+(?:(?:o|a|aplicativo|app|programa)\s+)?(.+)$", t)
        if m and m.group(1) not in ("tudo",):
            return _cmd(raw, "app.close", name=m.group(1))
        return None

    def _media_rules(self, raw, t):
        if re.search(r"aument\w* (o )?(volume|som)|volume (mais )?(alto|maior)|mais (alto|volume)", t):
            return _cmd(raw, "audio.volume", direction="up")
        if re.search(r"(diminu|abaix)\w* (o )?(volume|som)|volume (mais )?(baixo|menor)|mais baixo", t):
            return _cmd(raw, "audio.volume", direction="down")
        if re.search(r"\b(mudo|silenciar|silencie|tirar o som)\b", t):
            return _cmd(raw, "audio.volume", direction="mute")
        if re.search(r"proxim[ao] (musica|faixa)|pular (musica|faixa)", t):
            return _cmd(raw, "audio.media", action="next")
        if re.search(r"(musica|faixa) anterior|voltar (a )?(musica|faixa)", t):
            return _cmd(raw, "audio.media", action="previous")
        if re.search(r"\b(pausar|pause|pausa)\b( a)? (musica|video|reproducao)|tocar musica|continuar (a )?(musica|reproducao)|"
                     r"^(pausar|pause|play|tocar)$", t):
            return _cmd(raw, "audio.media", action="play_pause")
        return None

    def _input_rules(self, raw, t):
        m = re.match(r"^(?:mover|mova|movimentar)\s+(?:(?:o\s+)?mouse|cursor)\s+(?:para\s+)?(?:x\s*)?(\d+)\s*(?:,\s*|\s+)(?:y\s*)?(\d+)$", t)
        if m:
            return _cmd(raw, "input.move_mouse", x=int(m.group(1)), y=int(m.group(2)))
        if re.search(r"duplo clique|clique duplo|clicar duas vezes", t):
            return _cmd(raw, "input.click", button="double")
        if re.search(r"clique (?:com )?(?:o )?botao direito|clique direito|clicar com (o )?botao direito", t):
            return _cmd(raw, "input.click", button="right")
        if re.fullmatch(r"(clicar|clique|clica|clique esquerdo)", t):
            return _cmd(raw, "input.click", button="left")
        if re.search(r"rol\w* (a pagina )?(para )?baixo|descer a pagina", t):
            return _cmd(raw, "input.scroll", direction="down", amount=3)
        if re.search(r"rol\w* (a pagina )?(para )?cima|subir a pagina", t):
            return _cmd(raw, "input.scroll", direction="up", amount=3)
        m = re.match(r"(?i)^(?:digitar|digite|digita|escrever|escreva)\s+(.+)$", raw.strip())
        if m:
            return _cmd(raw, "input.type_text", text=m.group(1))
        m = re.match(r"^(?:apertar|aperte|aperta|pressionar|pressione|tecle)\s+(?:a tecla\s+)?(.+)$", t)
        if m:
            return _cmd(raw, "input.press_key", key=m.group(1).replace(" mais ", "+").replace(" ", ""))
        return None
