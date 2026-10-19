"""JARVIS NEURAL HUB — interface neural procedural (PySide6).

* ``brain_model``: malha neural 3D procedural do cérebro (numpy);
* ``scene``: estado visual derivado só de eventos e do JARVIS_STATE reais (sem Qt);
* ``brain_view``: desenho da cena; ``window``/``orb``: janelas; ``controller``: ligação com o Core.

Os módulos com Qt são importados sob demanda: o JARVIS roda sem interface (``--headless``)
mesmo sem PySide6 instalado.
"""


def run_hud(core, **kwargs):
    from .controller import run_hud as _run
    return _run(core, **kwargs)


__all__ = ["run_hud"]
