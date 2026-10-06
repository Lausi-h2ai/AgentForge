"""Provider routing, chat-only operation, configuration validation, and CLI precedence."""

import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents import utils
from aidev_orchestrator import orchestrator as runtime
from orchestrator_core.pipeline.task_escalation import TaskEscalationPolicy
from orchestrator_core.provider_config import api_base, openai_llm_args, resolve_provider


@pytest.fixture
def endpoint(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("OPENAI_", "LLM_", "EMBEDDING_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8080/v1/")
    monkeypatch.setenv("LLM_MODEL", "vendor/arbitrary-model")


def test_arbitrary_model_and_auth_free_endpoint(endpoint):
    args = openai_llm_args()
    assert args["model"] == "vendor/arbitrary-model"
    assert args["api_base"] == "http://localhost:8080/v1"
    assert args["api_key"] == "not-required"
    assert args["is_chat_model"] is True
    assert args["is_function_calling_model"] is False


def test_credentials_and_escalated_model_override(endpoint, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    assert openai_llm_args("stronger/model")["model"] == "stronger/model"
    assert openai_llm_args()["api_key"] == "test-secret"
    monkeypatch.setenv("LLM_ESCALATION_MODEL", "stronger/model")
    policy = TaskEscalationPolicy.from_env()
    assert policy.get_escalation_model("openai") == "stronger/model"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ftp://localhost/v1",
        "https://user:secret@host/v1",
        "https://host/v1?key=secret",
        "http://host/v1/chat/completions",
    ],
)
def test_invalid_endpoint_fails_without_echoing_credentials(endpoint, monkeypatch, value):
    monkeypatch.setenv("OPENAI_BASE_URL", value)
    with pytest.raises(ValueError) as error:
        api_base("OPENAI_BASE_URL")
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "name,value",
    [
        ("LLM_MODEL", ""),
        ("LLM_MAX_TOKENS", "0"),
        ("LLM_CONTEXT_WINDOW", "bad"),
        ("LLM_REQUEST_TIMEOUT", "nan"),
        ("OPENAI_ADDITIONAL_KWARGS", "[]"),
        ("OPENAI_ADDITIONAL_KWARGS", '{"model":"other"}'),
    ],
)
def test_invalid_model_settings_fail_early(endpoint, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        openai_llm_args()


def test_chat_only_provider_never_constructs_embeddings(endpoint, monkeypatch):
    settings = SimpleNamespace()
    monkeypatch.setattr(utils, "Settings", settings)
    monkeypatch.setattr(utils, "TokenCountingHandler", lambda: "counter")
    monkeypatch.setattr(utils, "CallbackManager", lambda handlers: handlers)

    def unexpected(*args, **kwargs):
        pytest.fail("Chat-only configuration attempted to construct embeddings")

    for name in ("OllamaEmbedding", "GoogleGenAIEmbedding", "OpenAILikeEmbedding"):
        monkeypatch.setattr(utils, name, unexpected)
    llm_class, args, counter = utils.configure_llm_and_embed("openai")
    assert llm_class is utils.OpenAILike
    assert counter == "counter"
    assert not hasattr(settings, "embed_model")
    assert args["model"] == "vendor/arbitrary-model"


def test_separate_embedding_endpoint_and_credentials(endpoint, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "custom-embed")
    monkeypatch.setenv("OPENAI_EMBEDDING_BASE_URL", "http://localhost:9090/v1")
    monkeypatch.setenv("OPENAI_EMBEDDING_API_KEY", "embedding-secret")
    monkeypatch.setattr(utils, "Settings", SimpleNamespace())
    monkeypatch.setattr(utils, "TokenCountingHandler", lambda: "counter")
    monkeypatch.setattr(utils, "CallbackManager", lambda handlers: handlers)
    captured = {}

    def embedding(**kwargs):
        captured.update(kwargs)
        return "embedding-instance"

    monkeypatch.setattr(utils, "OpenAILikeEmbedding", embedding)
    utils.configure_llm_and_embed("openai")
    assert captured["api_base"] == "http://localhost:9090/v1"
    assert captured["api_key"] == "embedding-secret"
    assert captured["model_name"] == "custom-embed"


def test_disabled_index_still_loads_files(endpoint, tmp_path):
    (tmp_path / "hello.py").write_text("print('hello')", encoding="utf-8")
    orch = runtime.Orchestrator.__new__(runtime.Orchestrator)
    from orchestrator_core.blackboard import BlackboardState

    orch.blackboard = BlackboardState()
    orch.project_dir = str(tmp_path)
    orch.embeddings_enabled = False
    orch._build_index_from_disk()
    assert "hello.py" in orch.files
    assert orch.code_index is None
    assert "read_file" in orch._get_rag_context("hello")


@pytest.mark.parametrize(
    "arguments,expected",
    [
        ([], "openai"),
        (["--provider", "ollama"], "ollama"),
        (["--google"], "google"),
        (["--provider", "openai-compatible"], "openai"),
    ],
)
def test_cli_provider_precedence(endpoint, monkeypatch, arguments, expected):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    captured = {}

    class Dummy:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        async def run(self):
            pass

    monkeypatch.setattr(runtime, "Orchestrator", Dummy)
    assert runtime.main(["project", "--prompt", "prompt.txt", *arguments]) == 0
    assert captured["provider"] == expected
    assert resolve_provider("openai-compatible") == "openai"


def test_real_sdk_transport_in_isolated_process():
    # Existing tests can install global SDK stubs; isolate the real transport test.
    for package in ("llama-index-llms-openai-like", "llama-index-embeddings-openai-like"):
        try:
            importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pytest.skip("Install .[openai,dev] for the real SDK transport test")
    script = Path(__file__).with_name("openai_transport_probe.py")
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
