"""Modelos de IA: cliente do Ollama e roteador dinâmico."""
from .ollama_client import ChatResult, ModelInfo, OllamaClient, OllamaError
from .router import ModelRouter, ModelUnavailable, Selection

__all__ = ["ChatResult", "ModelInfo", "OllamaClient", "OllamaError", "ModelRouter",
           "ModelUnavailable", "Selection"]
