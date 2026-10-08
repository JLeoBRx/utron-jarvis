"""Extração de conceitos a partir de texto real (falas, objetivos, observações).

Determinística e local: um léxico de termos conhecidos, nomes de projetos, termos entre
aspas e nomes próprios. O resultado alimenta o Neural Graph — é assim que o cérebro cresce
com o que o usuário realmente fala e faz ("Python" → PYTHON → PROJECT → TERMINAL...).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .neural_graph import normalize

# termo normalizado -> (rótulo, tipo de nó)
LEXICON: dict[str, tuple[str, str]] = {
    "python": ("Python", "CONCEPT"), "javascript": ("JavaScript", "CONCEPT"),
    "typescript": ("TypeScript", "CONCEPT"), "java": ("Java", "CONCEPT"), "c#": ("C#", "CONCEPT"),
    "c++": ("C++", "CONCEPT"), "rust": ("Rust", "CONCEPT"), "golang": ("Go", "CONCEPT"),
    "html": ("HTML", "CONCEPT"), "css": ("CSS", "CONCEPT"), "sql": ("SQL", "CONCEPT"),
    "react": ("React", "CONCEPT"), "node": ("Node.js", "CONCEPT"), "nodejs": ("Node.js", "CONCEPT"),
    "git": ("Git", "CONCEPT"), "github": ("GitHub", "CONCEPT"), "docker": ("Docker", "CONCEPT"),
    "linux": ("Linux", "CONCEPT"), "windows": ("Windows", "CONCEPT"),
    "ollama": ("Ollama", "CONCEPT"), "qwen": ("Qwen", "CONCEPT"),
    "arduino": ("Arduino", "CONCEPT"), "esp32": ("ESP32", "CONCEPT"), "unity": ("Unity", "CONCEPT"),
    "pip": ("pip", "CONCEPT"), "venv": ("Ambiente virtual", "CONCEPT"),
    "ambiente virtual": ("Ambiente virtual", "CONCEPT"), "dependencia": ("Dependências", "CONCEPT"),
    "dependencias": ("Dependências", "CONCEPT"), "biblioteca": ("Bibliotecas", "CONCEPT"),
    "erro": ("Erro", "CONCEPT"), "bug": ("Erro", "CONCEPT"), "exception": ("Erro", "CONCEPT"),
    "traceback": ("Erro", "CONCEPT"), "modulenotfounderror": ("ModuleNotFoundError", "CONCEPT"),
    "importerror": ("ImportError", "CONCEPT"), "debug": ("Debugging", "CONCEPT"),
    "depurar": ("Debugging", "CONCEPT"), "depuracao": ("Debugging", "CONCEPT"),
    "teste": ("Testes", "CONCEPT"), "testes": ("Testes", "CONCEPT"),
    "terminal": ("Terminal", "APPLICATION"), "powershell": ("PowerShell", "APPLICATION"),
    "vs code": ("VS Code", "APPLICATION"), "vscode": ("VS Code", "APPLICATION"),
    "visual studio code": ("VS Code", "APPLICATION"), "chrome": ("Chrome", "APPLICATION"),
    "edge": ("Edge", "APPLICATION"), "navegador": ("Navegador", "APPLICATION"),
    "spotify": ("Spotify", "APPLICATION"), "discord": ("Discord", "APPLICATION"),
    "word": ("Word", "APPLICATION"), "excel": ("Excel", "APPLICATION"),
    "explorador de arquivos": ("Explorador de Arquivos", "APPLICATION"),
    "arquivo": ("Sistema de arquivos", "CONCEPT"), "arquivos": ("Sistema de arquivos", "CONCEPT"),
    "pasta": ("Sistema de arquivos", "CONCEPT"),
    "rede": ("Rede", "CONCEPT"), "wi-fi": ("Wi-Fi", "CONCEPT"), "wifi": ("Wi-Fi", "CONCEPT"),
    "internet": ("Internet", "CONCEPT"), "dns": ("DNS", "CONCEPT"), "gateway": ("Gateway", "CONCEPT"),
    "roteador": ("Roteador", "DEVICE"), "impressora": ("Impressora", "DEVICE"),
    "camera": ("Câmera", "DEVICE"), "microfone": ("Microfone", "DEVICE"),
    "teclado": ("Teclado", "DEVICE"), "mouse": ("Mouse", "DEVICE"), "monitor": ("Monitor", "DEVICE"),
    "memoria": ("Memória", "CONCEPT"), "visao": ("Visão", "CONCEPT"), "voz": ("Voz", "CONCEPT"),
    "cidade": ("Cidade", "CONCEPT"), "mundo": ("Mundo", "CONCEPT"), "arquitetura": ("Arquitetura", "CONCEPT"),
    "biologia": ("Biologia", "CONCEPT"), "espaco": ("Espaço", "CONCEPT"), "musica": ("Música", "CONCEPT"),
    "inteligencia artificial": ("Inteligência artificial", "CONCEPT"), "ia": ("Inteligência artificial", "CONCEPT"),
}

_PROJECT_RE = re.compile(r"\b[Pp]rojeto\s+([A-Za-zÀ-ÿ0-9_.\-]{2,40}(?:\s+[A-Z][A-Za-zÀ-ÿ0-9_.\-]{1,30})?)")
_QUOTED_RE = re.compile(r"[\"“']([^\"”']{2,48})[\"”']")
_PROPER_RE = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-zà-ÿ]{2,}(?:\s+[A-Z][a-zà-ÿ]{2,}){0,2})\b")
_STOP_PROPER = {"Ultron", "Senhor", "Entendido", "Analisando", "Concluído", "Windows", "Eu", "Você"}
_PROJECT_STOP = {"de", "do", "da", "que", "e", "o", "a", "em", "para", "com", "meu", "minha", "esse", "este"}


@dataclass(frozen=True)
class ConceptMention:
    label: str
    type: str
    source: str            # lexicon | project | quoted | proper


def extract(text: str, *, max_items: int = 12) -> list[ConceptMention]:
    raw = str(text or "")
    norm = " " + normalize(raw) + " "
    found: dict[str, ConceptMention] = {}

    def add(label: str, type_: str, source: str) -> None:
        key = f"{type_}:{normalize(label)}"
        if key not in found and len(found) < max_items:
            found[key] = ConceptMention(label, type_, source)

    masked = raw
    for term, (label, type_) in sorted(LEXICON.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![\w#+]){re.escape(term)}(?![\w#+])", norm):
            add(label, type_, "lexicon")
            masked = re.sub(rf"(?<![\w#+]){re.escape(term)}(?![\w#+])", " ", masked, flags=re.I)
    for match in _PROJECT_RE.finditer(raw):
        name = match.group(1).strip(" .,;:")
        if name and normalize(name) not in _PROJECT_STOP:
            add(name, "PROJECT", "project")
            masked = masked.replace(name, " ")
    for match in _QUOTED_RE.finditer(raw):
        add(match.group(1).strip(), "CONCEPT", "quoted")
        masked = masked.replace(match.group(1), " ")
    for match in _PROPER_RE.finditer(masked):
        name = match.group(1).strip()
        if name not in _STOP_PROPER and normalize(name) not in LEXICON:
            add(name, "CONCEPT", "proper")
    return list(found.values())
