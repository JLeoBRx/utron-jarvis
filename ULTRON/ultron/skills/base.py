"""Contrato das Skills.

Uma Skill é uma capacidade executável e verificável:

* ``name``, ``description``, ``inputs`` (JSON Schema), ``outputs``, ``requirements``, ``risk``;
* ``execute(ctx, **args) -> SkillResult`` — executa e devolve evidências;
* ``verify(ctx, args, result) -> VerificationResult`` — confirma a pós-condição observando o
  mundo de novo (nunca confiando apenas no que ``execute`` disse).

Uma Skill nunca decide se pode executar: isso é papel do Decision/Autonomy. Ela também
nunca usa shell com texto livre.
"""
from __future__ import annotations

import enum
import importlib.util
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


class Risk(str, enum.Enum):
    NONE = "none"          # leitura pura
    LOW = "low"            # reversível e inofensivo (abrir app, pesquisar)
    MEDIUM = "medium"      # altera estado, reversível (digitar, mover janela, criar arquivo)
    HIGH = "high"          # difícil de reverter ou executa código (fechar app, mover arquivo, rodar projeto)
    CRITICAL = "critical"  # destrutivo/irreversível (excluir, desligar, encerrar processo)

    @property
    def level(self) -> int:
        return ["none", "low", "medium", "high", "critical"].index(self.value)


@dataclass
class SkillResult:
    success: bool
    result: str = ""
    evidence: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    error: str = ""
    error_kind: str = ""              # TIMEOUT | APPLICATION_ERROR | NETWORK_ERROR | PERMISSION_ERROR | ...
    started_at: float = field(default_factory=time.time)
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    status: str                       # VERIFIED | FAILED | UNCONFIRMED
    confidence: float = 0.0
    checks: list = field(default_factory=list)      # [{"name", "passed", "detail"}]
    evidence: list = field(default_factory=list)
    reason: str = ""

    @property
    def verified(self) -> bool:
        return self.status == "VERIFIED"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["verified"] = self.verified
        return data

    @classmethod
    def from_checks(cls, checks: list[dict], *, unconfirmed_reason: str = "") -> "VerificationResult":
        if not checks:
            return cls("UNCONFIRMED", 0.3, [], [], unconfirmed_reason or "nenhuma verificação disponível")
        passed = [c for c in checks if c.get("passed")]
        failed = [c for c in checks if c.get("passed") is False]
        evidence = [c.get("detail", "") for c in checks if c.get("detail")]
        if failed:
            return cls("FAILED", 0.9, checks, evidence, failed[0].get("detail") or failed[0]["name"])
        if len(passed) == len(checks):
            return cls("VERIFIED", min(0.99, 0.75 + 0.08 * len(passed)), checks, evidence, "pós-condições confirmadas")
        return cls("UNCONFIRMED", 0.5, checks, evidence, unconfirmed_reason or "verificação incompleta")


@dataclass
class SkillContext:
    """O que uma skill pode usar. Nada além disso."""

    world: Any = None
    memory: Any = None
    perception: Any = None
    network: Any = None
    router: Any = None
    settings: Any = None
    privacy: Any = None
    imagination: Any = None
    voice: Any = None
    cancel: Any = None
    emit: Callable[..., None] | None = None
    extras: dict = field(default_factory=dict)

    def cancelled(self) -> bool:
        return bool(self.cancel is not None and getattr(self.cancel, "cancelled", False))

    def wait(self, seconds: float) -> bool:
        """Espera cooperativa; devolve True se cancelada."""
        if self.cancel is not None and hasattr(self.cancel, "wait"):
            return self.cancel.wait(seconds)
        time.sleep(seconds)
        return False


class Skill:
    name: str = "skill"
    description: str = ""
    category: str = "general"
    inputs: dict = {"type": "object", "properties": {}, "required": []}
    outputs: dict = {}
    requirements: dict = {}          # {"platform": "win32", "modules": ["pyautogui"], "executables": ["code"]}
    risk: Risk = Risk.LOW
    reversible: bool = True
    sensitive: str = ""              # categoria que SEMPRE exige autorização específica (agent.autonomy.SENSITIVE)
    timeout: float = 30.0
    expose_to_llm: bool = True        # pode ser escolhida pelo modelo em passos agênticos

    def available(self) -> tuple[bool, str]:
        req = self.requirements or {}
        platform = req.get("platform")
        if platform and not sys.platform.startswith(platform):
            return False, f"requer {platform}"
        for module in req.get("modules", ()):
            if importlib.util.find_spec(module) is None:
                return False, f"módulo {module} não instalado"
        return True, ""

    def validate(self, args: dict) -> dict:
        """Validação estrita contra ``inputs`` (tipos, obrigatórios, enum, limites)."""
        if not isinstance(args, dict):
            raise ValueError("argumentos devem ser um objeto")
        schema = self.inputs or {}
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        unknown = set(args) - set(props)
        if unknown:
            raise ValueError(f"argumentos não permitidos: {sorted(unknown)}")
        missing = required - set(args)
        if missing:
            raise ValueError(f"argumentos obrigatórios ausentes: {sorted(missing)}")
        clean = {}
        for key, value in args.items():
            spec = props[key]
            kind = spec.get("type")
            if kind == "string":
                if not isinstance(value, str):
                    raise ValueError(f"{key} deve ser texto")
                value = value.strip()
                if spec.get("minLength", 1) and not value:
                    raise ValueError(f"{key} vazio")
                if len(value) > spec.get("maxLength", 2000):
                    raise ValueError(f"{key} excede {spec.get('maxLength', 2000)} caracteres")
            elif kind == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
                        value = int(value)
                    else:
                        raise ValueError(f"{key} deve ser inteiro")
                if "minimum" in spec and value < spec["minimum"]:
                    raise ValueError(f"{key} abaixo de {spec['minimum']}")
                if "maximum" in spec and value > spec["maximum"]:
                    raise ValueError(f"{key} acima de {spec['maximum']}")
            elif kind == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{key} deve ser número")
            elif kind == "boolean":
                if not isinstance(value, bool):
                    raise ValueError(f"{key} deve ser verdadeiro/falso")
            elif kind == "object":
                if not isinstance(value, dict):
                    raise ValueError(f"{key} deve ser objeto")
            elif kind == "array":
                if not isinstance(value, list):
                    raise ValueError(f"{key} deve ser lista")
            if "enum" in spec and value not in spec["enum"]:
                raise ValueError(f"{key} fora das opções permitidas")
            clean[key] = value
        return clean

    def risk_for(self, args: dict) -> Risk:
        """Risco efetivo (algumas skills elevam o risco conforme os argumentos)."""
        return self.risk

    def sensitive_for(self, args: dict) -> str:
        """Categoria sensível desta chamada ('' = nenhuma): exclusão definitiva, rede, credenciais..."""
        return self.sensitive

    def precheck(self, ctx: "SkillContext", args: dict) -> str | None:
        """Devolve um motivo quando a ação é desnecessária (nada a fazer). Evita pedir autorização à toa."""
        return None

    def describe_action(self, args: dict) -> str:
        return f"{self.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"

    def describe_resource(self, ctx: "SkillContext", args: dict) -> str:
        """O recurso exato afetado (ex.: título do registro, endereço), mostrado no pedido de autorização."""
        return ""

    def execute(self, ctx: SkillContext, **args: Any) -> SkillResult:  # pragma: no cover
        raise NotImplementedError

    def verify(self, ctx: SkillContext, args: dict, result: SkillResult) -> VerificationResult:
        """Padrão: sem observação independente, o resultado fica NÃO CONFIRMADO."""
        if not result.success:
            return VerificationResult("FAILED", 0.9, [], result.evidence, result.error or "a execução falhou")
        return VerificationResult("UNCONFIRMED", 0.5, [], result.evidence,
                                  "a skill não possui verificação independente")

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": {**self.inputs, "additionalProperties": False}}}

    def info(self) -> dict:
        ok, reason = self.available()
        return {"name": self.name, "description": self.description, "category": self.category,
                "inputs": self.inputs, "outputs": self.outputs, "requirements": self.requirements,
                "risk": self.risk.value, "reversible": self.reversible, "sensitive": self.sensitive,
                "available": ok, "reason": reason}


def check(name: str, passed: bool | None, detail: str = "") -> dict:
    return {"name": name, "passed": passed, "detail": detail}


def string(max_length: int = 300, **extra: Any) -> dict:
    return {"type": "string", "maxLength": max_length, **extra}


def schema(properties: dict, required: tuple = ()) -> dict:
    return {"type": "object", "properties": properties, "required": list(required)}
