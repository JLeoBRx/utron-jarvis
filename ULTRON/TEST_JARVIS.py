"""TEST_JARVIS — executa a suíte de testes e mostra o estado do ambiente (componentes ausentes).

    python TEST_JARVIS.py                 todos os testes
    python TEST_JARVIS.py --quick         pula os testes lentos (voz real e renderização)
    python TEST_JARVIS.py test_voice      apenas os módulos indicados
    python TEST_JARVIS.py --env           só o relatório do ambiente (modo de diagnóstico)

Os testes usam pastas temporárias: nenhum dado real do usuário é lido ou alterado.
O Ollama real não é necessário (um servidor HTTP local imita a API dele).
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import platform
import sys
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS = ROOT / "tests"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

REQUIRED = {"numpy": "numpy", "psutil": "psutil"}
INTERFACE = {"PySide6": "JARVIS CORE e TARDIS (sem ele: modo console)"}
OPTIONAL = {
    "vosk": "reconhecimento de fala offline", "pyaudio": "microfone e saída de áudio (PyAudio)",
    "sounddevice": "microfone e saída de áudio (alternativa ao PyAudio)",
    "piper": "voz neural do JARVIS", "pyttsx3": "voz alternativa (SAPI)",
    "pyautogui": "teclado, mouse e mídia", "pywinauto": "elementos de interface do Windows",
    "pycaw": "volume do sistema", "send2trash": "exclusão segura (Lixeira)", "mss": "captura de tela",
    "PIL": "imagens (Pillow)", "pytesseract": "OCR (requer Tesseract OCR)",
    "serial": "Noctário pela porta COM do Bluetooth (pyserial)",
}


def has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def environment_report() -> list[str]:
    from ultron import __version__
    from ultron.config import paths
    from ultron.voice.stt import LARGE, SMALL

    lines = [f"JARVIS {__version__} · Python {platform.python_version()} · {platform.system()} {platform.release()}"]
    for module, label in {**REQUIRED, **INTERFACE}.items():
        lines.append(f"  [{'ok' if has(module) else 'FALTA'}] {module:<12} {label}")
    for module, label in OPTIONAL.items():
        lines.append(f"  [{'ok' if has(module) else ' — '}] {module:<12} {label}")
    stt = paths.stt_models_dir()
    lines.append(f"  [{'ok' if (stt / LARGE / 'am' / 'final.mdl').is_file() else ' — '}] modelo de fala grande ({LARGE})")
    lines.append(f"  [{'ok' if (stt / SMALL / 'final.mdl').is_file() else ' — '}] modelo de fala pequeno ({SMALL})")
    voice = paths.voices_dir() / "pt_BR-faber-medium.onnx"
    lines.append(f"  [{'ok' if voice.is_file() else ' — '}] voz pt_BR-faber-medium")
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5) as response:
            import json
            models = [m.get("name") for m in json.loads(response.read()).get("models", [])]
        lines.append(f"  [ok ] Ollama local · modelos: {', '.join(models) or 'nenhum'}")
    except Exception:
        lines.append("  [ — ] Ollama local não está em execução (os testes não precisam dele)")
    return lines


class _Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.per_module: dict[str, list[int]] = {}

    def _count(self, test, index: int) -> None:
        module = type(test).__module__
        self.per_module.setdefault(module, [0, 0, 0])[index] += 1

    def addSuccess(self, test):  # noqa: N802 (unittest)
        super().addSuccess(test)
        self._count(test, 0)

    def addFailure(self, test, err):  # noqa: N802
        super().addFailure(test, err)
        self._count(test, 1)

    def addError(self, test, err):  # noqa: N802
        super().addError(test, err)
        self._count(test, 1)

    def addSkip(self, test, reason):  # noqa: N802
        super().addSkip(test, reason)
        self._count(test, 2)


def _safe_output() -> None:
    """O relatório nunca cai por um caractere: redirecionada (CI, arquivo), a saída vira UTF-8; num console,
    o que a página de código não tiver vira '?' em vez de derrubar a impressão das falhas."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _safe_output()
    parser = argparse.ArgumentParser(description="Suíte de testes do JARVIS")
    parser.add_argument("modules", nargs="*", help="módulos de teste (ex.: test_voice)")
    parser.add_argument("--quick", action="store_true", help="pula testes lentos")
    parser.add_argument("--env", action="store_true", help="só o relatório do ambiente")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.quick:
        os.environ["ULTRON_TEST_QUICK"] = "1"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import helpers  # noqa: F401  (isola dados em pasta temporária antes de qualquer import do JARVIS)

    logging.basicConfig(level=logging.CRITICAL)
    print("\n".join(environment_report()))
    if args.env:
        return 0
    loader = unittest.TestLoader()
    if args.modules:
        suite = unittest.TestSuite(loader.loadTestsFromName(name.removesuffix(".py")) for name in args.modules)
    else:
        suite = loader.discover(str(TESTS), pattern="test_*.py", top_level_dir=str(TESTS))
    print(f"\nExecutando {suite.countTestCases()} testes…\n")
    started = time.perf_counter()
    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1, resultclass=_Result, stream=sys.stdout)
    result = runner.run(suite)
    print("\nResumo por módulo (ok / falhas / pulados):")
    for module, (ok, failed, skipped) in sorted(result.per_module.items()):
        mark = "FALHOU" if failed else "ok"
        print(f"  {module:<22} {ok:>3} / {failed:>2} / {skipped:>2}   {mark}")
    total = time.perf_counter() - started
    status = "APROVADO" if result.wasSuccessful() else "REPROVADO"
    print(f"\n{status}: {result.testsRun} testes em {total:.1f}s · {len(result.failures) + len(result.errors)} falha(s)"
          f" · {len(result.skipped)} pulado(s)")
    helpers.cleanup()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
