"""Skills de desenvolvimento: localizar projeto, inspecionar ambiente, checar dependências,
executar, diagnosticar erros, criar ambiente virtual e instalar dependências.

Executar código do projeto e instalar pacotes são ações sensíveis (risco alto): sempre
passam por autorização. Nenhum comando aceita texto livre: nomes de pacote e módulos são
validados por expressões estritas e os argumentos são vetores fixos.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from ...perception.filesystem import IGNORED_DIRS, detect_project
from ...platform import system
from .._util import absolute_path, norm
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string

IS_WINDOWS = sys.platform == "win32"
PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}(\[[A-Za-z0-9,._-]+\])?(==[A-Za-z0-9.*+!-]{1,40})?$")
MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,5}$")
MODULE_TO_PACKAGE = {
    "cv2": "opencv-python", "PIL": "Pillow", "yaml": "PyYAML", "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv", "serial": "pyserial", "win32api": "pywin32", "win32con": "pywin32",
    "Crypto": "pycryptodome", "docx": "python-docx", "fitz": "PyMuPDF", "dateutil": "python-dateutil",
    "jwt": "PyJWT", "telegram": "python-telegram-bot", "googleapiclient": "google-api-python-client",
}
ENTRY_CANDIDATES = ("main.py", "app.py", "run.py", "manage.py", "__main__.py", "src/main.py", "start.py")
COMMON_ROOTS = ("Projects", "Projetos", "projetos", "projects", "dev", "code", "source/repos", "Documents",
                "Documentos", "Desktop", "Área de Trabalho")


def venv_python(project: Path) -> Path | None:
    for name in (".venv", "venv", "env"):
        base = project / name
        exe = base / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
        if (base / "pyvenv.cfg").is_file() and exe.exists():
            return exe
    return None


def project_python(project: Path) -> tuple[str, bool]:
    exe = venv_python(project)
    return (str(exe), True) if exe else (sys.executable if not getattr(sys, "frozen", False) else "python", False)


def requirements_of(project: Path) -> list[str]:
    names: list[str] = []
    req = project / "requirements.txt"
    if req.is_file():
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith(("-", "git+", "http")):
                continue
            name = re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].strip()
            if name:
                names.append(name)
    pyproject = project / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            for dep in data.get("project", {}).get("dependencies", []) or []:
                name = re.split(r"[<>=!~;\[ ]", dep, maxsplit=1)[0].strip()
                if name:
                    names.append(name)
        except Exception:
            pass
    return list(dict.fromkeys(names))


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def find_entry(project: Path) -> str | None:
    for candidate in ENTRY_CANDIDATES:
        if (project / candidate).is_file():
            return candidate
    py_files = [p.name for p in project.glob("*.py")]
    return py_files[0] if len(py_files) == 1 else None


def parse_traceback(text: str) -> dict:
    """Extrai tipo, mensagem e local do erro de uma saída Python."""
    text = str(text or "")
    result = {"has_traceback": "Traceback (most recent call last)" in text, "type": "", "message": "",
              "file": "", "line": None, "module": "", "category": ""}
    match = None
    for match in re.finditer(r"^(\w+(?:\.\w+)*(?:Error|Exception|Exit|Interrupt|Warning))(?::\s*(.*))?$", text, re.M):
        pass
    if match:
        result["type"] = match.group(1).split(".")[-1]
        result["message"] = (match.group(2) or "").strip()[:300]
    frames = re.findall(r'File "([^"]+)", line (\d+)', text)
    if frames:
        result["file"], result["line"] = frames[-1][0], int(frames[-1][1])
    module = re.search(r"No module named '([\w.]+)'", text)
    if module:
        result["module"] = module.group(1)
    kind = result["type"]
    result["category"] = (
        "DEPENDENCY_ERROR" if kind in ("ModuleNotFoundError", "ImportError") else
        "SYNTAX_ERROR" if kind in ("SyntaxError", "IndentationError", "TabError") else
        "FILE_NOT_FOUND" if kind == "FileNotFoundError" else
        "PERMISSION_ERROR" if kind == "PermissionError" else
        "APPLICATION_ERROR" if kind else "")
    return result


def _run_capture(args: list[str], cwd: str, timeout: float) -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            env=env, creationflags=system.NO_WINDOW, shell=False)
    chunks: list[bytes] = []

    def reader():
        # continua drenando a saída enquanto o processo viver (um servidor deixado em execução não
        # trava por pipe cheio) e fecha o pipe ao final
        try:
            for line in iter(proc.stdout.readline, b""):
                if sum(len(c) for c in chunks) < 200_000:
                    chunks.append(line)
        finally:
            proc.stdout.close()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        code = proc.wait(timeout=timeout)
        thread.join(2)
        running = False
    except subprocess.TimeoutExpired:
        code, running = None, True
    output = b"".join(chunks).decode("utf-8", "replace")
    return {"exit_code": code, "running": running, "pid": proc.pid, "output": output[-20000:]}


class _DevSkill(Skill):
    category = "development"


class LocateProject(_DevSkill):
    name = "dev.locate_project"
    description = "Localizar um projeto de software pelo nome (ou o projeto aberto no editor)."
    inputs = schema({"name": string(120)})
    risk = Risk.NONE
    timeout = 40.0

    def _roots(self, ctx) -> list[Path]:
        roots = []
        if ctx.memory is not None:
            custom = ctx.memory.preferences.get("projects_root")
            if custom:
                roots.append(Path(custom))
        home = Path.home()
        roots += [home / r for r in COMMON_ROOTS]
        return [r for r in roots if r.is_dir()]

    def execute(self, ctx, name: str | None = None) -> SkillResult:
        wanted = norm(name or "")
        candidates: list[dict] = []
        if ctx.world is not None:
            for project in ctx.world.get("projects").values():
                if not wanted or wanted in norm(project.get("name", "")):
                    if Path(project.get("path", "")).is_dir():
                        candidates.append(project)
        if not wanted and ctx.world is not None and not candidates:
            window = ctx.world.get("user_context").get("window", "")
            match = re.search(r" - ([^-]+) - Visual Studio Code", window)
            if match:
                wanted = norm(match.group(1))
        if not candidates:
            deadline = time.monotonic() + 25
            for root in self._roots(ctx):
                for folder, dirs, _files in os.walk(root):
                    depth = len(Path(folder).relative_to(root).parts)
                    dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")] if depth < 3 else []
                    if wanted and wanted not in norm(os.path.basename(folder)):
                        continue
                    project = detect_project(Path(folder))
                    if project:
                        candidates.append(project)
                        dirs[:] = []
                    if len(candidates) >= 10 or time.monotonic() > deadline:
                        break
                if len(candidates) >= 10:
                    break
        if not candidates:
            return SkillResult(False, error=f"projeto {name or ''} não encontrado".replace("  ", " "),
                               error_kind="NOT_FOUND")
        candidates.sort(key=lambda p: (norm(p.get("name", "")) != wanted, -p.get("last_seen", 0)))
        best = candidates[0]
        if ctx.world is not None:
            ctx.world.upsert_item("projects", best["path"], best, source="dev.locate_project")
        alternatives = [c["path"] for c in candidates[1:5]]
        return SkillResult(True, f"Projeto {best['name']} em {best['path']} ({best.get('language', '?')}).",
                           [best["path"]] + ([f"alternativas: {', '.join(alternatives)}"] if alternatives else []),
                           {"project": best, "path": best["path"], "alternatives": alternatives})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        project = detect_project(Path(result.data["path"]))
        return VerificationResult.from_checks([check("project_exists", bool(project), result.data["path"])])


class InspectEnvironment(_DevSkill):
    name = "dev.inspect_environment"
    description = "Inspecionar o ambiente de um projeto Python (versão, ambiente virtual, ponto de entrada)."
    inputs = schema({"path": string(1000)}, ("path",))
    risk = Risk.NONE

    def execute(self, ctx, path: str) -> SkillResult:
        project = Path(absolute_path(path))
        if not project.is_dir():
            return SkillResult(False, error=f"pasta inexistente: {project}", error_kind="FILE_NOT_FOUND")
        python, in_venv = project_python(project)
        version = system.run([python, "--version"], timeout=10, encoding="utf-8")
        entry = find_entry(project)
        requirements = requirements_of(project)
        info = {"python": python, "venv": in_venv, "version": (version.stdout or version.stderr).strip(),
                "entry": entry, "requirements": requirements, "path": str(project)}
        text = (f"{info['version'] or 'Python não encontrado'}; "
                f"{'ambiente virtual presente' if in_venv else 'sem ambiente virtual'}; "
                f"entrada: {entry or 'não identificada'}; {len(requirements)} dependência(s) declarada(s).")
        return SkillResult(version.ok, text if version.ok else "", [python], info,
                           error="" if version.ok else "interpretador Python indisponível",
                           error_kind="" if version.ok else "DEPENDENCY_ERROR")

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.95, [check("interpreter", True, result.data["version"])])


class CheckDependencies(_DevSkill):
    name = "dev.check_dependencies"
    description = "Comparar as dependências declaradas do projeto com as instaladas no ambiente."
    inputs = schema({"path": string(1000)}, ("path",))
    risk = Risk.LOW
    timeout = 90.0

    def execute(self, ctx, path: str) -> SkillResult:
        project = Path(absolute_path(path))
        python, in_venv = project_python(project)
        declared = requirements_of(project)
        listing = system.run([python, "-m", "pip", "list", "--format=json", "--disable-pip-version-check"],
                             timeout=60, encoding="utf-8")
        if not listing.ok:
            return SkillResult(False, error="pip indisponível no ambiente do projeto", error_kind="DEPENDENCY_ERROR")
        try:
            installed = {canonical(p["name"]): p["version"] for p in json.loads(listing.stdout or "[]")}
        except ValueError:
            return SkillResult(False, error="saída inesperada do pip", error_kind="DEPENDENCY_ERROR")
        missing = [d for d in declared if canonical(d) not in installed]
        broken = system.run([python, "-m", "pip", "check", "--disable-pip-version-check"], timeout=60, encoding="utf-8")
        conflicts = [] if broken.ok else [l for l in broken.stdout.splitlines() if l.strip()][:10]
        text = (f"{len(declared)} declarada(s), {len(missing)} ausente(s)"
                + (f": {', '.join(missing[:8])}" if missing else "") + (f"; {len(conflicts)} conflito(s)" if conflicts else ""))
        return SkillResult(True, text + ".", [f"ambiente: {'venv' if in_venv else 'Python do sistema'}"],
                           {"declared": declared, "missing": missing, "conflicts": conflicts, "venv": in_venv,
                            "installed_count": len(installed)})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.9, [check("pip_list", True, "lista obtida do pip do projeto")])


class RunProject(_DevSkill):
    name = "dev.run_project"
    description = "Executar o projeto (ponto de entrada Python) e observar a saída."
    inputs = schema({"path": string(1000), "entry": string(200),
                     "observe_seconds": {"type": "integer", "minimum": 3, "maximum": 300}}, ("path",))
    risk = Risk.HIGH
    reversible = False
    timeout = 320.0

    def describe_action(self, args):
        return f"executar o projeto em {args.get('path')} ({args.get('entry') or 'entrada automática'})"

    def execute(self, ctx, path: str, entry: str | None = None, observe_seconds: int = 20) -> SkillResult:
        project = Path(absolute_path(path))
        entry = entry or find_entry(project)
        if not entry:
            return SkillResult(False, error="ponto de entrada não identificado (main.py/app.py)", error_kind="NOT_FOUND")
        script = (project / entry).resolve()
        if project.resolve() not in script.parents or not script.is_file():
            return SkillResult(False, error="o ponto de entrada deve estar dentro do projeto", error_kind="PERMISSION_ERROR")
        python, _ = project_python(project)
        run = _run_capture([python, str(script)], str(project), float(observe_seconds))
        diagnosis = parse_traceback(run["output"])
        failed = bool(diagnosis["has_traceback"] or (run["exit_code"] not in (0, None)))
        data = {**run, "diagnosis": diagnosis, "entry": entry, "path": str(project)}
        if ctx.extras is not None:
            ctx.extras["last_run"] = data
        if failed:
            summary = f"{diagnosis['type'] or 'erro'}: {diagnosis['message'] or 'código ' + str(run['exit_code'])}"
            return SkillResult(False, run["output"][-1500:], [summary], data, error=summary,
                               error_kind=diagnosis["category"] or "APPLICATION_ERROR")
        state = (f"em execução (pid {run['pid']}); nenhum erro em {observe_seconds} s" if run["running"]
                 else "terminou com código 0")
        return SkillResult(True, f"Projeto {project.name}: {state}.", [state], data)

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        diag = result.data.get("diagnosis", {})
        return VerificationResult.from_checks([
            check("no_traceback", not diag.get("has_traceback"), "nenhum traceback na saída"),
            check("exit_status", result.data.get("exit_code") in (0, None),
                  f"código de saída {result.data.get('exit_code')}" if result.data.get("exit_code") is not None
                  else "processo em execução"),
        ])


class DiagnoseError(_DevSkill):
    name = "dev.diagnose_error"
    description = "Diagnosticar a última falha de execução (ou um texto de erro fornecido)."
    inputs = schema({"text": {"type": "string", "maxLength": 20000, "minLength": 0}})
    risk = Risk.NONE

    def execute(self, ctx, text: str = "") -> SkillResult:
        source = text or (ctx.extras.get("last_run") or {}).get("output", "")
        if not source:
            return SkillResult(False, error="não há saída de erro para diagnosticar", error_kind="NOT_FOUND")
        diag = parse_traceback(source)
        if not diag["type"]:
            return SkillResult(True, "Nenhum erro Python reconhecível na saída.", [], {"diagnosis": diag})
        advice = ""
        if diag["category"] == "DEPENDENCY_ERROR" and diag["module"]:
            root = diag["module"].split(".")[0]
            diag["package"] = MODULE_TO_PACKAGE.get(root, root)
            advice = f" Correção provável: instalar o pacote {diag['package']} no ambiente do projeto."
        elif diag["file"]:
            advice = f" Local: {os.path.basename(diag['file'])}, linha {diag['line']}."
        return SkillResult(True, f"{diag['type']}: {diag['message']}.{advice}", [diag["category"]], {"diagnosis": diag})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.85, [check("parsed", True, "traceback analisado")])


class CreateVenv(_DevSkill):
    name = "dev.create_venv"
    description = "Criar um ambiente virtual .venv no projeto."
    inputs = schema({"path": string(1000)}, ("path",))
    risk = Risk.MEDIUM
    timeout = 180.0

    def execute(self, ctx, path: str) -> SkillResult:
        project = Path(absolute_path(path))
        if venv_python(project):
            return SkillResult(True, "O projeto já possui ambiente virtual.", [], {"path": str(project)})
        result = system.run([sys.executable, "-m", "venv", str(project / ".venv")], timeout=150, encoding="utf-8")
        if not result.ok:
            return SkillResult(False, error=result.stderr.strip()[:300] or "falha ao criar o ambiente",
                               error_kind="DEPENDENCY_ERROR")
        return SkillResult(True, f"Ambiente virtual criado em {project / '.venv'}.", [], {"path": str(project)})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        ok = venv_python(Path(result.data["path"])) is not None
        return VerificationResult.from_checks([check("venv_exists", ok, "pyvenv.cfg e interpretador presentes")])


class InstallDependency(_DevSkill):
    name = "dev.install_dependency"
    description = "Instalar um pacote Python no ambiente virtual do projeto (pip)."
    inputs = schema({"path": string(1000), "package": string(140), "module": string(120)}, ("path", "package"))
    risk = Risk.HIGH
    reversible = True
    timeout = 360.0

    def validate(self, args):
        args = super().validate(args)
        if not PACKAGE_RE.match(args["package"]):
            raise ValueError("nome de pacote inválido")
        if args.get("module") and not MODULE_RE.match(args["module"]):
            raise ValueError("nome de módulo inválido")
        return args

    def describe_action(self, args):
        return f"instalar o pacote {args.get('package')} no ambiente do projeto"

    def execute(self, ctx, path: str, package: str, module: str | None = None) -> SkillResult:
        project = Path(absolute_path(path))
        python = venv_python(project)
        if python is None:
            return SkillResult(False, error="o projeto não tem ambiente virtual; não instalo pacotes no Python do sistema",
                               error_kind="DEPENDENCY_ERROR", data={"needs_venv": True})
        if ctx.privacy is not None:
            ctx.privacy.allow_external("pip install", package, explicit=True)
        result = system.run([str(python), "-m", "pip", "install", package, "--disable-pip-version-check"],
                            timeout=330, encoding="utf-8")
        if not result.ok:
            tail = (result.stdout + result.stderr).strip()[-400:]
            kind = "NETWORK_ERROR" if re.search(r"connection|timed out|resolve", tail, re.I) else "DEPENDENCY_ERROR"
            return SkillResult(False, error=f"pip falhou: {tail}", error_kind=kind)
        return SkillResult(True, f"Pacote {package} instalado.", [f"python: {python}"],
                           {"python": str(python), "package": package, "module": module})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        python = result.data["python"]
        name = re.split(r"[\[=]", result.data["package"])[0]
        shown = system.run([python, "-m", "pip", "show", name, "--disable-pip-version-check"], timeout=60,
                           encoding="utf-8")
        checks = [check("package_installed", shown.ok, f"pip show {name}")]
        module = result.data.get("module")
        if module:
            imported = system.run([python, "-c", f"import {module}"], timeout=60, encoding="utf-8")
            checks.append(check("module_importable", imported.ok, f"import {module}"))
        return VerificationResult.from_checks(checks)


SKILLS = (LocateProject, InspectEnvironment, CheckDependencies, RunProject, DiagnoseError, CreateVenv,
          InstallDependency)
