"""GENERATIVE IMAGE PIPELINE — IDEIA → CONCEITO → PROMPT → MODELO DE IMAGEM → IMAGEM → MEMÓRIA.

Provedores (detectados de verdade, nunca presumidos):

* ``webui``    — Stable Diffusion WebUI local (Automatic1111/Forge) em 127.0.0.1:7860;
* ``diffusers``— modelo local via biblioteca ``diffusers`` (pasta configurada em
                 ``ULTRON_IMAGE_MODEL_DIR``);
* provedores externos podem ser registrados por plugins e só são usados se a
  política de privacidade permitir.

Sem provedor disponível, ``generate`` levanta ``ImageUnavailable`` com a explicação.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import logging
import os
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from ..config import paths

log = logging.getLogger("ultron.images")


class ImageUnavailable(RuntimeError):
    pass


@dataclass
class ImageRecord:
    id: str
    path: str
    prompt: str
    provider: str
    concept_id: str | None
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WebUIProvider:
    name = "webui"
    external = False

    def __init__(self, url: str = "http://127.0.0.1:7860"):
        self.url = url.rstrip("/")

    def available(self) -> tuple[bool, str]:
        try:
            with urllib.request.urlopen(self.url + "/sdapi/v1/sd-models", timeout=1.5) as response:
                models = json.loads(response.read().decode("utf-8"))
            return (bool(models), "" if models else "WebUI sem modelos carregados")
        except Exception:
            return False, "Stable Diffusion WebUI não encontrado em 127.0.0.1:7860"

    def generate(self, prompt: str, *, width: int = 768, height: int = 512, steps: int = 24, cancel=None) -> bytes:
        payload = {"prompt": prompt, "negative_prompt": "text, watermark, blurry, low quality", "width": width,
                   "height": height, "steps": steps, "cfg_scale": 6.5}
        req = urllib.request.Request(self.url + "/sdapi/v1/txt2img", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as response:
            data = json.loads(response.read().decode("utf-8"))
        images = data.get("images") or []
        if not images:
            raise RuntimeError("o WebUI não devolveu imagem")
        return base64.b64decode(images[0].split(",", 1)[-1])


class DiffusersProvider:
    name = "diffusers"
    external = False

    def __init__(self, model_dir: str | None = None):
        self.model_dir = model_dir or os.environ.get("ULTRON_IMAGE_MODEL_DIR", "")
        self._pipe = None

    def available(self) -> tuple[bool, str]:
        if importlib.util.find_spec("diffusers") is None or importlib.util.find_spec("torch") is None:
            return False, "biblioteca diffusers/torch não instalada"
        if not self.model_dir or not Path(self.model_dir).is_dir():
            return False, "ULTRON_IMAGE_MODEL_DIR não aponta para um modelo local"
        return True, ""

    def generate(self, prompt: str, *, width: int = 768, height: int = 512, steps: int = 24, cancel=None) -> bytes:
        import io

        import torch
        from diffusers import AutoPipelineForText2Image
        if self._pipe is None:
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            self._pipe = AutoPipelineForText2Image.from_pretrained(self.model_dir, torch_dtype=dtype,
                                                                   local_files_only=True)
            self._pipe.to("cuda" if torch.cuda.is_available() else "cpu")
        image = self._pipe(prompt, width=width, height=height, num_inference_steps=steps).images[0]
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


class ImagePipeline:
    name = "images"

    def __init__(self, *, db=None, graph=None, bus=None, privacy=None, providers: list | None = None,
                 settings_getter: Callable[[], Any] | None = None):
        self.db = db
        self.graph = graph
        self._bus = bus
        self._privacy = privacy
        self._settings = settings_getter
        self.providers = providers if providers is not None else [WebUIProvider(), DiffusersProvider()]
        self._status_cache: tuple[float, dict] | None = None

    def register(self, provider) -> None:
        self.providers.append(provider)
        self._status_cache = None

    def status(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._status_cache and not refresh and time.time() - self._status_cache[0] < 30:
            return self._status_cache[1]
        report, chosen = [], None
        for provider in self.providers:
            ok, reason = provider.available()
            if ok and getattr(provider, "external", False) and self._privacy is not None:
                if not self._privacy.allow_external("geração de imagem", provider.name, explicit=False).allowed:
                    ok, reason = False, "provedor externo bloqueado pelo modo local"
            report.append({"provider": provider.name, "available": ok, "reason": reason})
            if ok and chosen is None:
                chosen = provider.name
        status = {"available": chosen is not None, "provider": chosen, "providers": report,
                  "reason": "" if chosen else "Módulo de imagem indisponível: " + "; ".join(r["reason"] for r in report)}
        self._status_cache = (time.time(), status)
        return status

    def generate(self, prompt: str, *, concept_id: str | None = None, label: str = "", cancel=None) -> ImageRecord:
        status = self.status(refresh=True)
        if not status["available"]:
            raise ImageUnavailable(status["reason"])
        provider = next(p for p in self.providers if p.name == status["provider"])
        data = provider.generate(prompt, cancel=cancel)
        if not data[:8].startswith(b"\x89PNG"):
            raise RuntimeError("o provedor de imagem devolveu dados que não são PNG")
        record = ImageRecord(uuid.uuid4().hex[:12], "", prompt[:1000], provider.name, concept_id, time.time())
        path = paths.images_dir() / f"{record.id}.png"
        path.write_bytes(data)
        record.path = str(path)
        if self.db is not None:
            self.db.execute("INSERT INTO images(id,concept_id,path,prompt,provider,created_at) VALUES(?,?,?,?,?,?)",
                            (record.id, concept_id, record.path, record.prompt, record.provider, record.created_at))
        if self.graph is not None:
            try:
                node = self.graph.add_node("MEMORY", f"Imagem {label or record.id}", {"image": record.path})
                if concept_id:
                    self.graph.connect(node.id, concept_id, "CREATED_FROM", delta=0.3)
            except (ValueError, KeyError):
                pass
        return record
