"""Configuração do gateway pelo ambiente (segredos vêm do gerenciador de segredos do servidor, nunca do código).

Variáveis (ver ``.env.example``):

* ``JARVIS_PUBLIC_URL``         endereço público do site (ex.: https://orb.seudominio.com) — origem aceita no WebSocket
                               e base dos links de pareamento;
* ``JARVIS_ENROLL_SECRET_HASH`` hash scrypt do segredo de inscrição do agente (``python -m jarvis_gateway hash-secret``);
                               sem ele, nenhuma matriz-mãe consegue se inscrever;
* ``JARVIS_GATEWAY_DB``         banco do gateway (padrão ``./data/gateway.sqlite3``);
* ``JARVIS_SCENE_DIR``          pasta da cena 3D do JARVIS (módulos da ORBE e Three.js);
* ``JARVIS_HOST``/``JARVIS_PORT`` endereço local de escuta (atrás do proxy HTTPS);
* ``JARVIS_TRUST_PROXY``        1 = usar X-Forwarded-For (só atrás do proxy do compose);
* ``JARVIS_DEVICE_DAYS``        validade da sessão de um dispositivo pareado (padrão 30);
* ``JARVIS_PAIR_TTL``           validade de um código de pareamento em segundos (padrão 300);
* ``JARVIS_DEV_INSECURE``       1 = cookies sem "Secure" — aceito SOMENTE com endereço público local (127.0.0.1/localhost).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_SCENE = PACKAGE_DIR.parents[1] / "ultron" / "hud" / "scene3d" / "web"


@dataclass
class Config:
    public_url: str = "http://127.0.0.1:8080"
    enroll_secret_hash: str = ""
    db_path: str = "./data/gateway.sqlite3"
    scene_dir: Path = field(default_factory=lambda: DEFAULT_SCENE)
    host: str = "127.0.0.1"
    port: int = 8080
    trust_proxy: bool = False
    device_days: float = 30.0
    pair_ttl: float = 300.0
    dev_insecure: bool = False

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = os.environ if env is None else env
        flag = lambda name: str(env.get(name, "")).strip() in ("1", "true", "sim", "yes")   # noqa: E731
        cfg = cls(public_url=str(env.get("JARVIS_PUBLIC_URL", cls.public_url)).rstrip("/"),
                  enroll_secret_hash=str(env.get("JARVIS_ENROLL_SECRET_HASH", "")),
                  db_path=str(env.get("JARVIS_GATEWAY_DB", cls.db_path)),
                  scene_dir=Path(env.get("JARVIS_SCENE_DIR", DEFAULT_SCENE)),
                  host=str(env.get("JARVIS_HOST", cls.host)), port=int(env.get("JARVIS_PORT", cls.port)),
                  trust_proxy=flag("JARVIS_TRUST_PROXY"),
                  device_days=float(env.get("JARVIS_DEVICE_DAYS", cls.device_days)),
                  pair_ttl=float(env.get("JARVIS_PAIR_TTL", cls.pair_ttl)), dev_insecure=flag("JARVIS_DEV_INSECURE"))
        cfg.validate()
        return cfg

    @property
    def origin(self) -> str:
        parts = urlsplit(self.public_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def local_only(self) -> bool:
        return urlsplit(self.public_url).hostname in ("127.0.0.1", "localhost", "::1")

    @property
    def secure_cookies(self) -> bool:
        return not (self.dev_insecure and self.local_only)

    def validate(self) -> None:
        parts = urlsplit(self.public_url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("JARVIS_PUBLIC_URL inválido (ex.: https://orb.seudominio.com)")
        if parts.scheme == "http" and not self.local_only:
            raise ValueError("JARVIS_PUBLIC_URL precisa ser HTTPS fora do computador local")
        if self.dev_insecure and not self.local_only:
            raise ValueError("JARVIS_DEV_INSECURE só é aceito com endereço público local (127.0.0.1/localhost)")
