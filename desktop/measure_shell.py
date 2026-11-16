"""Mede uma casca do desktop com o mesmo método para todas (decisão AD-07).

Inicia o comando da casca com `--self-test`, espera o relatório SELFTEST_READY (interface carregada), e então,
com a casca em repouso, amostra por N segundos a memória residente e a CPU de TODA a árvore de processos
(a casca, o motor web e o Assistant, se ela o iniciou). No fim, encerra a árvore e confere que nada sobrou.

Uso:
  python desktop/measure_shell.py --name tauri --out resultado.json -- desktop/poc-tauri/target/release/safra-poc-tauri
  python desktop/measure_shell.py --name qt --out resultado.json -- python desktop/poc-qt/shell.py
Variáveis repassadas à casca: SAFRA_POC_BACKEND, SAFRA_POC_BACKEND_ARGS, SAFRA_POC_BACKEND_PORT.
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
import time
from pathlib import Path

import psutil


def tree(process: psutil.Process) -> list[psutil.Process]:
    try:
        return [process, *process.children(recursive=True)]
    except psutil.NoSuchProcess:
        return []


def measure(command: list[str], *, name: str, idle_seconds: float, timeout: float) -> dict:
    report_file = Path(tempfile.mkdtemp(prefix="safra-shell-")) / "relatorio.txt"
    env = {**os.environ, "SAFRA_POC_REPORT": str(report_file)}
    launched = time.perf_counter()
    process = subprocess.Popen([*command, "--self-test"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    root = psutil.Process(process.pid)
    report = None
    while time.perf_counter() - launched < timeout:
        if report_file.is_file() and report_file.read_text(encoding="utf-8").startswith("SELFTEST_READY "):
            report = json.loads(report_file.read_text(encoding="utf-8")[len("SELFTEST_READY "):])
            break
        if process.poll() is not None:
            break
        time.sleep(0.05)
    ready_seen_s = time.perf_counter() - launched
    result: dict = {"shell": name, "command": command, "platform": platform.platform(), "python": platform.python_version(),
                    "cpus": psutil.cpu_count(), "report": report, "ready_seen_by_harness_s": round(ready_seen_s, 3)}
    if report is None:
        result["error"] = "a casca não ficou pronta" if process.poll() is None else f"a casca encerrou com código {process.returncode}"
        result["stderr"] = (process.stderr.read().decode("utf-8", "replace")[-2000:] if process.poll() is not None else "")
        if process.poll() is None:
            for item in reversed(tree(root)):
                item.kill()
        return result
    samples_rss, samples_cpu, counts = [], [], []
    procs = tree(root)
    for item in procs:
        try:
            item.cpu_percent(None)
        except psutil.NoSuchProcess:
            pass
    end = time.monotonic() + idle_seconds
    while time.monotonic() < end:
        time.sleep(1.0)
        procs = tree(root)
        rss, cpu = 0, 0.0
        for item in procs:
            try:
                rss += item.memory_info().rss
                cpu += item.cpu_percent(None)
            except psutil.NoSuchProcess:
                continue
        samples_rss.append(rss / 2**20)
        samples_cpu.append(cpu)
        counts.append(len(procs))
    names = sorted({p.name() for p in procs if p.is_running()})
    for item in reversed(procs):                           # encerra a árvore inteira
        try:
            item.terminate()
        except psutil.NoSuchProcess:
            pass
    gone, alive = psutil.wait_procs(procs, timeout=10)
    for item in alive:
        item.kill()
    result.update({
        "idle_seconds": idle_seconds,
        "processes": max(counts) if counts else 0, "process_names": names,
        "rss_total_mb": {"median": round(statistics.median(samples_rss), 1), "max": round(max(samples_rss), 1)},
        "cpu_idle_percent": {"mean": round(statistics.fmean(samples_cpu), 2), "max": round(max(samples_cpu), 2),
                             "note": "100 = um núcleo lógico, somando todos os processos da árvore"},
        "left_running_after_terminate": len(alive),
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--idle", type=float, default=15.0)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    runs = [measure(command, name=args.name, idle_seconds=args.idle, timeout=args.timeout) for _ in range(args.runs)]
    Path(args.out).write_text(json.dumps({"runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = all(run.get("report") for run in runs)
    for run in runs:
        print(json.dumps({k: run.get(k) for k in ("shell", "ready_seen_by_harness_s", "rss_total_mb", "cpu_idle_percent",
                                                 "processes", "left_running_after_terminate", "error")}, ensure_ascii=False))
        if run.get("report"):
            print("  relatório:", json.dumps(run["report"], ensure_ascii=False)[:600])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
