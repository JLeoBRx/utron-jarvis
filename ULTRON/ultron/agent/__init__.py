"""AGENT: execução, verificação, recuperação e autonomia."""
from .autonomy import AuthorizationManager, AuthorizationRequest, AutonomyDecision, AutonomyPolicy, classify_reply
from .execution import Action, ExecutionEngine, ExecutionRecord
from .recovery import Diagnosis, RecoveryEngine, RecoveryPlan
from .verification import VerificationEngine

__all__ = ["AuthorizationManager", "AuthorizationRequest", "AutonomyDecision", "AutonomyPolicy", "classify_reply",
           "Action", "ExecutionEngine", "ExecutionRecord", "Diagnosis", "RecoveryEngine", "RecoveryPlan",
           "VerificationEngine"]
