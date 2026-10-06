"""Compatibility wrappers for optional LlamaIndex imports.

This module keeps import-time failures from cascading through tests and
lightweight tooling when the full LlamaIndex stack is not installed.
Runtime usage still raises a clear error when a missing dependency is
actually required.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

LLAMA_INDEX_IMPORT_ERROR: Exception | None = None
LLAMA_INDEX_AVAILABLE = True

try:
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core.agent import ReActAgent
    from llama_index.core.agent.workflow import AgentOutput, AgentStream, ToolCallResult
    from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
    from llama_index.core.llms import ChatMessage
    from llama_index.core.tools import FunctionTool
    from llama_index.core.workflow import Context, StopEvent
except ImportError as exc:  # pragma: no cover - only exercised in minimal installs
    LLAMA_INDEX_AVAILABLE = False
    LLAMA_INDEX_IMPORT_ERROR = exc

    def _raise_missing() -> None:
        raise ModuleNotFoundError(
            "LlamaIndex dependencies are not installed. "
            "Install the appropriate extras, for example `pip install -e .[ollama]` "
            "or `pip install -e .[openai]`."
        ) from LLAMA_INDEX_IMPORT_ERROR

    def _load_runtime(module_path: str, attr_name: str):
        try:
            module = import_module(module_path)
            return getattr(module, attr_name)
        except Exception:
            _raise_missing()

    @dataclass
    class ChatMessage:
        role: str | None = None
        content: str | None = None

    class Settings:
        embed_model: Any = None
        callback_manager: Any = None

    class CallbackManager:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            runtime_cls = _load_runtime("llama_index.core.callbacks", "CallbackManager")
            self.__dict__ = runtime_cls(*_args, **_kwargs).__dict__

    class TokenCountingHandler:
        llm_token_counts = []
        total_llm_token_count = 0
        prompt_llm_token_count = 0
        total_completion_tokens = 0

    class FunctionTool:
        @classmethod
        def from_defaults(cls, *_args: Any, **_kwargs: Any) -> "FunctionTool":
            runtime_cls = _load_runtime("llama_index.core.tools", "FunctionTool")
            return runtime_cls.from_defaults(*_args, **_kwargs)

    class ReActAgent:
        def __new__(cls, *_args: Any, **_kwargs: Any):
            runtime_cls = _load_runtime("llama_index.core.agent", "ReActAgent")
            return runtime_cls(*_args, **_kwargs)

    class Context:
        def __new__(cls, *_args: Any, **_kwargs: Any):
            runtime_cls = _load_runtime("llama_index.core.workflow", "Context")
            return runtime_cls(*_args, **_kwargs)

    class StopEvent:
        pass

    class AgentStream:
        delta = ""

    class ToolCallResult:
        tool_name = ""
        tool_kwargs = {}
        tool_output = ""

    class AgentOutput:
        response = ""

    class Document:
        def __new__(cls, *_args: Any, **_kwargs: Any):
            runtime_cls = _load_runtime("llama_index.core", "Document")
            return runtime_cls(*_args, **_kwargs)

    class VectorStoreIndex:
        @classmethod
        def from_documents(cls, *_args: Any, **_kwargs: Any) -> "VectorStoreIndex":
            runtime_cls = _load_runtime("llama_index.core", "VectorStoreIndex")
            return runtime_cls.from_documents(*_args, **_kwargs)


def _provider_class(module_path: str, name: str, extra: str):
    """Resolve only the selected provider; other provider extras stay optional."""

    class LazyProvider:
        def __new__(cls, *args, **kwargs):
            try:
                runtime_class = getattr(import_module(module_path), name)
            except ImportError as exc:
                raise ModuleNotFoundError(
                    f"Install the '{extra}' extra to use {name}: pip install -e .[{extra}]"
                ) from exc
            return runtime_class(*args, **kwargs)

    LazyProvider.__name__ = name
    return LazyProvider


GoogleGenAI = _provider_class("llama_index.llms.google_genai", "GoogleGenAI", "google")
GoogleGenAIEmbedding = _provider_class(
    "llama_index.embeddings.google_genai", "GoogleGenAIEmbedding", "google"
)
Ollama = _provider_class("llama_index.llms.ollama", "Ollama", "ollama")
OllamaEmbedding = _provider_class("llama_index.embeddings.ollama", "OllamaEmbedding", "ollama")
OpenAILike = _provider_class("llama_index.llms.openai_like", "OpenAILike", "openai")
OpenAILikeEmbedding = _provider_class(
    "llama_index.embeddings.openai_like", "OpenAILikeEmbedding", "openai"
)
