"""Arquitetura de memória: trabalho, episódica, semântica, procedural e preferências.

``MemorySystem`` é exportado de forma preguiçosa porque depende do Neural Graph, que por
sua vez usa ``memory.store`` (evita importação circular).
"""
from .episodic_memory import EpisodicMemory
from .preference_memory import PreferenceMemory
from .procedural_memory import ProceduralMemory
from .retrieval import Recall, Retriever
from .semantic_memory import SemanticMemory
from .store import Database, looks_secret
from .working_memory import WorkingMemory

__all__ = ["EpisodicMemory", "PreferenceMemory", "ProceduralMemory", "Recall", "Retriever",
           "SemanticMemory", "Database", "looks_secret", "MemorySystem", "WorkingMemory"]


def __getattr__(name):
    if name == "MemorySystem":
        from .system import MemorySystem
        return MemorySystem
    raise AttributeError(name)
