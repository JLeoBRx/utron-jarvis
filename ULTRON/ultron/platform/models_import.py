"""Copia os modelos locais (fala Vosk, voz Piper) de uma instalação anterior — sem sobrescrever nada.

Layouts reconhecidos:

* JARVIS original: ``<pasta>\\voices\\pt_BR-faber-medium.onnx`` e ``<pasta>\\vosk-model-*\\`` na raiz;
* ULTRON / JARVIS atual: ``<pasta>\\assets\\voices\\`` e ``<pasta>\\assets\\stt\\``;
* a pasta indicada pode ser a de cima (que contém ``JARVIS\\`` ou ``ULTRON\\``).

Cada arquivo copiado é conferido pelo tamanho; arquivos já presentes no destino nunca são tocados.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..config import paths

VOICE_FILES = ("pt_BR-faber-medium.onnx", "pt_BR-faber-medium.onnx.json")
STT_MODELS = ("vosk-model-small-pt-0.3", "vosk-model-pt-fb-v0.1.1-20220516_2113")
STT_MARKERS = {"vosk-model-small-pt-0.3": "final.mdl", "vosk-model-pt-fb-v0.1.1-20220516_2113": "am/final.mdl"}


@dataclass
class ImportReport:
    source: str
    copied: list[str] = field(default_factory=list)
    already_present: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Origem: {self.source}"]
        lines.append(f"Copiados: {len(self.copied)} arquivo(s)" + (f" ({', '.join(self.copied[:6])}"
                                                                   f"{'…' if len(self.copied) > 6 else ''})"
                                                                   if self.copied else ""))
        if self.already_present:
            lines.append(f"Já presentes (não tocados): {', '.join(self.already_present)}")
        for item in self.failed:
            lines.append(f"[FALHA] {item}")
        if self.missing:
            lines.append("Ainda faltam: " + "; ".join(self.missing))
        else:
            lines.append("Modelos de fala e voz presentes.")
        return "\n".join(lines)


def _roots(base: Path) -> list[Path]:
    """A própria pasta e subpastas típicas (o usuário pode indicar a pasta de cima)."""
    roots = [base]
    for name in ("JARVIS", "ULTRON", "jarvis", "ultron"):
        if (base / name).is_dir():
            roots.append(base / name)
    return roots


def _find_voice(base: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for root in _roots(base):
        for folder in (root / "assets" / "voices", root / "voices", root):
            for name in VOICE_FILES:
                if name not in found and (folder / name).is_file():
                    found[name] = folder / name
    return found


def _find_stt(base: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for root in _roots(base):
        for folder in (root / "assets" / "stt", root):
            for model in STT_MODELS:
                if model not in found and (folder / model / STT_MARKERS[model]).is_file():
                    found[model] = folder / model
    return found


def _copy_file(src: Path, dst: Path, report: ImportReport, label: str) -> None:
    if dst.exists():
        report.already_present.append(label)
        return
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        partial = dst.with_name(dst.name + ".partial")
        shutil.copyfile(src, partial)
        if partial.stat().st_size != src.stat().st_size:
            partial.unlink(missing_ok=True)
            report.failed.append(f"{label}: tamanho diferente após a cópia")
            return
        partial.replace(dst)
        report.copied.append(label)
    except OSError as exc:
        report.failed.append(f"{label}: {exc}")


def import_models(source: str | Path, assets: Path | None = None) -> ImportReport:
    base = Path(source).expanduser()
    assets = Path(assets) if assets else paths.assets_dir()
    report = ImportReport(str(base))
    if not base.is_dir():
        report.failed.append(f"pasta não encontrada: {base}")
        report.missing = missing_models(assets)
        return report
    for name, src in _find_voice(base).items():
        _copy_file(src, assets / "voices" / name, report, f"voz {name}")
    for model, folder in _find_stt(base).items():
        target = assets / "stt" / model
        if (target / STT_MARKERS[model]).is_file():
            report.already_present.append(f"modelo de fala {model}")
            continue
        for item in sorted(folder.rglob("*")):
            if item.is_file():
                rel = item.relative_to(folder)
                _copy_file(item, target / rel, report, f"{model}/{rel.as_posix()}")
    report.missing = missing_models(assets)
    return report


def missing_models(assets: Path | None = None) -> list[str]:
    assets = Path(assets) if assets else paths.assets_dir()
    missing = []
    if not any((assets / "stt" / m / STT_MARKERS[m]).is_file() for m in STT_MODELS):
        missing.append("modelo de fala Vosk em assets\\stt (vosk-model-small-pt-0.3: alphacephei.com/vosk/models)")
    if not (assets / "voices" / VOICE_FILES[0]).is_file():
        missing.append("voz neural pt_BR-faber-medium em assets\\voices (huggingface.co/rhasspy/piper-voices); "
                       "sem ela, a voz do Windows é usada")
    return missing
