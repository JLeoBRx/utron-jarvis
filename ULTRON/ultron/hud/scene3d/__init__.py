"""Central 3D do SAFRA: holograma de corpo inteiro, ORBE, cabine e sala da TARDIS num só motor 3D.

Arquitetura (AUDITORIA_VISUAL_3D.md):

* o desenho é Three.js (r170, MIT, embutido em ``web/vendor/three``) numa página local dentro de um
  ``QWebEngineView`` — o resto da interface continua Qt; não é uma migração;
* a página só DESENHA: o estado vem do Python (os mesmos sinais reais que o rosto 2D usa) e o que ela pede
  (abrir a TARDIS, escolher um painel, alternar o microfone) volta por uma ponte (QWebChannel) e é decidido
  pelo Python pelo mesmo caminho dos botões;
* sem rede: a página só lê os próprios arquivos (um interceptador bloqueia qualquer outro endereço);
* se a vista 3D não puder abrir (QtWebEngine ausente, sem WebGL 2, contexto perdido, processo de desenho
  encerrado, página sem resposta), a interface volta para a vista 2D e diz por quê — nunca fica em branco.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("ultron.hud.scene3d")

WEB_DIR = Path(__file__).with_name("web")
INDEX = WEB_DIR / "index.html"
MARKER_FILE = "cena3d.estado"            # "iniciando" enquanto abre; "falhou: motivo" após uma falha tratada
CHOICES = ("auto", "desligado")
NO_WINDOW_PLATFORMS = ("offscreen", "minimal", "vnc")
_persist = True                          # a verificação da interface (--gui-check) não mexe no marcador


def set_persist(value: bool) -> None:
    global _persist
    _persist = bool(value)


def inside_web(local_file: str) -> bool:
    """O arquivo pedido pela página está dentro da pasta da cena (sem ``..`` nem atalhos para fora)?"""
    root = WEB_DIR.resolve()
    try:
        path = Path(local_file).resolve()
    except (OSError, ValueError):
        return False
    return path == root or root in path.parents


def marker_path() -> Path:
    from ...config import paths
    return paths.data_file(MARKER_FILE)


def read_marker() -> str:
    try:
        return marker_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write_marker(text: str) -> None:
    if not _persist:
        return
    try:
        marker_path().write_text(text, encoding="utf-8")
    except OSError:
        log.debug("marcador da cena 3D não gravado", exc_info=True)


def clear_marker() -> None:
    if not _persist:
        return
    try:
        marker_path().unlink(missing_ok=True)
    except OSError:
        log.debug("marcador da cena 3D não apagado", exc_info=True)


def webengine_import_error() -> str:
    """Vazio se o QtWebEngine (PySide6-Addons) importa; senão, o motivo."""
    import importlib
    try:
        for name in ("PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel"):
            importlib.import_module(name)
    except Exception as exc:                      # ImportError ou biblioteca nativa ausente
        return f"{type(exc).__name__}: {exc}"
    return ""


def prepare_qt() -> None:
    """Antes de criar a QApplication: o QtWebEngine exige contexto OpenGL compartilhado. Inofensivo para o
    resto da interface; depois da QApplication criada, não tem efeito (e o QtWebEngine avisa no log)."""
    try:
        from PySide6 import QtCore
        if QtCore.QCoreApplication.instance() is None:
            QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
            if sys.platform.startswith("linux"):
                # no Linux o Qt Quick escolhe Vulkan quando existe, e o compositor do QtWebEngine entrega texturas
                # OpenGL: a página fica sem imagem ("Compositor returned null texture"). No Windows fica o padrão.
                from PySide6 import QtQuick
                QtQuick.QQuickWindow.setGraphicsApi(QtQuick.QSGRendererInterface.GraphicsApi.OpenGL)
    except Exception:
        log.debug("preparação do Qt para a cena 3D não aplicada", exc_info=True)


def availability(settings=None, *, platform_name: str = "") -> tuple[bool, str]:
    """(True, "") quando a central 3D pode abrir; senão (False, motivo em português)."""
    choice = str(getattr(settings, "scene3d", "auto") or "auto")
    if choice == "desligado":
        return False, "desligada em CONFIGURAÇÕES > APARÊNCIA"
    if platform_name in NO_WINDOW_PLATFORMS:
        return False, f"plataforma gráfica sem janela ({platform_name})"
    if not INDEX.is_file():
        return False, f"arquivos da cena ausentes ({INDEX})"
    error = webengine_import_error()
    if error:
        return False, f"QtWebEngine indisponível ({error}); instale PySide6-Addons (INSTALL_JARVIS.bat)"
    marker = read_marker()
    if marker.startswith("falhou"):
        return False, (marker.split(":", 1)[1].strip() if ":" in marker else "falhou na última execução") + \
            " — para tentar de novo: CONFIGURAÇÕES > APARÊNCIA > Cena 3D: desligada e depois automática"
    if marker.startswith("iniciando"):
        return False, ("a cena 3D não terminou de abrir na última execução (o processo foi encerrado) — para "
                       "tentar de novo: CONFIGURAÇÕES > APARÊNCIA > Cena 3D: desligada e depois automática")
    return True, ""


def mark_starting() -> None:
    write_marker(f"iniciando {time.strftime('%Y-%m-%d %H:%M:%S')}")


def mark_failed(reason: str) -> None:
    write_marker(f"falhou: {reason}")
