"""Gera ``COMANDOS_JARVIS.md`` — a referência das ações (skills) que o JARVIS sabe executar — a partir do
registro real de skills. Nada é escrito à mão: nome, descrição, risco, categoria de permissão e requisitos
vêm do próprio código, e ``tests/test_cli.py`` confere que o arquivo está em dia.

    python tools/gerar_comandos.py            regrava COMANDOS_JARVIS.md
    python tools/gerar_comandos.py --check    só confere (código 1 se estiver desatualizado)
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import unicodedata
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
TARGET = PROJECT / "COMANDOS_JARVIS.md"

RISK = {"none": "nenhum", "low": "baixo", "medium": "moderado", "high": "alto", "critical": "crítico"}
GROUPS = {
    "activity": "Histórico de atividades", "app": "Aplicativos", "audio": "Áudio e mídia",
    "automation": "Automações", "autonomy": "Autonomia e autorizações", "dev": "Desenvolvimento",
    "devices": "Periféricos", "diagnostics": "Diagnóstico", "fs": "Arquivos e pastas", "imagination": "Imaginação",
    "input": "Teclado e mouse", "jarvis": "O próprio JARVIS",
    "memory": "Memória e preferências", "network": "Rede local", "noctario": "Noctário (robô)",
    "secondbrain": "Memória pessoal (segundo cérebro)", "system": "Sistema", "tardis": "TARDIS",
    "vision": "Tela e visão", "voice": "Voz", "web": "Navegador e web", "window": "Janelas",
}

HEADER = """# JARVIS — Referência de comandos (ações executáveis)

Gerado por `tools/gerar_comandos.py` a partir do registro real de skills (`ultron/skills/`); não edite à
mão. São **{total} ações** em {groups} grupos. Você não chama estes nomes: fala ou digita o pedido ("abra o
bloco de notas", "anote uma ideia…", "pare o Noctário") e o JARVIS escolhe a ação — os exemplos de frases
estão no `README_JARVIS.md` (§§ 4–7) e o mapa dos comandos do JARVIS original em
`docs/inventario/comandos.md`.

Como cada ação passa pelo executor (`ultron/agent/execution.py`), na ordem: validação estrita dos
argumentos → recusa antecipada (ex.: pastas protegidas — nem um "sim" libera) → pré-condições → autonomia
pelo risco e permissão da categoria → autorização quando exigida → execução → **verificação independente**
do resultado. Nomes fora deste registro (shell, PowerShell, `eval`, desligar Defender/Firewall/UAC…) são
recusados antes de qualquer coisa.

Colunas: **risco** (base; algumas ações sobem o risco conforme os argumentos); **permissão** — a categoria
em CONFIGURAÇÕES > PERMISSÕES ({labels}); **modelo** — "sim" se o modelo de linguagem pode escolher a
ação sozinho num passo agêntico; "não" = só por pedido direto seu; **requer** — sistema ou biblioteca
necessários (sem eles a ação responde que está indisponível, não finge).
"""


def _skills():
    os.environ.setdefault("JARVIS_DATA_DIR", tempfile.mkdtemp(prefix="jarvis-comandos-"))
    sys.path.insert(0, str(PROJECT))
    from ultron.agent.permissions import LABELS, category_for
    from ultron.skills import SkillRegistry, load_builtin
    return load_builtin(SkillRegistry()).all(), LABELS, category_for


def _sort_key(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn")


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def render() -> str:
    skills, labels, category_for = _skills()
    groups: dict[str, list] = {}
    for skill in skills:
        groups.setdefault(skill.name.split(".", 1)[0], []).append(skill)
    label_text = ", ".join(f"*{label}*" for label in labels.values())
    lines = [HEADER.format(total=len(skills), groups=len(groups), labels=label_text).rstrip(), ""]
    for prefix in sorted(groups, key=lambda key: _sort_key(GROUPS.get(key, key))):
        lines += [f"## {GROUPS.get(prefix, prefix)}", "",
                  "| Ação | O que faz | Risco | Permissão | Modelo | Requer |", "|---|---|---|---|---|---|"]
        for skill in groups[prefix]:
            if getattr(skill, "emergency", False):
                permission = "parada de emergência: nunca bloqueada nem condicionada"
            else:
                permission = labels.get(category_for(skill, {}), "—")
            req = skill.requirements or {}
            needs = [{"win32": "Windows"}.get(req.get("platform"), req.get("platform"))] if req.get("platform") else []
            needs += list(req.get("modules", ())) + list(req.get("executables", ()))
            lines.append(f"| `{skill.name}` | {_cell(skill.description)} | {RISK.get(skill.risk.value, skill.risk.value)}"
                         f" | {permission} | {'sim' if skill.expose_to_llm else 'não'} | {', '.join(needs) or '—'} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="só confere se o arquivo está em dia")
    args = parser.parse_args(argv)
    text = render()
    current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
    if args.check:
        if current != text:
            print(f"{TARGET.name} desatualizado: rode python tools/gerar_comandos.py")
            return 1
        print(f"{TARGET.name} em dia.")
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"{TARGET.name}: {text.count(chr(10) + '| `')} ações")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
