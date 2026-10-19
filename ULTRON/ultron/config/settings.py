"""Configuração do JARVIS.

Ordem de carga (a última vence):

1. valores padrão desta classe;
2. perfil escolhido (``profiles.py``);
3. ``settings.json`` na pasta de dados do usuário (migrado da identidade ULTRON, se preciso);
4. variáveis de ambiente ``JARVIS_<CAMPO>`` ou, por compatibilidade, ``ULTRON_<CAMPO>``
   (ex.: ``JARVIS_MODEL=qwen2.5:7b``).

Todo valor passa por validação: campos desconhecidos são ignorados e números fora da faixa
são limitados. A configuração nunca guarda credenciais.

Migração de identidade (versão 2): só os campos que eram IDENTIDADE do ULTRON mudam —
palavra de ativação "ultron" → "jarvis" (variantes do ULTRON trocadas pelas do JARVIS; formas
calibradas pelo usuário que não são do ULTRON são mantidas), tema dourado → azul e perfil
"performance" → "economy". Antes de regravar, uma cópia do arquivo original é guardada em
``settings.ultron-backup.json``. Preferências pessoais (microfone, volume, modelos, horários…)
não são tocadas.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger("ultron.config")
_QUIET_RE = re.compile(r"([01]?\d|2[0-3]):[0-5]\d-([01]?\d|2[0-3]):[0-5]\d")

AUTONOMY_LEVELS = ("restricted", "balanced", "autonomous")
PERFORMANCE_PROFILES = ("economy", "balanced", "high", "cinematic")
LEGACY_PROFILES = {"performance": "economy"}           # nome antigo (ULTRON) → nome atual
PRIVACY_MODES = ("local", "standard")
THEMES = ("jarvis-blue",)
STT_ENGINES = ("auto", "vosk-large", "vosk-small")
MIC_BACKENDS = ("auto", "pyaudio", "sounddevice")
SETTINGS_VERSION = 2                                   # 2 = identidade JARVIS

DEFAULT_WAKE_VARIANTS = ("jarvis", "javis", "ja vis", "jar vis", "jarvis jarvis")
# Nomes próprios que soam como "Jarvis": fortes só no início da frase.
DEFAULT_WAKE_NAMES = ("jarbas", "javi")
# Confusões com palavras comuns (medidas): só ativam seguidas de um comando reconhecido.
DEFAULT_WEAK_WAKE_VARIANTS = ("aviso", "aves", "a vez", "ja vi", "e vi", "davis", "travis", "avis")
LEGACY_WAKE_VARIANTS = ("ultron", "ultrom", "ultrão", "ultrao", "últron", "ultrón", "altron", "ultro",
                        "ul tron", "u tron", "ultrone", "outron")
LEGACY_WEAK_WAKE_VARIANTS = ("o tom", "o trom", "o tron", "u tom", "u trom", "ultra", "outro", "autor")


@dataclass
class Settings:
    # ------------------------------------------------------------ modelos
    model: str = "qwen2.5:3b"
    vision_model: str = "qwen2.5vl:3b"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_autostart: bool = True
    llm_timeout: float = 120.0
    llm_temperature: float = 0.4
    max_agent_steps: int = 8
    max_tool_calls: int = 10
    # ------------------------------------------------------------ voz
    voice: str = "pt_BR-faber-medium"
    volume: float = 0.9
    speech_speed: float = 0.9
    voice_enabled: bool = True
    voice_profile: str = "jarvis"          # jarvis (masculina, grave, natural) | neutral
    stt_engine: str = "auto"
    wake_words: tuple = ("jarvis",)
    wake_variants: tuple = DEFAULT_WAKE_VARIANTS
    wake_names: tuple = DEFAULT_WAKE_NAMES
    wake_weak_variants: tuple = DEFAULT_WEAK_WAKE_VARIANTS
    mic_backend: str = "auto"              # auto (PyAudio, depois sounddevice) | pyaudio | sounddevice
    mic_name: str = ""
    mic_index: int = -1
    followup_seconds: float = 12.0
    # ------------------------------------------------------------ memória
    memory: bool = True
    consolidation_interval: float = 300.0
    # ------------------------------------------------------------ percepção
    screen_observation: bool = True
    vision_interval: float = 20.0
    window_interval: float = 1.0
    process_interval: float = 5.0
    system_interval: float = 2.0
    device_interval: float = 30.0
    filesystem_interval: float = 10.0
    watch_dirs: tuple = ()
    excluded_apps: tuple = ()
    # ------------------------------------------------------------ rede
    network_interval: float = 30.0
    network_discovery: bool = True
    network_ssdp: bool = False             # anúncios SSDP/UPnP (opcional): nomes de TVs, impressoras, roteadores
    discovery_interval: float = 600.0
    discovery_max_hosts: int = 256
    # ------------------------------------------------------------ privacidade e autonomia
    privacy_mode: str = "local"
    allow_external_models: bool = False
    autonomy_level: str = "balanced"
    proactive: bool = True
    authorization_timeout: float = 30.0
    # ------------------------------------------------------------ imaginação
    image_provider: str = "auto"
    dream_mode: bool = True
    dream_idle_minutes: float = 15.0
    # ------------------------------------------------------------ second brain e lembretes
    second_brain: bool = True
    auto_capture: bool = True            # registra sozinho tarefas/lembretes com intenção clara (reversível)
    reminders: bool = True
    reminder_default_leads: tuple = ("10",)   # minutos de antecedência padrão p/ compromissos (ex.: 10, 60, 1440)
    reminder_repeat_minutes: float = 10.0     # um lembrete ignorado é repetido após este intervalo...
    reminder_max_repeats: int = 2             # ...no máximo esta quantidade de vezes (nunca indefinidamente)
    overdue_alerts: bool = True               # aviso diário de tarefas atrasadas
    notifications_muted: bool = False
    quiet_hours: str = ""                     # "22:00-07:00": sem som, voz ou pop-up (fica na central)
    timezone: str = ""                        # vazio = fuso do sistema; ou IANA (ex.: America/Sao_Paulo)
    # ------------------------------------------------------------ interface e som
    theme: str = "jarvis-blue"
    performance_profile: str = "balanced"     # economy | balanced | high | cinematic (custo visual)
    ambient_sound: bool = False               # som ambiente discreto do TARDIS (desligado por padrão)
    hud_fps: int = 60
    hud_start_minimized: bool = False
    hud_auto_expand: bool = True
    sound_effects: bool = True
    sfx_volume: float = 0.35
    # ------------------------------------------------------------ plugins
    plugins: bool = True
    plugins_enabled: tuple = ()          # plugins desativados por padrão que o usuário ativou
    plugins_disabled: tuple = ()
    # ------------------------------------------------------------ sistema
    startup: bool = False
    debug: bool = False
    profile: str = "default"
    settings_version: int = SETTINGS_VERSION

    # Faixas numéricas aceitas.
    _RANGES = {
        "llm_timeout": (5.0, 600.0), "llm_temperature": (0.0, 1.5),
        "max_agent_steps": (1, 25), "max_tool_calls": (1, 40),
        "volume": (0.0, 1.0), "speech_speed": (0.6, 1.4), "followup_seconds": (0.0, 120.0),
        "consolidation_interval": (30.0, 86400.0), "vision_interval": (5.0, 3600.0),
        "window_interval": (0.25, 30.0), "process_interval": (1.0, 120.0),
        "system_interval": (0.5, 60.0), "device_interval": (5.0, 3600.0),
        "filesystem_interval": (2.0, 3600.0), "network_interval": (5.0, 3600.0),
        "discovery_interval": (60.0, 86400.0), "discovery_max_hosts": (1, 1024),
        "authorization_timeout": (5.0, 300.0), "dream_idle_minutes": (1.0, 1440.0),
        "hud_fps": (15, 144), "sfx_volume": (0.0, 1.0), "mic_index": (-1, 64),
        "reminder_repeat_minutes": (1.0, 1440.0), "reminder_max_repeats": (0, 10),
    }
    _CHOICES = {
        "autonomy_level": AUTONOMY_LEVELS, "privacy_mode": PRIVACY_MODES,
        "theme": THEMES, "stt_engine": STT_ENGINES, "performance_profile": PERFORMANCE_PROFILES,
        "mic_backend": MIC_BACKENDS, "voice_profile": ("jarvis", "neutral"),
    }

    # ------------------------------------------------------------ utilidades
    @classmethod
    def field_names(cls) -> set[str]:
        return {f.name for f in fields(cls)}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, tuple):
                data[key] = list(value)
        return data

    def apply(self, values: dict[str, Any], *, source: str = "") -> list[str]:
        """Aplica valores validados. Devolve a lista de campos alterados."""
        changed = []
        names = self.field_names()
        for key, raw in (values or {}).items():
            if key not in names:
                log.debug("campo de configuração ignorado (%s): %s", source, key)
                continue
            try:
                value = self._coerce(key, raw)
            except (TypeError, ValueError) as exc:
                log.warning("valor inválido para %s (%s): %s", key, source, exc)
                continue
            if getattr(self, key) != value:
                setattr(self, key, value)
                changed.append(key)
        return changed

    def _coerce(self, key: str, raw: Any) -> Any:
        current = getattr(self, key)
        if isinstance(current, bool):
            if isinstance(raw, str):
                value = raw.strip().lower() in ("1", "true", "sim", "yes", "on")
            else:
                value = bool(raw)
        elif isinstance(current, int) and not isinstance(current, bool):
            value = int(float(raw))
        elif isinstance(current, float):
            value = float(raw)
        elif isinstance(current, tuple):
            if isinstance(raw, str):
                raw = [x for x in raw.split(",")]
            value = tuple(str(x).strip() for x in raw if str(x).strip())
        else:
            value = str(raw).strip()
        if key == "performance_profile":
            value = LEGACY_PROFILES.get(value, value)
        if key in self._RANGES:
            low, high = self._RANGES[key]
            value = type(value)(max(low, min(high, value)))
        if key in self._CHOICES and value not in self._CHOICES[key]:
            raise ValueError(f"{value!r} não está em {self._CHOICES[key]}")
        if key in ("model", "vision_model") and not value:
            raise ValueError("nome de modelo vazio")
        if key == "ollama_url" and not str(value).startswith(("http://", "https://")):
            raise ValueError("URL do Ollama deve começar com http:// ou https://")
        if key == "quiet_hours" and value and not _QUIET_RE.fullmatch(str(value)):
            raise ValueError("horário de silêncio no formato HH:MM-HH:MM")
        if key == "reminder_default_leads":
            value = tuple(str(int(float(x))) for x in value if 0 < float(x) <= 43200)
        if key == "timezone" and value:
            from ..secondbrain import timeutil
            if timeutil.zone(str(value)) is None:
                raise ValueError(f"fuso horário desconhecido: {value}")
        return value


def _close_to_ultron(form: str) -> bool:
    import difflib
    import unicodedata
    value = unicodedata.normalize("NFD", str(form).casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn").replace(" ", "")
    return difflib.SequenceMatcher(None, value, "ultron").ratio() >= 0.6


def migrate(stored: dict) -> tuple[dict, list[str]]:
    """Migra um settings.json da identidade ULTRON (versão 1) para JARVIS (versão 2)."""
    stored = dict(stored or {})
    try:
        version = int(stored.get("settings_version", 1))
    except (TypeError, ValueError):
        version = 1
    if version >= SETTINGS_VERSION or not stored:
        return stored, []
    notes: list[str] = []
    words = [str(w) for w in stored.get("wake_words") or []]
    if words:
        new_words = ["jarvis" if _close_to_ultron(w) else w for w in words]
        new_words = list(dict.fromkeys(new_words))
        if new_words != words:
            stored["wake_words"] = new_words
            notes.append("palavra de ativação ultron → jarvis")
    variants = [str(v) for v in stored.get("wake_variants") or []]
    if variants:
        kept = [v for v in variants if v not in LEGACY_WAKE_VARIANTS and not _close_to_ultron(v)]
        stored["wake_variants"] = list(dict.fromkeys(list(DEFAULT_WAKE_VARIANTS) + kept))
        if len(kept) != len(variants):
            notes.append("variantes do ULTRON trocadas pelas do JARVIS")
    weak = [str(v) for v in stored.get("wake_weak_variants") or []]
    if weak:
        kept = [v for v in weak if v not in LEGACY_WEAK_WAKE_VARIANTS and not _close_to_ultron(v)]
        stored["wake_weak_variants"] = list(dict.fromkeys(list(DEFAULT_WEAK_WAKE_VARIANTS) + kept))
        if len(kept) != len(weak):
            notes.append("formas fracas do ULTRON trocadas pelas do JARVIS")
    if stored.get("theme") not in (None, *THEMES):
        stored["theme"] = THEMES[0]
        notes.append("tema dourado → azul JARVIS")
    if stored.get("performance_profile") in LEGACY_PROFILES:
        stored["performance_profile"] = LEGACY_PROFILES[stored["performance_profile"]]
        notes.append("perfil performance → economy")
    stored["settings_version"] = SETTINGS_VERSION
    return stored, notes or ["versão das configurações atualizada"]


class SettingsManager:
    """Carrega, valida, persiste e notifica mudanças de configuração."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else paths.data_file("settings.json")
        self._lock = threading.RLock()
        self._listeners: list = []
        self.settings = Settings()
        self.migration_notes: list[str] = []

    def load(self, profile: str | None = None) -> Settings:
        from . import profiles

        with self._lock:
            settings = Settings()
            stored: dict[str, Any] = {}
            if self.path.is_file():
                try:
                    stored = json.loads(self.path.read_text(encoding="utf-8")) or {}
                except (OSError, ValueError) as exc:
                    log.warning("settings.json ilegível (%s); usando padrões", exc)
                    stored = {}
            stored, notes = migrate(stored)
            if notes and self.path.is_file():
                self._backup_and_rewrite(stored, notes)
            chosen = (profile or os.environ.get("JARVIS_PROFILE") or os.environ.get("ULTRON_PROFILE")
                      or stored.get("profile") or "default")
            settings.apply(profiles.get(chosen), source=f"perfil {chosen}")
            settings.apply(stored, source="settings.json")
            if profile:
                settings.profile = profile
            env = {}
            for name in Settings.field_names():
                value = os.environ.get("JARVIS_" + name.upper(), os.environ.get("ULTRON_" + name.upper()))
                if value is not None:
                    env[name] = value
            settings.apply(env, source="ambiente")
            self.settings = settings
            self.migration_notes = notes
            return settings

    def _backup_and_rewrite(self, stored: dict, notes: list[str]) -> None:
        """Guarda o arquivo original e grava a versão migrada (só campos de identidade mudam)."""
        backup = self.path.with_name("settings.ultron-backup.json")
        try:
            if not backup.exists():
                backup.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            log.info("configurações migradas para a identidade JARVIS: %s (cópia em %s)", "; ".join(notes),
                     backup.name)
        except OSError as exc:
            log.warning("não foi possível regravar settings.json migrado (%s); a migração vale só nesta sessão",
                        exc)

    def save(self) -> None:
        with self._lock:
            payload = self.settings.to_dict()
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    def update(self, **values: Any) -> list[str]:
        with self._lock:
            changed = self.settings.apply(values, source="runtime")
            if changed:
                self.save()
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(changed, self.settings)
            except Exception:  # um ouvinte com erro não impede os demais
                log.exception("ouvinte de configuração falhou")
        return changed

    def on_change(self, callback) -> None:
        with self._lock:
            self._listeners.append(callback)


_manager: SettingsManager | None = None
_manager_lock = threading.Lock()


def manager() -> SettingsManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = SettingsManager()
            _manager.load()
        return _manager


def get() -> Settings:
    return manager().settings
