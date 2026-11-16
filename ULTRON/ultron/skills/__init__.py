"""Sistema de Skills: capacidades executáveis e verificáveis."""
from .base import Risk, Skill, SkillContext, SkillResult, VerificationResult
from .registry import FORBIDDEN, SkillRegistry, load_builtin

__all__ = ["Risk", "Skill", "SkillContext", "SkillResult", "VerificationResult", "FORBIDDEN", "SkillRegistry",
           "load_builtin"]
