"""PV-02 — Tempo de resposta do núcleo (do pedido à resposta publicada) e tempo de inicialização do núcleo.

Monta o MESMO ``NeuralCore`` do aplicativo (sem microfone, sem percepção, sem plugins; pasta de dados
temporária) e mede, para cada pedido, o tempo entre ``submit()`` e o evento ``RESPONSE_READY``:

* **comandos determinísticos** (respondidos por regras e pela memória, sem modelo de linguagem): horas, data,
  anotação na memória pessoal, consulta de compromissos, estado do sistema — meta RNF01 (p95 ≤ 1 s);
* **perguntas ao modelo**: com ``--ollama URL`` usa o Ollama REAL indicado (meta RNF02, registrar modelo e
  hardware). Sem ``--ollama``, usa um servidor local que responde na hora (0 ms de inferência): o número
  medido é só a **sobrecarga do núcleo** no caminho do modelo, não o tempo de um modelo real.

Uso:  python tools/experimentos/pv02_latencia.py [--repeticoes 20] [--ollama http://127.0.0.1:11434 --modelo qwen2.5:3b]
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum as C  # noqa: E402

DETERMINISTICOS = (
    "que horas são", "que dia é hoje", "anote uma ideia: horta vertical na varanda",
    "o que eu tenho amanhã", "liste minhas ideias", "status do sistema",
)
PERGUNTAS = (
    "explique em uma frase o que é fotossíntese", "qual a diferença entre RAM e armazenamento",
    "sugira um nome para um projeto de horta", "resuma em uma frase o que é um banco de dados",
)


def medir(core, texto: str, prazo: float) -> tuple[float | None, dict]:
    from ultron.core.events import EventType
    pronto = threading.Event()
    caixa: dict = {}

    def ao_responder(evento):
        payload = evento.payload if hasattr(evento, "payload") else {}
        if payload.get("partial"):                              # mensagens de progresso não contam
            return
        caixa.update(payload)
        pronto.set()

    assinatura = core.bus.subscribe(EventType.RESPONSE_READY, ao_responder, name="pv02")
    try:
        t0 = time.perf_counter()
        if not core.submit(texto, source="text"):
            return None, {"erro": "submit recusado"}
        ok = pronto.wait(prazo)
        dt = time.perf_counter() - t0
    finally:
        core.bus.unsubscribe(assinatura)
    deadline = time.monotonic() + prazo                        # espera o núcleo voltar ao repouso
    while core.busy and time.monotonic() < deadline:
        time.sleep(0.01)
    return (dt if ok else None), caixa


def main() -> int:
    args = C.argumentos(__doc__.splitlines()[0], extra=lambda p: (
        p.add_argument("--repeticoes", type=int, default=20),
        p.add_argument("--ollama", default="", help="URL de um Ollama REAL (sem isso, inferência simulada de 0 ms)"),
        p.add_argument("--modelo", default="qwen2.5:3b")))
    C.preparar()
    from fake_ollama import FakeOllama
    from ultron.config.settings import SettingsManager
    from ultron.config import paths
    from ultron.core.neural_core import NeuralCore
    falso = None
    url = args.ollama
    if not url:
        falso = FakeOllama([args.modelo], responder=lambda payload: "Resposta de teste do servidor simulado.")
        falso.__enter__()
        url = falso.url
    gerente = SettingsManager(paths.data_file("settings.json"))
    gerente.load()
    gerente.settings.apply({"ollama_url": url, "model": args.modelo, "network_discovery": False,
                            "auto_backup": False, "voice_enabled": False, "ollama_autostart": False})
    with C.Cronometro() as t_boot:
        core = NeuralCore(gerente, voice=False, perception=False, plugins=False)
        core.boot()
    repeticoes = 3 if args.rapido else args.repeticoes
    brutos = []
    try:
        for grupo, frases, prazo in (("deterministico", DETERMINISTICOS, 30.0), ("modelo", PERGUNTAS, 300.0)):
            for r in range(repeticoes if grupo == "deterministico" else max(1, repeticoes // 2)):
                for frase in frases:
                    dt, payload = medir(core, frase, prazo)
                    prov = (payload.get("provenance") or {}).get("label")
                    brutos.append({"grupo": grupo, "frase": frase, "rep": r, "s": None if dt is None else round(dt, 4),
                                   "procedencia": prov, "tipo": payload.get("kind")})
    finally:
        core.shutdown()
        if falso is not None:
            falso.__exit__(None, None, None)
    metricas = {"inicializacao_nucleo_s": round(t_boot.s, 3)}
    for grupo in ("deterministico", "modelo"):
        tempos = [b["s"] for b in brutos if b["grupo"] == grupo and b["s"] is not None]
        sem_resposta = sum(b["s"] is None for b in brutos if b["grupo"] == grupo)
        metricas[grupo] = {**C.resumo(tempos), "sem_resposta": sem_resposta}
        metricas[grupo + "_por_frase"] = {f: C.resumo([b["s"] for b in brutos if b["frase"] == f and b["s"] is not None])
                                         for f in sorted({b["frase"] for b in brutos if b["grupo"] == grupo})}
    resultado = {"protocolo": "PV-02", "modelo_real": bool(args.ollama), "modelo": args.modelo,
                 "real": ["NeuralCore completo (orquestrador, intenções, memória, executor, Event Bus, SQLite)"] +
                         (["Ollama real em " + args.ollama] if args.ollama else []),
                 "simulado": [] if args.ollama else ["inferência do modelo (servidor local que responde em 0 ms)"],
                 "ambiente": C.ambiente(), "rapido": args.rapido, "metricas": metricas, "amostras": brutos}
    caminho = C.gravar("pv02_latencia", resultado, rotulo=args.rotulo)
    print({k: (v.get("p95") if isinstance(v, dict) else v) for k, v in metricas.items() if not k.endswith("_por_frase")})
    print(f"resultado: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
