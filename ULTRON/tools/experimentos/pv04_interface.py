"""PV-04 — Interface: tempo de montagem da interface, tempo até a cena 3D ficar pronta e quadros por segundo.

* **montagem da interface** — ``main.py --gui-check`` em processo novo (importa o Qt, monta janela, páginas,
  avatar e menu da bandeja, sem mostrar a janela), N vezes; registra o tempo total e o código de saída;
* **cena 3D pronta** — ``tests/scene3d_probe.py`` (QtWebEngine + WebGL desta máquina), N vezes: tempo até a página
  avisar que está pronta, renderizador usado e erros de JavaScript;
* **quadros por segundo** — ``tools/benchmark_scene3d.py`` no perfil Equilibrado (a própria página mede).

Em contêiner/servidor sem GPU, o WebGL roda por software (llvmpipe/SwiftShader): os números servem para
verificar o instrumento, não para avaliar a meta RNF04, que exige o computador de referência com GPU.
No Linux, rode dentro de um servidor X (ex.: ``xvfb-run -a``).

Uso:  python tools/experimentos/pv04_interface.py [--repeticoes 10] [--rotulo NOME]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum as C  # noqa: E402


def _rodar(cmd: list[str], env: dict, prazo: float) -> tuple[float, int, str]:
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=C.RAIZ, env=env, capture_output=True, text=True, timeout=prazo,
                           stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        return time.perf_counter() - t0, p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return time.perf_counter() - t0, -999, "tempo esgotado"


def main() -> int:
    args = C.argumentos(__doc__.splitlines()[0], extra=lambda p: (
        p.add_argument("--repeticoes", type=int, default=10),
        p.add_argument("--segundos-fps", type=float, default=15.0)))
    pasta = C.preparar()
    env = {**os.environ, "JARVIS_DATA_DIR": str(pasta), "SAFRA_DATA_DIR": str(pasta), "PYTHONIOENCODING": "utf-8"}
    env.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--ignore-gpu-blocklist")
    if sys.platform.startswith("linux"):
        env.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    n = 2 if args.rapido else args.repeticoes
    montagem, cena = [], []
    for _ in range(n):
        s, code, out = _rodar([sys.executable, "main.py", "--gui-check", "--no-voice"], env, 180)
        montagem.append({"s": round(s, 3), "codigo": code, "saida": out.strip().splitlines()[-1:] if out else []})
    for _ in range(n):
        s, code, out = _rodar([sys.executable, str(C.RAIZ / "tests" / "scene3d_probe.py")], env, 180)
        linha = next((x for x in out.splitlines() if x.startswith("SONDA ")), "")
        dados = json.loads(linha[6:]) if linha else {}
        cena.append({"processo_s": round(s, 3), "pronta_s": dados.get("seconds"), "pronta": dados.get("ready"),
                     "renderizador": dados.get("renderer"), "erros_js": dados.get("js_errors"),
                     "falha": dados.get("failed") or dados.get("reason")})
    s, code, out = _rodar([sys.executable, "tools/benchmark_scene3d.py", "--seconds", str(args.segundos_fps),
                           "--profiles", "balanced"], env, 300)
    fps = [json.loads(x.split(" | ")[0]) for x in out.splitlines() if x.startswith("{")]
    metricas = {
        "montagem_interface_s": C.resumo([m["s"] for m in montagem if m["codigo"] == 0]),
        "montagem_falhas": sum(m["codigo"] != 0 for m in montagem),
        "cena_pronta_s": C.resumo([c["pronta_s"] for c in cena if c["pronta"]]),
        "cena_abriu": C.proporcao(sum(bool(c["pronta"]) for c in cena), len(cena)),
        "cena_erros_js": sum(int(c["erros_js"] or 0) for c in cena),
        "renderizadores": sorted({str(c["renderizador"]) for c in cena}),
        "fps_equilibrado": fps,
    }
    resultado = {"protocolo": "PV-04", "real": ["interface Qt", "QtWebEngine + WebGL desta máquina"],
                 "simulado": [], "observacao": "WebGL por software quando não há GPU: não avalia a meta RNF04",
                 "ambiente": C.ambiente({"display": os.environ.get("DISPLAY", ""),
                                         "qpa": os.environ.get("QT_QPA_PLATFORM", "")}),
                 "rapido": args.rapido, "metricas": metricas, "montagem": montagem, "cena": cena}
    caminho = C.gravar("pv04_interface", resultado, rotulo=args.rotulo)
    print(json.dumps(metricas, ensure_ascii=False)[:1200])
    print(f"resultado: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
