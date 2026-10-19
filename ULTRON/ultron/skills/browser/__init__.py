"""Skills de navegador: abrir endereços e pesquisar.

Somente HTTP/HTTPS, sem credenciais embutidas na URL. Abrir uma página no navegador é ação
do usuário (não é uma conexão do próprio JARVIS).
"""
from __future__ import annotations

import re
import webbrowser
from urllib.parse import quote_plus, urlsplit

from .._util import processes_named, wait_until
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string

BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "chrome", "firefox",
                     "chromium", "chromium-browser", "google-chrome", "brave"}


def validate_url(value: str) -> str:
    value = value.strip()
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError("somente endereços HTTP ou HTTPS válidos")
    if parsed.username or parsed.password:
        raise ValueError("endereços com credenciais não são aceitos")
    return value


class _BrowserSkill(Skill):
    category = "browser"

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        running = wait_until(lambda: processes_named(BROWSER_PROCESSES), timeout=6.0, ctx=ctx)
        return VerificationResult.from_checks(
            [check("browser_running", bool(running) or None,
                   f"navegador ativo ({running[0]['name']})" if running else "processo do navegador não identificado")],
            unconfirmed_reason="o navegador padrão não pôde ser identificado")


class OpenUrl(_BrowserSkill):
    name = "web.open_url"
    description = "Abrir um endereço HTTP/HTTPS no navegador."
    inputs = schema({"url": string(1500)}, ("url",))
    risk = Risk.LOW

    def validate(self, args):
        args = super().validate(args)
        args["url"] = validate_url(args["url"])
        return args

    def execute(self, ctx, url: str) -> SkillResult:
        if not webbrowser.open(url, new=2):
            return SkillResult(False, error="nenhum navegador disponível", error_kind="APPLICATION_ERROR")
        return SkillResult(True, f"Abrindo {urlsplit(url).hostname}.", [url], {"url": url})


class WebSearch(_BrowserSkill):
    name = "web.search"
    description = "Pesquisar na web (Google ou YouTube)."
    inputs = schema({"query": string(300), "site": string(10, enum=["google", "youtube"])}, ("query",))
    risk = Risk.LOW

    def execute(self, ctx, query: str, site: str = "google") -> SkillResult:
        q = quote_plus(query)
        url = (f"https://www.youtube.com/results?search_query={q}" if site == "youtube"
               else f"https://www.google.com/search?q={q}")
        if not webbrowser.open(url, new=2):
            return SkillResult(False, error="nenhum navegador disponível", error_kind="APPLICATION_ERROR")
        return SkillResult(True, f"Pesquisando '{query}' no {site}.", [url], {"url": url})


SKILLS = (OpenUrl, WebSearch)
