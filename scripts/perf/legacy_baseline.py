"""Linha de base de desempenho do sistema LEGADO (pasta ULTRON/), medida sem alterá-lo.

O que mede (tudo com pasta de dados temporária; nenhum dado real é tocado):

* processo  — tempo de parede de ``main.py --version``, ``main.py --say "que horas são"`` e ``main.py --gui-check``;
* núcleo    — inicialização do NeuralCore (em processo), latência de comandos determinísticos e sobrecarga do
              caminho do modelo (inferência SIMULADA de 0 ms: não é o tempo de um modelo real);
* repouso   — CPU do processo, memória residente e threads com o núcleo parado por 60 s;
* voz       — síntese (Piper real) e reconhecimento (Vosk real) sobre áudio sintetizado, sem microfone.

Uso:  python scripts/perf/legacy_baseline.py [--rapido] [--saida docs/performance/data/ARQUIVO.json]
Requer o ambiente Python do legado (ULTRON/requirements.txt).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
LEGADO = RAIZ / "ULTRON"


def resumo(valores: list[float], casas: int = 4) -> dict:
    v = sorted(x for x in valores if x is not None)
    if not v:
        return {"n": 0}

    def pct(p: float) -> float:
        k = (len(v) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(v) - 1)
        return round(v[lo] + (v[hi] - v[lo]) * (k - lo), casas)

    return {"n": len(v), "min": round(v[0], casas), "p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99),
            "max": round(v[-1], casas), "media": round(statistics.fmean(v), casas)}


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def ambiente() -> dict:
    import psutil
    info = {"sistema": f"{platform.system()} {platform.release()}", "maquina": platform.machine(),
            "python": platform.python_version(), "cpus_logicas": psutil.cpu_count(),
            "memoria_total_gb": round(psutil.virtual_memory().total / 2**30, 1), "commit": git("rev-parse", "--short", "HEAD")}
    try:
        modelo = [l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
                  if l.startswith("model name")]
        info["cpu"] = modelo[0] if modelo else platform.processor()
    except OSError:
        info["cpu"] = platform.processor()
    for pacote in ("PySide6-Essentials", "vosk", "piper-tts", "numpy", "psutil"):
        try:
            import importlib.metadata as md
            info[pacote] = md.version(pacote)
        except Exception:
            info[pacote] = "ausente"
    return info


def medir_processo(rapido: bool) -> dict:
    """Tempo de parede de execuções completas do programa (interpretador + importações + trabalho + saída)."""
    n = 3 if rapido else 7
    saida: dict = {}
    casos = {"versao": ["--version"], "pedido_texto": ["--say", "que horas são"], "montar_interface": ["--gui-check"]}
    for nome, args in casos.items():
        tempos, falhas = [], 0
        for _ in range(n):
            pasta = tempfile.mkdtemp(prefix="safra-base-")
            env = dict(os.environ, SAFRA_DATA_DIR=pasta, JARVIS_DATA_DIR=pasta, QT_QPA_PLATFORM="offscreen")
            t0 = time.perf_counter()
            r = subprocess.run([sys.executable, "main.py", *args], cwd=LEGADO, env=env, capture_output=True, text=True,
                               timeout=300)
            dt = time.perf_counter() - t0
            if r.returncode == 0:
                tempos.append(dt)
            else:
                falhas += 1
        saida[nome] = {**resumo(tempos, 3), "falhas": falhas, "unidade": "s"}
    return saida


def medir_nucleo(rapido: bool) -> dict:
    import psutil
    pasta = tempfile.mkdtemp(prefix="safra-base-")
    os.environ["SAFRA_DATA_DIR"] = os.environ["JARVIS_DATA_DIR"] = pasta
    sys.path.insert(0, str(LEGADO))
    sys.path.append(str(LEGADO / "tests"))
    from fake_ollama import FakeOllama
    from ultron.config import paths
    from ultron.config.settings import SettingsManager
    from ultron.core.events import EventType
    from ultron.core.neural_core import NeuralCore

    proc = psutil.Process()
    falso = FakeOllama(["qwen2.5:3b"], responder=lambda payload: "Resposta de teste do servidor simulado.")
    falso.__enter__()

    def novo():
        gerente = SettingsManager(paths.data_file("settings.json"))
        gerente.load()
        gerente.settings.apply({"ollama_url": falso.url, "model": "qwen2.5:3b", "network_discovery": False,
                                "auto_backup": False, "voice_enabled": False, "ollama_autostart": False})
        t0 = time.perf_counter()
        core = NeuralCore(gerente, voice=False, perception=False, plugins=False)
        core.boot()
        return core, time.perf_counter() - t0

    def pedir(core, texto: str, prazo: float) -> float | None:
        pronto = threading.Event()

        def ao_responder(evento):
            payload = evento.payload if hasattr(evento, "payload") else {}
            if not payload.get("partial"):
                pronto.set()

        assinatura = core.bus.subscribe(EventType.RESPONSE_READY, ao_responder, name="base")
        try:
            t0 = time.perf_counter()
            if not core.submit(texto, source="text"):
                return None
            ok = pronto.wait(prazo)
            dt = time.perf_counter() - t0
        finally:
            core.bus.unsubscribe(assinatura)
        limite = time.monotonic() + prazo
        while core.busy and time.monotonic() < limite:
            time.sleep(0.005)
        return dt if ok else None

    boots = []
    for _ in range(2 if rapido else 4):                       # inicializações repetidas (a 1ª cria o banco)
        core, dt = novo()
        boots.append(dt)
        core.shutdown()
    core, dt = novo()
    boots.append(dt)
    rss_apos_boot = proc.memory_info().rss
    deterministicos = ("que horas são", "que dia é hoje", "anote uma ideia: horta vertical na varanda",
                       "o que eu tenho amanhã", "liste minhas ideias", "status do sistema")
    perguntas = ("explique em uma frase o que é fotossíntese", "qual a diferença entre RAM e armazenamento",
                 "sugira um nome para um projeto de horta", "resuma em uma frase o que é um banco de dados")
    reps = 5 if rapido else 50
    t_det, t_mod, sem_resposta = [], [], 0
    try:
        for _ in range(reps):
            for frase in deterministicos:
                dt = pedir(core, frase, 30.0)
                sem_resposta += dt is None
                t_det.append(dt)
        for _ in range(max(1, reps // 2)):
            for frase in perguntas:
                dt = pedir(core, frase, 120.0)
                sem_resposta += dt is None
                t_mod.append(dt)
        rss_apos_carga = proc.memory_info().rss
        # repouso: núcleo no ar, sem pedidos
        segundos = 15 if rapido else 60
        proc.cpu_percent(None)
        cpu = []
        for _ in range(segundos):
            time.sleep(1.0)
            cpu.append(proc.cpu_percent(None))
        repouso = {"segundos": segundos, "cpu_processo_pct": resumo(cpu, 2),
                   "observacao": "100 % = um núcleo lógico; núcleo sem voz, sem percepção e sem interface",
                   "memoria_residente_mb": round(proc.memory_info().rss / 2**20, 1), "threads": proc.num_threads()}
    finally:
        core.shutdown()
        falso.__exit__(None, None, None)
    time.sleep(1.0)
    return {
        "inicializacao_nucleo_s": {**resumo(boots, 3), "amostras": [round(b, 3) for b in boots],
                                   "observacao": "a primeira cria o banco; as seguintes reabrem o mesmo banco"},
        "comando_deterministico_ms": resumo([None if t is None else t * 1000 for t in t_det], 2),
        "caminho_do_modelo_inferencia_simulada_ms": resumo([None if t is None else t * 1000 for t in t_mod], 2),
        "sem_resposta": sem_resposta,
        "memoria_residente_mb": {"apos_inicializar": round(rss_apos_boot / 2**20, 1),
                                 "apos_a_carga": round(rss_apos_carga / 2**20, 1)},
        "repouso": repouso,
        "threads_apos_encerrar": threading.active_count(),
    }


def medir_voz(rapido: bool) -> dict:
    """Síntese (Piper) e reconhecimento (Vosk) reais, sobre áudio sintetizado — sem microfone nem alto-falante."""
    import numpy as np
    saida: dict = {}
    voz = LEGADO / "assets" / "voices" / "pt_BR-faber-medium.onnx"
    modelo = LEGADO / "assets" / "stt" / "vosk-model-small-pt-0.3"
    frases = ["São quatorze horas e trinta e dois minutos.", "Anotei a sua ideia na memória pessoal.",
              "O sistema está funcionando normalmente, sem falhas registradas.",
              "Você tem dois compromissos amanhã: reunião às nove horas e dentista às quinze.",
              "Não encontrei nenhum registro sobre isso na sua memória."]
    if rapido:
        frases = frases[:2]
    try:
        sys.path.insert(0, str(LEGADO))
        from ultron.voice.tts import PiperSynth
        t0 = time.perf_counter()
        piper = PiperSynth(str(voz))
        carga_piper = time.perf_counter() - t0
        sint, fator, audios = [], [], []
        for rodada in range(1 if rapido else 4):
            for frase in frases:
                t0 = time.perf_counter()
                amostras, taxa, _ = piper.synthesize_segments(frase)
                dt = time.perf_counter() - t0
                duracao = len(amostras) / taxa
                sint.append(dt * 1000)
                fator.append(dt / duracao if duracao else None)
                if rodada == 0:
                    audios.append((amostras, taxa, frase))
        saida["sintese_piper"] = {"carregar_voz_s": round(carga_piper, 3), "por_frase_ms": resumo(sint, 1),
                                  "fator_tempo_real": resumo(fator, 3),
                                  "observacao": "fator < 1 = sintetiza mais rápido do que a fala dura"}
    except Exception as exc:                                   # dependência ou modelo ausente: registrado, não inventado
        saida["sintese_piper"] = {"indisponivel": f"{type(exc).__name__}: {exc}"}
        audios = []
    try:
        import vosk
        vosk.SetLogLevel(-1)
        t0 = time.perf_counter()
        modelo_vosk = vosk.Model(str(modelo))
        carga_vosk = time.perf_counter() - t0
        rec_ms, fator = [], []
        for amostras, taxa, frase in audios:
            indices = np.linspace(0, len(amostras) - 1, int(len(amostras) * 16000 / taxa))
            pcm = (np.interp(indices, np.arange(len(amostras)), amostras) * 32767).astype(np.int16).tobytes()
            rec = vosk.KaldiRecognizer(modelo_vosk, 16000)
            t0 = time.perf_counter()
            for i in range(0, len(pcm), 8000):
                rec.AcceptWaveform(pcm[i:i + 8000])
            rec.FinalResult()
            dt = time.perf_counter() - t0
            rec_ms.append(dt * 1000)
            fator.append(dt / (len(pcm) / 2 / 16000))
        saida["reconhecimento_vosk"] = {"carregar_modelo_s": round(carga_vosk, 3), "por_frase_ms": resumo(rec_ms, 1),
                                        "fator_tempo_real": resumo(fator, 3), "modelo": modelo.name}
    except Exception as exc:
        saida["reconhecimento_vosk"] = {"indisponivel": f"{type(exc).__name__}: {exc}"}
    return saida


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--rapido", action="store_true", help="amostra reduzida (só para conferir o instrumento)")
    p.add_argument("--saida", default="")
    args = p.parse_args()
    resultado = {"o_que_e": "linha de base de desempenho do sistema legado (ULTRON/)", "rapido": args.rapido,
                 "data_utc": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "ambiente": ambiente(),
                 "real": ["processo completo do programa", "NeuralCore completo com SQLite", "síntese Piper", "reconhecimento Vosk"],
                 "simulado": ["inferência do modelo de linguagem (servidor local que responde em 0 ms)"],
                 "nao_medido": ["microfone e alto-falante", "GPU", "Windows", "modelo de linguagem real",
                                "tempo até o primeiro token", "interface em tela real"]}
    resultado["processo"] = medir_processo(args.rapido)
    resultado["nucleo"] = medir_nucleo(args.rapido)            # antes da voz: a memória do núcleo não inclui os modelos de fala
    resultado["voz"] = medir_voz(args.rapido)
    destino = Path(args.saida) if args.saida else RAIZ / "docs" / "performance" / "data" / (
        f"legacy_baseline_{resultado['ambiente']['commit'] or 'sem-commit'}.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: resultado[k] for k in ("processo", "voz", "nucleo")}, ensure_ascii=False, indent=1)[:3000])
    print(f"resultado: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
