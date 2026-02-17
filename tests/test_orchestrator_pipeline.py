import os
import sys
import json
import asyncio
from pathlib import Path
import types

import pytest

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Avoid hard dependency on docker for unit tests
if "docker" not in sys.modules:
    sys.modules["docker"] = types.ModuleType("docker")

# Avoid hard dependency on gitpython for unit tests
if "git" not in sys.modules:
    git_stub = types.ModuleType("git")

    class _DummyIndex:
        def add(self, *args, **kwargs):
            return None

        def commit(self, *args, **kwargs):
            return None

    class _DummyRepo:
        def __init__(self, *args, **kwargs):
            self.index = _DummyIndex()

        @staticmethod
        def init(path):
            return _DummyRepo(path)

        def tree(self):
            class _Tree:
                def traverse(self):
                    return []
            return _Tree()

    git_stub.Repo = _DummyRepo
    sys.modules["git"] = git_stub

# Avoid hard dependency on llama_index for unit tests
if "llama_index" not in sys.modules:
    llama_index = types.ModuleType("llama_index")
    llama_index.core = types.ModuleType("llama_index.core")
    llama_index.core.callbacks = types.ModuleType("llama_index.core.callbacks")
    llama_index.core.llms = types.ModuleType("llama_index.core.llms")
    llama_index.core.tools = types.ModuleType("llama_index.core.tools")
    llama_index.core.agent = types.ModuleType("llama_index.core.agent")
    llama_index.core.workflow = types.ModuleType("llama_index.core.workflow")
    llama_index.core.agent.workflow = types.ModuleType("llama_index.core.agent.workflow")
    llama_index.llms = types.ModuleType("llama_index.llms")
    llama_index.llms.ollama = types.ModuleType("llama_index.llms.ollama")
    llama_index.llms.google_genai = types.ModuleType("llama_index.llms.google_genai")
    llama_index.embeddings = types.ModuleType("llama_index.embeddings")
    llama_index.embeddings.ollama = types.ModuleType("llama_index.embeddings.ollama")
    llama_index.embeddings.google_genai = types.ModuleType("llama_index.embeddings.google_genai")

    class _Dummy:
        def __init__(self, *args, **kwargs):
            self.temperature = kwargs.get("temperature", None)

        def chat(self, *args, **kwargs):
            class _Msg:
                message = type("m", (), {"content": ""})()
            return _Msg()

    class _Settings:
        embed_model = None
        callback_manager = None

    class _ChatMessage:
        def __init__(self, role=None, content=None):
            self.role = role
            self.content = content

    class _CallbackManager:
        def __init__(self, *args, **kwargs):
            pass

    class _TokenCountingHandler:
        llm_token_counts = []
        total_llm_token_count = 0
        prompt_llm_token_count = 0
        total_completion_tokens = 0

    class _FunctionTool:
        def __init__(self, fn=None, name=None, description=None):
            self.fn = fn
            self.metadata = type("m", (), {"name": name})()
            self.description = description

        @classmethod
        def from_defaults(cls, fn=None, name=None, description=None):
            return cls(fn=fn, name=name, description=description)

    class _ReActAgent:
        def __init__(self, *args, **kwargs):
            self.tools = kwargs.get("tools", [])
            self.system_prompt = kwargs.get("system_prompt", "")

        def run(self, *args, **kwargs):
            class _Handler:
                async def stream_events(self):
                    if False:
                        yield None
            return _Handler()

    class _Context:
        def __init__(self, *args, **kwargs):
            pass

    class _StopEvent:
        pass

    class _AgentStream:
        delta = ""

    class _ToolCallResult:
        tool_name = ""
        tool_kwargs = {}
        tool_output = ""

    class _AgentOutput:
        response = ""

    llama_index.core.Settings = _Settings
    llama_index.core.llms.ChatMessage = _ChatMessage
    llama_index.core.callbacks.CallbackManager = _CallbackManager
    llama_index.core.callbacks.TokenCountingHandler = _TokenCountingHandler
    llama_index.core.tools.FunctionTool = _FunctionTool
    llama_index.core.agent.ReActAgent = _ReActAgent
    llama_index.core.workflow.Context = _Context
    llama_index.core.workflow.StopEvent = _StopEvent
    llama_index.core.agent.workflow.AgentStream = _AgentStream
    llama_index.core.agent.workflow.ToolCallResult = _ToolCallResult
    llama_index.core.agent.workflow.AgentOutput = _AgentOutput
    llama_index.llms.ollama.Ollama = _Dummy
    llama_index.embeddings.ollama.OllamaEmbedding = _Dummy
    llama_index.llms.google_genai.GoogleGenAI = _Dummy
    llama_index.embeddings.google_genai.GoogleGenAIEmbedding = _Dummy
    llama_index.core.VectorStoreIndex = _Dummy
    llama_index.core.Document = _Dummy

    sys.modules["llama_index"] = llama_index
    sys.modules["llama_index.core"] = llama_index.core
    sys.modules["llama_index.core.callbacks"] = llama_index.core.callbacks
    sys.modules["llama_index.core.llms"] = llama_index.core.llms
    sys.modules["llama_index.core.tools"] = llama_index.core.tools
    sys.modules["llama_index.core.agent"] = llama_index.core.agent
    sys.modules["llama_index.core.workflow"] = llama_index.core.workflow
    sys.modules["llama_index.core.agent.workflow"] = llama_index.core.agent.workflow
    sys.modules["llama_index.llms"] = llama_index.llms
    sys.modules["llama_index.llms.ollama"] = llama_index.llms.ollama
    sys.modules["llama_index.llms.google_genai"] = llama_index.llms.google_genai
    sys.modules["llama_index.embeddings"] = llama_index.embeddings
    sys.modules["llama_index.embeddings.ollama"] = llama_index.embeddings.ollama
    sys.modules["llama_index.embeddings.google_genai"] = llama_index.embeddings.google_genai

# Avoid hard dependency on python-dotenv
if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    def _load_dotenv(*args, **kwargs):
        return None
    dotenv_stub.load_dotenv = _load_dotenv
    sys.modules["dotenv"] = dotenv_stub

# Avoid hard dependency on google.api_core
if "google" not in sys.modules:
    google_stub = types.ModuleType("google")
    api_core_stub = types.ModuleType("google.api_core")
    exceptions_stub = types.ModuleType("google.api_core.exceptions")
    api_core_stub.exceptions = exceptions_stub
    google_stub.api_core = api_core_stub
    sys.modules["google"] = google_stub
    sys.modules["google.api_core"] = api_core_stub
    sys.modules["google.api_core.exceptions"] = exceptions_stub

# Avoid hard dependency on pydantic
if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, *args, **kwargs):
            pass

        @classmethod
        def model_validate(cls, obj):
            return obj

        def model_dump(self):
            return {}

    def _Field(*args, **kwargs):
        return None

    pydantic_stub.BaseModel = _BaseModel
    pydantic_stub.Field = _Field
    sys.modules["pydantic"] = pydantic_stub

from orchestrator import Orchestrator


class DummyConversation:
    def add_message(self, role, message):
        pass


class DummyAgent:
    def __init__(self):
        self._conversations = {}

    def _get_or_create_conversation(self, name):
        if name not in self._conversations:
            self._conversations[name] = DummyConversation()
        return self._conversations[name]

    def clear_conversation(self, name):
        self._conversations.pop(name, None)

    def get_stats(self):
        return {
            "active_conversations": len(self._conversations),
            "call_count": 0,
            "error_count": 0,
            "error_rate": 0.0,
        }


class DummyReviewer(DummyAgent):
    async def review_code(self, task, project_structure, git_diff, previous_issues=None):
        return [], []


class DummyRequirements(DummyAgent):
    def analyze_requirements(self, prompt, _):
        return {"refined_prompt": prompt, "questions": []}


class DummyArchitect(DummyAgent):
    def design_architecture(self, prompt, logger=None):
        return {
            "technology_stack": "Test",
            "file_structure": ["hello.txt"],
            "component_breakdown": {"hello.txt": "Test file"},
            "run_command": "python -c 'print(1)'",
        }


class DummyPlanner:
    def create_plan(self, functional_prompt, technical_architecture, logger):
        return ["[T1] Create hello.txt with greeting (Output: hello.txt created)"], "python -c 'print(1)'"


def _apply_orchestrator_patches(orch, monkeypatch):
    class _DummyToolCall:
        def __init__(self, tool_name, tool_args):
            self.tool_name = tool_name
            self.tool_args = tool_args

        def to_legacy(self):
            return {"tool_name": self.tool_name, "tool_args": self.tool_args}

    class _DummyDevResult:
        def __init__(self, success, output, tool_calls):
            self.success = success
            self.output = output
            self.tool_calls = tool_calls

    async def fake_run_developer_agent(task):
        # Create a file to simulate work
        file_path = os.path.join(orch.project_dir, "hello.txt")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("hello")
        tool_calls = [_DummyToolCall("write_file", {"filename": "hello.txt"})]
        return _DummyDevResult(True, "ok", tool_calls)

    monkeypatch.setattr(orch, "_run_developer_agent", fake_run_developer_agent)
    monkeypatch.setattr(orch, "_get_project_diff", lambda: "")
    monkeypatch.setattr(orch, "_get_project_structure_string", lambda: "")
    monkeypatch.setattr(orch, "_update_index_incrementally", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_build_index_from_disk", lambda: None)
    monkeypatch.setattr(orch, "_git_commit", lambda *a, **k: None)
    monkeypatch.setattr(orch, "_find_placeholders_in_files", lambda *a, **k: [])

    def init_execution_agents():
        orch.dev_agent = DummyAgent()
        orch.reviewer_agent = DummyReviewer()
        orch.tester_agent = None
        orch.unit_test_agent = None
        orch._dev_base_system_prompt = ""

    monkeypatch.setattr(orch, "_init_execution_agents", init_execution_agents)


def _mk_tmp_dir(name: str) -> Path:
    base = ROOT / ".test_tmp"
    base.mkdir(exist_ok=True)
    d = base / name
    d.mkdir(exist_ok=True)
    return d


def test_orchestrator_smoke_mocked(monkeypatch):
    tmp_path = _mk_tmp_dir("orch_smoke")
    monkeypatch.chdir(tmp_path)

    project_name = "smoke_project"
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("Test prompt", encoding="utf-8")

    orch = Orchestrator(
        project_name,
        initial_prompt_file=str(prompt_path),
        provider="ollama",
        force_new=True,
        run_tests=False,
    )

    # Force resume path with a valid plan to avoid planning stages
    orch.plan = ["[T1] Create hello.txt with greeting (Output: hello.txt created)"]
    orch.technical_architecture = {
        "technology_stack": "Test",
        "file_structure": ["hello.txt"],
        "component_breakdown": {"hello.txt": "Test file"},
    }
    orch.last_completed_task_index = -1
    orch.is_resuming = True

    _apply_orchestrator_patches(orch, monkeypatch)

    asyncio.run(orch.run())

    state_path = Path(orch.state_file)
    assert state_path.exists()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["plan"]
    assert state["last_completed_task_index"] >= 0


def test_orchestrator_integration_minimal(monkeypatch):
    tmp_path = _mk_tmp_dir("orch_integration")
    monkeypatch.chdir(tmp_path)

    project_name = "integration_project"
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("Integration prompt", encoding="utf-8")

    orch = Orchestrator(
        project_name,
        initial_prompt_file=str(prompt_path),
        provider="ollama",
        force_new=True,
        run_tests=False,
    )

    # Force resume path with a valid plan to avoid planning stages
    orch.plan = ["[T1] Create hello.txt with greeting (Output: hello.txt created)"]
    orch.technical_architecture = {
        "technology_stack": "Test",
        "file_structure": ["hello.txt"],
        "component_breakdown": {"hello.txt": "Test file"},
    }
    orch.last_completed_task_index = -1
    orch.is_resuming = True

    _apply_orchestrator_patches(orch, monkeypatch)

    asyncio.run(orch.run())

    hello_path = Path(orch.project_dir) / "hello.txt"
    assert hello_path.exists()
    assert hello_path.read_text(encoding="utf-8") == "hello"


def test_contract_validators():
    # Requirements output
    requirements_output = {"refined_prompt": "X", "questions": []}
    assert "refined_prompt" in requirements_output

    # Architecture output
    architecture = {
        "technology_stack": "Test",
        "file_structure": ["a.py"],
        "component_breakdown": {"a.py": "A"},
    }
    assert isinstance(architecture["file_structure"], list)
    assert architecture["file_structure"]

    # Planner output
    plan = ["[T1] Do something"]
    assert isinstance(plan, list) and len(plan) > 0

    # Reviewer output
    review_report = {"issues": [], "confidence": 0.8}
    assert "issues" in review_report
    assert 0.0 <= review_report.get("confidence", 0.0) <= 1.0
