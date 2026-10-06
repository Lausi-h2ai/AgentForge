"""
Improved Orchestrator for Multi-Agent Software Development System

Key Improvements:
- Unified state management with atomic writes
- Git-based rollback on task failure  
- Better error handling and retry logic
- Conversation history between agents
- Progress tracking and visualization
- Per-agent token usage tracking
- Enhanced logging with call stacks
- Architecture validation
"""

import re
import os
import json
import ast
import sys
import asyncio
import traceback
from importlib import import_module
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from .skill_manager import SkillManager
from memory import MemoryManager
from agents.llama_compat import Document, VectorStoreIndex

try:
    import git
except ImportError:  # pragma: no cover - exercised only in minimal installs
    git = None

from orchestrator_core.contracts.execution import DeveloperRunResult
from orchestrator_core.blackboard import BlackboardState
from orchestrator_core.provider_config import embedding_provider, resolve_provider
from orchestrator_core.pipeline import (
    StageContext,
    TaskEscalationPolicy,
    TaskEscalationState,
    execute_development_stage,
    execute_finalization_stage,
    execute_planning_stage,
    execute_review_stage,
    execute_testing_stage,
)

# Load environment variables
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only in minimal installs
    def load_dotenv(*_args, **_kwargs):
        return None

load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# Review timeout configuration (seconds)
REVIEW_TIMEOUT_CONFIG = {
    "simple": _env_int("REVIEW_TIMEOUT_SIMPLE", 60),
    "medium": _env_int("REVIEW_TIMEOUT_MEDIUM", 120),
    "complex": _env_int("REVIEW_TIMEOUT_COMPLEX", 180),
}

# Import refactored agents
from agents import (
    DeveloperAgent,
    CodeReviewerAgent,
    ProductOwnerAgent,
    RequirementsAnalystAgent,
    SoftwareArchitectAgent,
    DocumentationAgent,
    UnitTestAgent,
    TesterAgent,
    configure_llm_and_embed,
    resolve_model_config,
)

# Import supporting modules (assumed to exist):
from .orchestrator_tools import OrchestratorTools


from .structured_logger import StructuredLogger
from .metrics_tracker import MetricsTracker
from .cost_tracker import CostTracker

try:
    from .config import debug
except ImportError:
    debug = False


def _require_git_dependency():
    global git
    if git is not None:
        return git
    try:
        git = import_module("git")
        return git
    except ImportError as exc:
        raise ModuleNotFoundError(
            "GitPython is not installed. Install the base or dev dependencies to use "
            "workspace initialization and rollback features."
        ) from exc


class TaskStatus(Enum):
    """Enhanced task execution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DEVELOPED = "developed"
    REVIEWED = "reviewed"
    TESTED = "tested"
    ARCHITECTURE_VALIDATED = "architecture_validated"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class TaskCheckpoint:
    """Enhanced checkpoint with more metadata"""
    task_index: int
    task_description: str
    status: str
    timestamp: str
    
    # Execution details
    development_output: Optional[str] = None
    review_feedback: Optional[List[Dict]] = None
    test_results: Optional[str] = None
    architecture_validation: Optional[Dict] = None
    
    # Retry tracking
    retry_count: int = 0
    retry_history: List[Dict] = field(default_factory=list)
    
    # File tracking
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    
    # Dependencies
    depends_on: List[int] = field(default_factory=list)
    blocked_by: List[int] = field(default_factory=list)
    
    # Git tracking
    git_commit_sha: Optional[str] = None
    git_stash_ref: Optional[str] = None  # NEW: For rollback
    
    # Agent interactions
    agent_interactions: List[Dict] = field(default_factory=list)
    
    def add_retry(self, error_type: str, error_message: str):
        """Record a retry attempt"""
        self.retry_count += 1
        self.retry_history.append({
            "attempt": self.retry_count,
            "error_type": error_type,
            "error_message": error_message[:500],  # Truncate long errors
            "timestamp": datetime.now().isoformat()
        })
    
    def add_agent_interaction(self, from_agent: str, to_agent: str, message: str, response: str):
        """Record an agent interaction"""
        self.agent_interactions.append({
            "from": from_agent,
            "to": to_agent,
            "message": message[:200],
            "response": response[:200],
            "timestamp": datetime.now().isoformat()
        })


class ProgressTracker:
    """Track and display progress of multi-agent work"""
    
    def __init__(self, total_tasks: int):
        self.total_tasks = total_tasks
        self.completed_tasks = 0
        self.processed_tasks = 0
        self.current_task = None
        self.start_time = datetime.now()
        self.task_start_time = None
        self.task_times = []
    
    def start_task(self, task_index: int, task_description: str):
        """Mark task as started"""
        self.current_task = {
            "index": task_index,
            "description": task_description,
            "start_time": datetime.now()
        }
        self.task_start_time = datetime.now()
        self._print_progress()
    
    def complete_task(self, success: bool = True):
        """Mark current task as completed"""
        if not self.current_task:
            return
        
        elapsed = (datetime.now() - self.task_start_time).total_seconds()
        self.task_times.append(elapsed)
        self.processed_tasks += 1

        if success:
            self.completed_tasks += 1
        
        self.current_task = None
        self._print_progress()
    
    def _print_progress(self):
        """Print current progress"""
        progress_pct = (self.processed_tasks / self.total_tasks) * 100 if self.total_tasks > 0 else 0
        
        # Create progress bar
        bar_width = 40
        filled = int(bar_width * progress_pct / 100)
        bar = "???" * filled + "???" * (bar_width - filled)
        
        # Calculate ETA
        eta_str = self._calculate_eta()
        
        # Print
        print(f"\n{'='*60}")
        print(f"Progress: [{bar}] {progress_pct:.1f}%")
        print(f"Tasks: completed={self.completed_tasks}/{self.total_tasks}, processed={self.processed_tasks}/{self.total_tasks}")
        
        if self.current_task:
            task_elapsed = (datetime.now() - self.task_start_time).total_seconds()
            print(f"Current: Task {self.current_task['index'] + 1} ({task_elapsed:.1f}s elapsed)")
            print(f"  {self.current_task['description'][:50]}...")
        
        print(f"ETA: {eta_str}")
        print(f"{'='*60}\n")
    
    def _calculate_eta(self) -> str:
        """Calculate estimated time remaining"""
        if not self.task_times or self.processed_tasks == 0:
            return "Calculating..."
        
        avg_time_per_task = sum(self.task_times) / len(self.task_times)
        remaining_tasks = self.total_tasks - self.processed_tasks
        
        eta_seconds = avg_time_per_task * remaining_tasks
        
        if eta_seconds < 60:
            return f"{int(eta_seconds)}s"
        elif eta_seconds < 3600:
            return f"{int(eta_seconds / 60)}m {int(eta_seconds % 60)}s"
        else:
            hours = int(eta_seconds / 3600)
            minutes = int((eta_seconds % 3600) / 60)
            return f"{hours}h {minutes}m"


class Orchestrator:
    """
    Enhanced orchestrator with:
    - Unified state management
    - Git-based rollback
    - Progress tracking
    - Better error handling
    """

    @property
    def plan(self) -> List[str]:
        return self.blackboard.plan

    @plan.setter
    def plan(self, value: List[str]) -> None:
        self.blackboard.plan = value or []

    @property
    def sadt_plan(self) -> Optional[List[str]]:
        return self.blackboard.sadt_plan

    @sadt_plan.setter
    def sadt_plan(self, value: Optional[List[str]]) -> None:
        self.blackboard.sadt_plan = value

    @property
    def planner_source(self) -> Optional[str]:
        return self.blackboard.planner_source

    @planner_source.setter
    def planner_source(self, value: Optional[str]) -> None:
        self.blackboard.planner_source = value

    @property
    def files(self) -> Dict[str, Any]:
        return self.blackboard.files

    @files.setter
    def files(self, value: Dict[str, Any]) -> None:
        self.blackboard.files = value or {}

    @property
    def run_command(self) -> str:
        return self.blackboard.run_command

    @run_command.setter
    def run_command(self, value: str) -> None:
        self.blackboard.run_command = value or ""

    @property
    def technical_architecture(self) -> Optional[Dict]:
        return self.blackboard.technical_architecture

    @technical_architecture.setter
    def technical_architecture(self, value: Optional[Dict]) -> None:
        self.blackboard.technical_architecture = value

    @property
    def last_completed_task_index(self) -> int:
        return self.blackboard.last_completed_task_index

    @last_completed_task_index.setter
    def last_completed_task_index(self, value: int) -> None:
        self.blackboard.last_completed_task_index = int(value) if value is not None else -1

    @property
    def task_checkpoints(self) -> Dict[int, TaskCheckpoint]:
        return self.blackboard.task_checkpoints

    @task_checkpoints.setter
    def task_checkpoints(self, value: Dict[int, TaskCheckpoint]) -> None:
        self.blackboard.task_checkpoints = value or {}
    
    def __init__(
        self,
        project_name,
        initial_prompt_file=None,
        provider=None,
        force_new=False,
        run_tests=False,
        planning_model: Optional[str] = None,
        execution_model: Optional[str] = None,
    ):
        """
        Initialize orchestrator.
        
        Args:
            project_name: Name of the project
            initial_prompt_file: Path to initial prompt file
            provider: LLM provider ("openai", "ollama", or "google")
            force_new: Force new project (ignore existing state)
            run_tests: Enable testing phase
        """
        
        # --- 1. CORE SETUP ---
        self.logger = StructuredLogger()
        self.provider = resolve_provider(provider)
        self.embeddings_enabled = embedding_provider(self.provider) != "none"
        env_planning_model, env_execution_model, env_escalation_models = resolve_model_config(self.provider)
        self.planning_model = planning_model or env_planning_model
        self.execution_model = execution_model or env_execution_model or self.planning_model

        llm_class, llm_args, token_counter = self._configure_llm(self.planning_model)
        self._llm_class = llm_class
        self._llm_args = llm_args
        
        self.metrics_tracker = MetricsTracker()
        
        # --- 2. PROJECT PATHS ---
        self.project_name = project_name
        self.project_path = os.path.join(".", "projects", project_name)
        self.requirements_file = os.path.join(self.project_path, "requirements.md")
        self.workspace_dir = os.path.join(self.project_path, "workspace")
        self.state_file = os.path.join(self.project_path, "state.json")
        self.checkpoint_file = os.path.join(self.project_path, "checkpoints.json")
        
        self.project_dir = self.workspace_dir
        self.repo = None
        self.run_tests_enabled = run_tests
        self.blackboard = BlackboardState()
        
        # --- 3. STATE VARIABLES ---
        self.technical_architecture = None
        self.plan = []
        self.sadt_plan = None
        self.planner_source = None
        self.files = {}  # Dictionary { 'filename': 'content' }
        self.run_command = ""
        self.last_completed_task_index = -1
        self.code_index = None
        
        # NEW: Enhanced tracking
        self.task_checkpoints: Dict[int, TaskCheckpoint] = {}
        self.max_retry_attempts = 10
        self.architecture_violations: List[Dict] = []
        self.progress_tracker = None  # Initialized when plan is ready
        self.is_resuming = False
        self.default_execution_model = self.execution_model
        self.active_execution_model = self.execution_model
        self.default_planning_model = self.planning_model
        self.active_planning_model = self.planning_model
        self.planning_escalation_enabled = os.getenv("PLANNER_ESCALATION_ENABLED", "false").lower() == "true"
        self.planning_escalation_failure_threshold = _env_int("PLANNER_ESCALATION_FAILURE_THRESHOLD", 1)
        self.planning_max_attempts = _env_int("PLANNER_MAX_ATTEMPTS", 2)
        self.planning_escalation_models = dict(env_escalation_models)
        self.task_escalation_policy = TaskEscalationPolicy.from_env()
        self.task_escalation_states: Dict[int, TaskEscalationState] = {}
        
        # --- 4. LOAD PROMPT ---
        if os.path.exists(self.requirements_file) and not force_new:
            with open(self.requirements_file, 'r', encoding='utf-8') as f:
                self.user_prompt = f.read()
        elif initial_prompt_file:
            with open(initial_prompt_file, 'r', encoding='utf-8') as f:
                self.user_prompt = f.read()
        else:
            raise ValueError("No requirements file found and no initial prompt file provided.")
        
        # --- 5. STATE MANAGEMENT ---
        if os.path.exists(self.state_file) and not force_new:
            self.logger.log("INFO", "Resuming existing project...")
            self._load_state()
            self._load_checkpoints()
            _require_git_dependency()
            self.repo = git.Repo(self.project_dir)
            self._build_index_from_disk()
            self.is_resuming = True
        else:
            self.logger.log("INFO", "Starting a new project...")
            self._clean_workspace()
            self.is_resuming = False
        
        # --- 6. AGENT INITIALIZATION ---
        # Create tools (pass self for access to files)
        if OrchestratorTools:
            tools = OrchestratorTools(self)
        else:
            # Minimal tools implementation if import failed
            tools = self._create_minimal_tools()
        
        #Initialize skill manager
        self.skill_manager = SkillManager(skills_directory="./skills",cache_dir="./skill_cache")

        self.tools = tools

        # Initialize memory manager (local-only defaults)
        self.memory = MemoryManager(
            enabled=os.getenv("HIPPOCAMP_AI_ENABLED", "false").lower() == "true",
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            llm_provider=os.getenv("HIPPOCAMP_AI_LLM_PROVIDER", "ollama"),
            llm_model=os.getenv("HIPPOCAMP_AI_LLM_MODEL"),
            logger=self.logger,
            enable_global_memory=True
        )

        # Initialize planning agents with planning model
        self.po_agent = None
        self.requirements_agent = None
        self.architect_agent = None
        self.doc_agent = None
        self.sadt_sart_agent = None
        self._init_planning_agents(self.planning_model)

        # Execution agents initialized later (after planning/model switch)
        self.dev_agent = None
        self.reviewer_agent = None
        self.tester_agent = None
        self.unit_test_agent = None

        # Preserve base system prompt to avoid unbounded growth when injecting skills.
        self._dev_base_system_prompt = None

        # File verification is expensive; keep it on by default to avoid empty tool runs.
        self.enable_file_verification = os.getenv("ENABLE_FILE_VERIFICATION", "true").lower() == "true"
        
        # Seed tool-usage memory guidance (global + project scopes)
        self._seed_tool_usage_memory()
        
        
        
        print(f"\n??? Orchestrator initialized for project: {project_name}")
        print(f"   Provider: {self.provider}")
        if self.planning_model:
            print(f"   Planning Model: {self.planning_model}")
        print(f"   Model: {self.model_name}")
        print(f"   Testing: {'Enabled' if run_tests else 'Disabled'}")
        print(f"   Loaded {len(self.skill_manager.skills)} skills")

    def _configure_llm(self, model_override: Optional[str] = None):
        """(Re)configure LLM + embeddings for a given model."""
        llm_class, llm_args, token_counter = configure_llm_and_embed(self.provider, model_override)
        self.model_name = llm_args.get("model_name") or llm_args.get("model")

        if hasattr(self, "cost_tracker") and self.cost_tracker:
            self.cost_tracker.token_counter = token_counter
            self.cost_tracker.processed_calls = 0
        else:
            self.cost_tracker = CostTracker(token_counter)

        return llm_class, llm_args, token_counter

    def _init_planning_agents(self, model_override: Optional[str] = None):
        """Initialize planning-phase agents using a selected model."""
        selected_model = model_override or self.planning_model
        llm_class, llm_args, _ = self._configure_llm(selected_model)
        self._llm_class = llm_class
        self._llm_args = llm_args

        self.po_agent = ProductOwnerAgent(self._llm_class, self._llm_args)
        self.requirements_agent = RequirementsAnalystAgent(self._llm_class, self._llm_args)
        self.architect_agent = SoftwareArchitectAgent(self._llm_class, self._llm_args)
        self.doc_agent = DocumentationAgent(self._llm_class, self._llm_args)

        try:
            from agents import SADTSARTPlannerAgent
            self.sadt_sart_agent = SADTSARTPlannerAgent(self._llm_class, self._llm_args)
        except ImportError:
            print("?????? SADTSARTPlannerAgent not available, using simple planner")
            self.sadt_sart_agent = None

        self.active_planning_model = selected_model

    def _ensure_planning_model(self, model_override: Optional[str] = None) -> None:
        selected_model = model_override or self.planning_model
        if self.active_planning_model == selected_model:
            return
        self._init_planning_agents(selected_model)
        if self.logger:
            self.logger.log("INFO", f"Planning agents set to model: {selected_model}")

    def _init_execution_agents(self, model_override: Optional[str] = None):
        """Initialize execution-phase agents using a selected model."""
        selected_model = model_override or self.execution_model
        llm_class, llm_args, _ = self._configure_llm(selected_model)
        self._llm_class = llm_class
        self._llm_args = llm_args

        self.dev_agent = DeveloperAgent(llm_class, llm_args, self.tools, self.logger, self.skill_manager)
        self.reviewer_agent = CodeReviewerAgent(llm_class, llm_args, self.tools, self.logger, self.skill_manager)
        self.tester_agent = TesterAgent(llm_class, llm_args, self.project_dir) if self.run_tests_enabled else None
        self.unit_test_agent = UnitTestAgent(llm_class, llm_args)
        self.active_execution_model = selected_model

        # Preserve base system prompt to avoid unbounded growth when injecting skills.
        self._dev_base_system_prompt = self.dev_agent.agent.system_prompt

    def _normalize_retry_signature(self, retry_entry: Dict[str, Any]) -> str:
        error_type = str((retry_entry or {}).get("error_type", "")).strip().lower()
        return error_type or "unknown"

    def _observe_task_retry_and_maybe_escalate(
        self,
        task_index: int,
        checkpoint: TaskCheckpoint,
        agent_name: str,
    ) -> None:
        if task_index not in self.task_escalation_states:
            self.task_escalation_states[task_index] = self.task_escalation_policy.new_task_state()
        state = self.task_escalation_states[task_index]
        if not checkpoint.retry_history:
            return

        action_signature = self._normalize_retry_signature(checkpoint.retry_history[-1])
        self.task_escalation_policy.observe_attempt(
            state,
            agent_name,
            action_signature,
            progress_made=False,
        )

        eligible = self.task_escalation_policy.should_escalate(state)
        escalated = self.task_escalation_policy.try_escalate(
            state,
            provider=self.provider,
            agent_name=agent_name,
            attempt_number=checkpoint.retry_count + 1,
        )
        if escalated:
            escalation_model = self.task_escalation_policy.resolve_model(
                state,
                provider=self.provider,
                default_model=self.default_execution_model,
            )
            if self.logger:
                self.logger.log(
                    "WARNING",
                    f"Task escalation triggered on task {task_index + 1} by {agent_name}: "
                    f"repeat={state.repeat_count}, no_progress={state.no_progress_count}, model={escalation_model}",
                )
            print(
                f"??????  Escalating task {task_index + 1} to stronger model "
                f"(repeat={state.repeat_count}, no_progress={state.no_progress_count})"
            )
        elif eligible:
            if self.logger:
                self.logger.log(
                    "WARNING",
                    f"Task escalation eligible on task {task_index + 1}, but no escalation model configured "
                    f"for provider '{self.provider}'",
                )

    def _resolve_task_model(self, task_index: int) -> Optional[str]:
        state = self.task_escalation_states.get(task_index)
        if not state:
            return self.default_execution_model
        return self.task_escalation_policy.resolve_model(
            state,
            provider=self.provider,
            default_model=self.default_execution_model,
        )

    def _ensure_execution_model(self, model_override: Optional[str]) -> None:
        selected_model = model_override or self.execution_model
        if self.dev_agent and self.reviewer_agent and self.active_execution_model == selected_model:
            return
        self._init_execution_agents(selected_model)
        if self.logger:
            self.logger.log("INFO", f"Execution agents set to model: {selected_model}")

    def _inject_skills(self, base_message: str, task_description: str, 
                      agent_type: str) -> str:
        """Inject relevant skills into system message."""
        
        # Token budgets by agent type
        budgets = {
            'developer': 40000,   # Developers need detailed guidance
            'planner': 20000,     # Planners need less
            'reviewer': 30000,    # Reviewers need comprehensive rules
        }
        
        budget = budgets.get(agent_type, 30000)
        
        # Get relevant skills
        skills_content = self.skill_manager.get_skills_for_task(
            task_description=task_description,
            token_budget=budget
        )
        
        if skills_content:
            # Inject at the end of system message
            return f"{base_message}\n\n{skills_content}"
        else:
            return base_message

    def _seed_tool_usage_memory(self) -> None:
        guidance = (
            "Tool usage rules: list_files takes no args. read_file requires filename. "
            "write_file only for new files. insert_text/replace_text for existing files. "
            "submit_review input must be {\"report\": {\"issues\": [...], \"confidence\": 0.x}} "
            "and must not include args/kwargs wrappers."
        )
        self._remember_memory(
            content=guidance,
            agent_name=None,
            memory_type="procedural",
            tags=["tool_rules", "global_guidance", f"project:{self.project_name}"],
            importance=0.9,
            store_global=True,
        )

    def _detect_reviewer_tool_errors(self, review_history: List[Dict]) -> bool:
        if not review_history:
            return False

        def _extract_result_dict(raw_result) -> Optional[Dict]:
            if isinstance(raw_result, dict):
                return raw_result
            text = str(raw_result or "").strip()
            if not text:
                return None
            # Tool outputs are sometimes repr(dict) wrapped in another object repr.
            match = re.search(r"\{.*\}", text, re.DOTALL)
            candidate = match.group(0) if match else text
            try:
                return ast.literal_eval(candidate)
            except Exception:
                try:
                    return json.loads(candidate)
                except Exception:
                    return None

        for entry in review_history:
            result = str(entry.get("result", "")).lower()
            tool_name = str(entry.get("tool_name", "")).lower()
            if tool_name not in ("list_files", "read_file", "get_code_summary", "directory_exists", "recall_memory", "submit_review"):
                continue

            structured = _extract_result_dict(entry.get("result"))
            if isinstance(structured, dict):
                if structured.get("success") is False:
                    return True
                if structured.get("success") is True:
                    continue
                if "error" in structured and structured.get("error"):
                    return True

            # Fallback to textual markers for genuine tool-call schema/runtime failures only.
            if (
                "unexpected keyword argument" in result
                or "missing required positional argument" in result
                or "validation error" in result
                or "traceback" in result
                or "toolerror" in result
            ):
                if "success': true" in result or '"success": true' in result:
                    continue
                return True
        return False

    def _get_memory_context(
        self,
        query: str,
        agent_name: Optional[str] = None,
        top_k: int = 5,
        max_chars: int = 2000,
    ) -> str:
        if not getattr(self, "memory", None):
            return ""
        if not self.memory.enabled:
            return ""
        try:
            return self.memory.recall_combined(
                query=query,
                project_name=self.project_name,
                agent_name=agent_name,
                top_k=top_k,
                max_chars=max_chars,
            )
        except Exception:
            return ""

    def _remember_memory(
        self,
        content: str,
        agent_name: Optional[str],
        memory_type: str,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        store_global: bool = False,
    ) -> None:
        if not getattr(self, "memory", None) or not self.memory.enabled:
            return
        try:
            self.memory.remember(
                content=content,
                project_name=self.project_name,
                agent_name=agent_name,
                memory_type=memory_type,
                importance=importance,
                tags=tags or [],
                store_global=store_global,
            )
        except Exception:
            return

    def _truncate_text(self, text: str, max_len: int = 1500) -> str:
        if text is None:
            return ""
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    def _make_stage_context(
        self,
        task: Optional[str] = None,
        checkpoint: Optional[TaskCheckpoint] = None,
        current_task_index: Optional[int] = None,
        savepoint: Optional[str] = None,
    ) -> StageContext:
        """Build a consistent stage context object for pipeline calls."""
        return StageContext(
            self,
            task=task,
            checkpoint=checkpoint,
            current_task_index=current_task_index,
            savepoint=savepoint,
        )
        

    async def _run_developer_agent(self, task_description) -> DeveloperRunResult:
        """Run developer with relevant skills injected."""
        
        # Inject relevant skills into system message (without mutating the base prompt permanently)
        injected_prompt = self._inject_skills(
            base_message=self._dev_base_system_prompt,
            task_description=task_description,
            agent_type='developer'
        )
        original_prompt = self.dev_agent.agent.system_prompt
        self.dev_agent.agent.system_prompt = injected_prompt

        try:
            success, dev_output, tool_calls = await self.dev_agent.run(
                task_description,
                system_prompt=injected_prompt
            )
            return DeveloperRunResult.from_legacy(success, dev_output, tool_calls)
        finally:
            self.dev_agent.agent.system_prompt = original_prompt
    
    def _create_minimal_tools(self):
        """Create minimal tools implementation if OrchestratorTools not available"""
        class MinimalTools:
            def __init__(self, orchestrator):
                self.orch = orchestrator
            
            def read_file(self, filename):
                if filename in self.orch.files:
                    return {"success": True, "content": self.orch.files[filename]}
                return {"success": False, "error": f"File '{filename}' not found"}
            
            def write_file(self, filename, content):
                self.orch.files[filename] = content
                filepath = os.path.join(self.orch.project_dir, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                return {"success": True, "message": f"File '{filename}' written"}
            
            def list_files(self):
                return list(self.orch.files.keys())
            
            def get_code_summary(self, filename):
                if filename not in self.orch.files:
                    return "File not found"
                content = self.orch.files[filename]
                try:
                    tree = ast.parse(content)
                    summary = []
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            summary.append(f"Class: {node.name}")
                        elif isinstance(node, ast.FunctionDef):
                            summary.append(f"Function: {node.name}")
                    return "\n".join(summary) if summary else "No classes or functions found"
                except:
                    return "Could not parse file"
            
            def submit_review(self, report):
                return {"success": True, "report_received": True}
            
            def replace_text(self, filename, old_text, new_text):
                if filename not in self.orch.files:
                    return {"success": False, "error": "File not found"}
                content = self.orch.files[filename]
                if old_text not in content:
                    return {"success": False, "error": "Old text not found"}
                new_content = content.replace(old_text, new_text, 1)
                self.orch.files[filename] = new_content
                filepath = os.path.join(self.orch.project_dir, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return {"success": True}
            
            def insert_text(self, filename, content_to_insert, before_text=None, after_text=None):
                if filename not in self.orch.files:
                    return {"success": False, "error": "File not found"}
                content = self.orch.files[filename]
                if after_text and after_text in content:
                    new_content = content.replace(after_text, after_text + "\n" + content_to_insert, 1)
                elif before_text and before_text in content:
                    new_content = content.replace(before_text, content_to_insert + "\n" + before_text, 1)
                else:
                    new_content = content + "\n" + content_to_insert
                self.orch.files[filename] = new_content
                filepath = os.path.join(self.orch.project_dir, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return {"success": True}
            
            def create_directory(self, dirname):
                dirpath = os.path.join(self.orch.project_dir, dirname)
                os.makedirs(dirpath, exist_ok=True)
                return {"success": True}
            
            def delete_file(self, filename):
                if filename in self.orch.files:
                    del self.orch.files[filename]
                filepath = os.path.join(self.orch.project_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                return {"success": True}
            
            def add_code_block(self, filepath, new_code, location, target_name=None):
                # Simplified version - just append
                if filepath not in self.orch.files:
                    return {"success": False, "error": "File not found"}
                content = self.orch.files[filepath]
                new_content = content + "\n\n" + new_code
                self.orch.files[filepath] = new_content
                file_path = os.path.join(self.orch.project_dir, filepath)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return {"success": True}
            
            def refactor_rename_symbol(self, filepath, old_name, new_name, symbol_type="all"):
                # Simplified version - just replace
                if filepath not in self.orch.files:
                    return {"success": False, "error": "File not found"}
                content = self.orch.files[filepath]
                new_content = content.replace(old_name, new_name)
                self.orch.files[filepath] = new_content
                file_path = os.path.join(self.orch.project_dir, filepath)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return {"success": True, "occurrences": content.count(old_name)}
            
            def delete_code_block(self, filepath, block_name, block_type="auto"):
                # Simplified version - remove lines containing block_name
                if filepath not in self.orch.files:
                    return {"success": False, "error": "File not found"}
                content = self.orch.files[filepath]
                lines = content.split('\n')
                new_lines = [line for line in lines if block_name not in line]
                new_content = '\n'.join(new_lines)
                self.orch.files[filepath] = new_content
                file_path = os.path.join(self.orch.project_dir, filepath)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return {"success": True}
            
            def call_agent(self, agent_name, message):
                # Route to appropriate agent
                agent_map = {
                    "ProductOwnerAgent": self.orch.po_agent,
                    "CodeReviewerAgent": self.orch.reviewer_agent,
                    "DeveloperAgent": self.orch.dev_agent,
                }
                agent = agent_map.get(agent_name)
                if agent:
                    # Run async chat in sync context
                    loop = asyncio.get_event_loop()
                    return loop.run_until_complete(agent.chat(message))
                return f"Agent {agent_name} not found"
        
        return MinimalTools(self)
    
    # ==================== STATE MANAGEMENT ====================
    
    def _clean_workspace(self):
        """Clean workspace and initialize git"""
        _require_git_dependency()
        os.makedirs(self.project_path, exist_ok=True)
        os.makedirs(self.workspace_dir, exist_ok=True)
        
        if not os.path.exists(os.path.join(self.workspace_dir, ".git")):
            self.repo = git.Repo.init(self.workspace_dir)
            gitignore_path = os.path.join(self.workspace_dir, ".gitignore")
            with open(gitignore_path, "w", encoding="utf-8") as f:
                f.write("__pycache__/\n*.pyc\n.env\n")
            self.repo.index.add([".gitignore"])
            self.repo.index.commit("Initial commit")
            print("??? Git repository initialized")
        else:
            self.repo = git.Repo(self.workspace_dir)
    
    def _save_state(self, last_completed_task_index=-1):
        """Save state with atomic write"""
        state = {
            "last_completed_task_index": last_completed_task_index,
            "plan": self.plan,
            "sadt_plan": self.sadt_plan,
            "planner_source": self.planner_source,
            "files": self.files,
            "run_command": self.run_command,
            "technical_architecture": self.technical_architecture,
            "cost_tracker_state": self.cost_tracker.to_dict(),
            "metrics_tracker_state": self.metrics_tracker.to_dict(),
            "schema_version": 1
        }
        
        # Atomic write
        temp_file = self.state_file + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(temp_file, self.state_file)
    
    def _load_state(self):
        """Load state from disk"""
        if not os.path.exists(self.state_file):
            return
        
        with open(self.state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        
        self.last_completed_task_index = state.get("last_completed_task_index", -1)
        self.plan = state.get("plan", [])
        self.sadt_plan = state.get("sadt_plan")
        self.planner_source = state.get("planner_source")
        self.files = state.get("files", {})
        self.run_command = state.get("run_command", "")
        self.technical_architecture = state.get("technical_architecture")

    def _has_valid_saved_state(self) -> bool:
        """Validate if saved state is sufficient to resume without re-planning."""
        if not isinstance(self.plan, list) or len(self.plan) == 0:
            return False
        if not isinstance(self.technical_architecture, dict) or not self.technical_architecture:
            return False

        file_structure = self.technical_architecture.get("file_structure")
        if file_structure is None:
            return False
        if not isinstance(file_structure, list) or len(file_structure) == 0:
            return False

        if self.last_completed_task_index >= len(self.plan):
            return False

        return True

    def _estimate_review_complexity(self, git_diff: str, files_modified: List[str]) -> str:
        """Heuristic complexity for review timeout selection."""
        unique_files = {f for f in (files_modified or []) if f}
        file_count = len(unique_files)
        diff_lines = git_diff.count("\n") if git_diff else 0

        if file_count >= 5 or diff_lines >= 300:
            return "complex"
        if file_count >= 2 or diff_lines >= 100:
            return "medium"
        return "simple"

    def _get_review_timeout(self, git_diff: str, files_modified: List[str]) -> int:
        complexity = self._estimate_review_complexity(git_diff, files_modified)
        return REVIEW_TIMEOUT_CONFIG.get(complexity, REVIEW_TIMEOUT_CONFIG["simple"])

    def _python_file_has_syntax_error(self, filepath: str) -> bool:
        """Return True if Python file has a syntax error; False otherwise."""
        full_path = os.path.join(self.project_dir, filepath)
        if not os.path.exists(full_path):
            return False
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                compile(f.read(), filepath, "exec")
            return False
        except SyntaxError:
            return True
        except Exception:
            # Only treat syntax errors as validated issues
            return False

    def _validate_review_findings(self, issues: List[Dict], files_modified: List[str]) -> List[Dict]:
        """Validate reviewer findings to reduce false positives."""
        validated = []
        for issue in issues or []:
            issue_type = str(issue.get("type", "")).lower()
            issue_file = issue.get("file", "")

            if issue_file.endswith(".py") and issue_type == "syntax_error":
                if not self._python_file_has_syntax_error(issue_file):
                    print(f"?????? Reviewer flagged false positive syntax error: {issue.get('description', '')}")
                    if self.logger:
                        self.logger.log("WARNING", f"Reviewer false positive (syntax): {issue_file}")
                    continue

            validated.append(issue)

        return validated
    
    def _save_checkpoint(self, checkpoint: TaskCheckpoint):
        """Save checkpoint with proper serialization"""
        self.task_checkpoints[checkpoint.task_index] = checkpoint
        
        checkpoints_data = {}
        
        for idx, cp in self.task_checkpoints.items():
            try:
                cp_dict = {
                    'task_index': cp.task_index,
                    'task_description': cp.task_description,
                    'status': cp.status,
                    'timestamp': cp.timestamp,
                    'development_output': cp.development_output,
                    'review_feedback': self._make_serializable(cp.review_feedback),
                    'test_results': cp.test_results,
                    'architecture_validation': self._make_serializable(cp.architecture_validation),
                    'retry_count': cp.retry_count,
                    'retry_history': self._make_serializable(cp.retry_history),
                    'files_modified': cp.files_modified,
                    'files_created': cp.files_created,
                    'files_deleted': cp.files_deleted,
                    'depends_on': cp.depends_on,
                    'blocked_by': cp.blocked_by,
                    'git_commit_sha': cp.git_commit_sha,
                    'git_stash_ref': cp.git_stash_ref,
                    'agent_interactions': self._make_serializable(cp.agent_interactions),
                }
                
                checkpoints_data[str(idx)] = cp_dict
            
            except Exception as e:
                print(f"?????? Error serializing checkpoint {idx}: {e}")
                self.logger.log("WARNING", f"Failed to serialize checkpoint {idx}: {e}")
                continue
        
        temp_file = self.checkpoint_file + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(checkpoints_data, f, indent=2, ensure_ascii=False)
            
            os.replace(temp_file, self.checkpoint_file)
            self.logger.log("INFO", f"Checkpoint saved for task {checkpoint.task_index}: {checkpoint.status}")
        
        except Exception as e:
            print(f"?????? Error writing checkpoint file: {e}")
            self.logger.log("ERROR", f"Failed to write checkpoint file: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
    
    def _load_checkpoints(self):
        """Load checkpoints with error recovery"""
        if not os.path.exists(self.checkpoint_file):
            return
        
        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                checkpoints_data = json.load(f)
            
            loaded_count = 0
            for idx_str, cp_dict in checkpoints_data.items():
                try:
                    idx = int(idx_str)
                    
                    checkpoint = TaskCheckpoint(
                        task_index=cp_dict.get('task_index', idx),
                        task_description=cp_dict.get('task_description', ''),
                        status=cp_dict.get('status', 'pending'),
                        timestamp=cp_dict.get('timestamp', datetime.now().isoformat()),
                        development_output=cp_dict.get('development_output'),
                        review_feedback=cp_dict.get('review_feedback', []),
                        test_results=cp_dict.get('test_results'),
                        architecture_validation=cp_dict.get('architecture_validation'),
                        retry_count=cp_dict.get('retry_count', 0),
                        retry_history=cp_dict.get('retry_history', []),
                        files_modified=cp_dict.get('files_modified', []),
                        files_created=cp_dict.get('files_created', []),
                        files_deleted=cp_dict.get('files_deleted', []),
                        depends_on=cp_dict.get('depends_on', []),
                        blocked_by=cp_dict.get('blocked_by', []),
                        git_commit_sha=cp_dict.get('git_commit_sha'),
                        git_stash_ref=cp_dict.get('git_stash_ref'),
                        agent_interactions=cp_dict.get('agent_interactions', []),
                    )
                    
                    self.task_checkpoints[idx] = checkpoint
                    loaded_count += 1
                
                except Exception as e:
                    print(f"?????? Failed to load checkpoint {idx_str}: {e}")
                    continue
            
            self.logger.log("INFO", f"Loaded {loaded_count} task checkpoints")
        
        except Exception as e:
            print(f"?????? Error loading checkpoints file: {e}")
            self.logger.log("WARNING", f"Failed to load checkpoints: {e}")
    
    # ==================== GIT ROLLBACK ====================
    
    def _create_task_savepoint(self, task_index: int) -> Optional[str]:
        """
        Create a git stash before starting a task for rollback capability.
        
        Args:
            task_index: Index of the task
        
        Returns:
            Stash reference string or None
        """
        if not self.repo:
            return None
        
        try:
            # Check if there are changes to stash
            if self.repo.is_dirty(untracked_files=True):
                stash_msg = f"savepoint_task_{task_index}"
                self.repo.git.stash('save', '-u', stash_msg)
                print(f"??? Created savepoint: {stash_msg}")
                return stash_msg
            else:
                print(f"??? No changes to savepoint for task {task_index}")
                return None
        except Exception as e:
            print(f"?????? Failed to create savepoint: {e}")
            return None
    
    def _rollback_to_savepoint(self, stash_ref: str) -> bool:
        """
        Rollback to a git stash.
        
        Args:
            stash_ref: Stash reference to rollback to
        
        Returns:
            True if successful, False otherwise
        """
        if not self.repo or not stash_ref:
            return False
        
        try:
            # Find the stash
            stashes = self.repo.git.stash('list').split('\n')
            stash_index = None
            
            for i, stash in enumerate(stashes):
                if stash_ref in stash:
                    stash_index = i
                    break
            
            if stash_index is not None:
                # Apply the stash
                try:
                    self.repo.git.stash('apply', f'stash@{{{stash_index}}}')
                except git.exc.GitCommandError as e:
                    print(f"?????? Rollback encountered conflict: {e}")
                    # Auto-resolve by taking stash version ("theirs")
                    try:
                        conflicted = self.repo.git.diff('--name-only', '--diff-filter=U').splitlines()
                        for path in conflicted:
                            if not path.strip():
                                continue
                            self.repo.git.checkout('--theirs', '--', path)
                            self.repo.git.add(path)
                        print(f"??? Auto-resolved {len(conflicted)} conflicted files using stash version.")
                    except Exception as resolve_err:
                        print(f"??? Auto-resolve failed: {resolve_err}")
                        traceback.print_exc()
                        return False
                # Drop the stash
                self.repo.git.stash('drop', f'stash@{{{stash_index}}}')
                print(f"??? Rolled back to savepoint: {stash_ref}")
                
                # Reload files from disk
                self._build_index_from_disk()
                return True
            else:
                print(f"?????? Savepoint not found: {stash_ref}")
                return False
        
        except Exception as e:
            print(f"??? Rollback failed: {e}")
            traceback.print_exc()
            return False
        

    def _make_serializable(self, obj):
        """
        Recursively convert non-serializable objects to JSON-serializable format.
        
        Handles:
        - AttributedDict (from LlamaIndex)
        - Custom objects
        - Dataclasses
        - Tuples (converts to lists)
        - Any dict-like objects
        
        Args:
            obj: Object to convert
        
        Returns:
            JSON-serializable version of the object
        """
        # Handle None
        if obj is None:
            return None
        
        # Handle primitives (already serializable)
        if isinstance(obj, (str, int, float, bool)):
            return obj
        
        # Handle lists
        if isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        
        # Handle tuples (convert to list for JSON)
        if isinstance(obj, tuple):
            return [self._make_serializable(item) for item in obj]
        
        # Handle dicts and dict-like objects (including AttributedDict)
        if isinstance(obj, dict) or hasattr(obj, 'items'):
            result = {}
            try:
                # Get items (works for dict and AttributedDict)
                if hasattr(obj, 'items'):
                    items = obj.items()
                else:
                    items = []
                
                for key, value in items:
                    # Ensure key is string
                    str_key = str(key) if not isinstance(key, str) else key
                    # Recursively convert value
                    result[str_key] = self._make_serializable(value)
                
                return result
            
            except Exception as e:
                # If items() fails, try converting to dict
                try:
                    return self._make_serializable(dict(obj))
                except:
                    # Last resort: string representation
                    print(f"?????? Could not serialize object of type {type(obj)}: {e}")
                    return str(obj)
        
        # Handle dataclasses (but avoid recursion with AttributedDict)
        if hasattr(obj, '__dataclass_fields__'):
            try:
                # First convert to dict with asdict
                obj_dict = {}
                for field_name in obj.__dataclass_fields__:
                    field_value = getattr(obj, field_name)
                    obj_dict[field_name] = self._make_serializable(field_value)
                return obj_dict
            except:
                pass
        
        # Handle objects with __dict__ attribute
        if hasattr(obj, '__dict__'):
            try:
                return self._make_serializable(obj.__dict__)
            except:
                pass
        
        # Fallback: convert to string
        try:
            return str(obj)
        except:
            return "<unserializable object>"
    
    # ==================== GIT OPERATIONS ====================
    
    def _git_commit(self, message: str):
        """Create a git commit"""
        try:
            if self.repo.is_dirty(untracked_files=True):
                self.repo.git.add(A=True)
                commit = self.repo.index.commit(message)
                print(f"??? Git commit created: '{message}' ({commit.hexsha[:7]})")
                return commit.hexsha
        except Exception as e:
            print(f"?????? Git commit failed: {e}")
            self.logger.log("ERROR", f"Git commit failed: {e}")
            return None
    
    def _get_project_diff(self) -> str:
        """Get git diff of all changes"""
        if not self.repo:
            return "Git repository not initialized."
        
        self.repo.git.add(A=True)
        return self.repo.git.diff('HEAD')
    
    def _get_available_files(self):
        if not os.path.exists(self.project_dir):
            return
        
        for root, _, files in os.walk(self.project_dir):
            for file in files:
                filepath = os.path.join(root, file)
                try:
                    rel_path = os.path.relpath(filepath, self.project_dir)
                    self.files[rel_path] = file
                except Exception as e:
                    self.logger.log("WARNING", f"Could not read {filepath}: {e}")
    
    # ==================== RAG INDEX ====================
    
    def _build_index_from_disk(self):
        """Build RAG index from existing files"""
        if not getattr(self, "embeddings_enabled", True):
            self.code_index = None
            self._get_available_files()
            return
        if not os.path.exists(self.project_dir):
            return
        
        documents = []
        for root, _, files in os.walk(self.project_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        rel_path = os.path.relpath(filepath, self.project_dir)
                        self.files[rel_path] = content
                        
                        doc = Document(
                            text=content,
                            metadata={'file_name': rel_path}
                        )
                        documents.append(doc)
                    except Exception as e:
                        self.logger.log("WARNING", f"Could not read {filepath}: {e}")
        
        if documents:
            self.code_index = VectorStoreIndex.from_documents(documents)
            self.logger.log("INFO", f"Built RAG index from {len(documents)} files")
    
    def _update_index_incrementally(self, changed_files: Optional[List[str]] = None):
        """Update RAG index with current files"""
        if not getattr(self, "embeddings_enabled", True):
            self.code_index = None
            return
        if not changed_files:
            return

        if not any(name.endswith('.py') for name in changed_files):
            return

        if not self.files:
            self._build_index_from_disk()
            return
        
        documents = []
        for filename, content in self.files.items():
            if filename.endswith('.py'):
                doc = Document(
                    text=content,
                    metadata={'file_name': filename}
                )
                documents.append(doc)
        
        if documents:
            self.code_index = VectorStoreIndex.from_documents(documents)
    
    def _get_rag_context(self, query: str) -> str:
        """Retrieve relevant code context using RAG"""
        if not getattr(self, "embeddings_enabled", True):
            return (
                "Vector retrieval is disabled. Use list_files, read_file, "
                "and get_code_summary for code context."
            )
        if self.code_index:
            retriever = self.code_index.as_retriever(similarity_top_k=3)
            relevant_nodes = retriever.retrieve(query)
            
            if not relevant_nodes:
                return "No relevant code snippets found."
            
            context_str = "Relevant code context:\n\n"
            for node in relevant_nodes:
                filename = node.metadata.get('file_name', 'unknown_file')
                context_str += f"--- {filename} ---\n"
                context_str += node.get_content() + "\n---\n"
            return context_str
        return "No code exists yet."
    
    # ==================== HELPER METHODS ====================
    def extract_filenames_from_task(self, task: str) -> List[str]:
        """Extract expected filenames from task description"""
        # Extract any file-like tokens from both instruction and output clauses.
        patterns = [
            r'([A-Za-z0-9_./-]+\.(?:py|tsx|ts|jsx|js|txt|yml|yaml|json|md|css|html))',
        ]

        files: List[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, task):
                candidate = match.strip(".,;:()[]{}'\"")
                if candidate:
                    files.append(candidate)

        return sorted(set(files))
    
    def _get_project_structure_string(self) -> str:
        """Generate string representation of project structure"""
        structure = []
        
        for root, dirs, files in os.walk(self.project_dir):
            dirs[:] = [d for d in dirs if d != '.git']
            
            level = root.replace(self.project_dir, '').count(os.sep)
            indent = ' ' * 2 * level
            structure.append(f'{indent}{os.path.basename(root)}/')
            
            subindent = ' ' * 2 * (level + 1)
            for file in sorted(files):
                structure.append(f'{subindent}{file}')
        
        return '\n'.join(structure)
    
    def _build_retry_context_from_conversations(
        self, 
        checkpoint: TaskCheckpoint, 
        task: str
    ) -> str:
        """
        Build retry context using agent conversation history.
        
        This leverages the conversation framework from base_agent.py
        to show the developer what happened in previous attempts.
        
        Args:
            checkpoint: Current task checkpoint
            task: Original task description
        
        Returns:
            Formatted context string with conversation history
        """
        if checkpoint.retry_count == 0:
            return ""  # First attempt, no history
        
        context_parts = []
        recent_error_types = [r.get('error_type', '') for r in checkpoint.retry_history[-3:]]
        repeated_no_tool_calls = recent_error_types.count('no_tool_calls') >= 2
        
        # Header
        context_parts.append(f"\n{'='*70}")
        context_parts.append(f"??????  RETRY ATTEMPT #{checkpoint.retry_count + 1}")
        context_parts.append(f"{'='*70}\n")
        
        # Show what went wrong in previous attempts
        if checkpoint.retry_history:
            context_parts.append("???? PREVIOUS ATTEMPTS:")
            for i, retry in enumerate(checkpoint.retry_history, 1):
                error_type = retry['error_type']
                error_msg = retry['error_message'][:150]
                context_parts.append(f"\n  Attempt {i} - Failed:")
                context_parts.append(f"    Error Type: {error_type}")
                context_parts.append(f"    Error: {error_msg}...")
        
        # Get conversation history between Developer and Reviewer
        dev_reviewer_conv = self.dev_agent._get_or_create_conversation("CodeReviewerAgent")
        
        if repeated_no_tool_calls:
            context_parts.append("\nRESET CONTEXT: Repeated no_tool_calls failures detected; ignore prior conversation patterns.")
        elif dev_reviewer_conv.history:
                context_parts.append(f"\n???? CONVERSATION HISTORY WITH REVIEWER:")
                conv_summary = dev_reviewer_conv.get_summary(max_chars=800)
                context_parts.append(f"    {conv_summary}")
        
        # Show specific review feedback
        if checkpoint.review_feedback:
            context_parts.append(f"\n???? DETAILED REVIEW FEEDBACK:")
            for i, issue in enumerate(checkpoint.review_feedback, 1):
                severity = issue.get('severity', 'unknown').upper()
                file_loc = f"{issue.get('file', '?')}:{issue.get('line', '?')}"
                desc = issue.get('description', 'No description')
                sugg = issue.get('suggestion', 'No suggestion provided')
                
                context_parts.append(f"\n  Issue {i} [{severity}] at {file_loc}:")
                context_parts.append(f"    Problem: {desc}")
                context_parts.append(f"    Fix Required: {sugg}")
        
        # Warning for stuck loops
        if checkpoint.retry_count >= 3:
            recent_errors = [r['error_type'] for r in checkpoint.retry_history[-3:]]
            if len(set(recent_errors)) == 1:
                context_parts.append(f"\n???? WARNING: You've made the same '{recent_errors[0]}' error 3 times!")
                context_parts.append(f"    TRY A COMPLETELY DIFFERENT APPROACH!")
                if recent_errors[0] == "no_tool_calls":
                    context_parts.append("    REQUIRED: Emit one valid tool call in strict Action/Action Input format before long reasoning.")
        
        if repeated_no_tool_calls:
            context_parts.append("\nSTRICT TOOL FORMAT (REQUIRED FOR NEXT ATTEMPT):")
            context_parts.append("  - Use exactly: Action: <tool_name>")
            context_parts.append('  - Use exactly: Action Input: {"filename":"...","content":"..."}')
            context_parts.append("  - DO NOT use inline syntax like Action: tool({...})")
            context_parts.append("  - DO NOT wrap inputs in kwargs/args containers unless the tool schema requires it")

        # Action items
        context_parts.append(f"\n{'='*70}")
        context_parts.append(f"??? ACTION REQUIRED:")
        context_parts.append(f"    1. Read ALL the feedback above carefully")
        context_parts.append(f"    2. Fix EACH issue mentioned")
        context_parts.append(f"    3. Verify your changes")
        context_parts.append(f"{'='*70}\n")
        
        return "\n".join(context_parts)

    def _collect_clarifications(self, questions: List[str]) -> str:
        """Prompt user for clarifying answers in the CLI."""
        if not questions:
            return ""

        print("\n???? Clarification needed before planning.")
        answers = []
        for i, q in enumerate(questions, 1):
            print(f"\nQuestion {i}: {q}")
            ans = input("Your answer (press Enter to accept default/skip): ").strip()
            if ans:
                answers.append(f"{i}. Q: {q}\n   A: {ans}")
            else:
                answers.append(f"{i}. Q: {q}\n   A: [default/assumed]")

        return "\n".join(answers)

    def _find_placeholders_in_files(self, file_list: List[str]) -> List[Dict]:
        """Scan modified files for placeholder content or TODOs."""
        if not file_list:
            return []

        patterns = [
            r'\bTODO\b',
            r'\bFIXME\b',
            r'\bplaceholder\b',
            r'NotImplementedError',
            r'\bpass\b\s*#',
        ]
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
        issues = []

        for rel_path in file_list:
            if not rel_path:
                continue
            full_path = os.path.join(self.project_dir, rel_path)
            if not os.path.exists(full_path):
                continue
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                for pattern in compiled:
                    if pattern.search(content):
                        issues.append({
                            "severity": "major",
                            "type": "incomplete_feature",
                            "file": rel_path,
                            "line": 0,
                            "description": "Placeholder or TODO text found in file. Production code must be complete.",
                            "suggestion": "Remove placeholders/TODOs and implement the missing logic."
                        })
                        break
            except Exception as e:
                self.logger.log("WARNING", f"Placeholder scan failed for {rel_path}: {e}")

        return issues
    
    # ==================== MAIN ORCHESTRATION LOOP ====================
    
    async def run(self):
        """
        Main orchestration loop with enhanced error handling and rollback
        """
        project_completed_successfully = False
        clarified_prompt = self.user_prompt
        
        try:
            clarified_prompt = execute_planning_stage(self._make_stage_context())

            # Ensure execution agents are initialized with execution model
            if not self.dev_agent or not self.reviewer_agent:
                self._init_execution_agents()
                if self.execution_model:
                    print(f"??? Execution model: {self.execution_model}")
                
                # Save initial state
                self._save_state(self.last_completed_task_index)

            if not self.progress_tracker:
                self.progress_tracker = ProgressTracker(len(self.plan))
            # Align progress counters when resuming.
            if self.is_resuming and self.task_checkpoints:
                completed_count = sum(
                    1 for cp in self.task_checkpoints.values()
                    if cp.status == TaskStatus.COMPLETED.value
                )
                self.progress_tracker.completed_tasks = completed_count
                self.progress_tracker.processed_tasks = min(
                    len(self.plan),
                    max(0, self.last_completed_task_index + 1)
                )
            
            # --- Phase 4: Development Loop ---
            self.logger.log_phase("Development")
            print("\n=== ???? Phase 4: Development ===")
            
            current_task_index = self.last_completed_task_index + 1
            
            while current_task_index < len(self.plan):
                task = self.plan[current_task_index]
                if current_task_index not in self.task_escalation_states:
                    self.task_escalation_states[current_task_index] = self.task_escalation_policy.new_task_state()
                
                # Start progress tracking
                self.progress_tracker.start_task(current_task_index, task)
                
                # Get or create checkpoint
                if current_task_index in self.task_checkpoints:
                    checkpoint = self.task_checkpoints[current_task_index]
                else:
                    checkpoint = TaskCheckpoint(
                        task_index=current_task_index,
                        task_description=task,
                        status=TaskStatus.PENDING.value,
                        timestamp=datetime.now().isoformat()
                    )
                    self._save_checkpoint(checkpoint)
                
                print(f"\n{'='*60}")
                print(f"Task {current_task_index + 1}/{len(self.plan)}")
                print(f"Description: {task}")
                print(f"Status: {checkpoint.status}")
                print(f"Retry count: {checkpoint.retry_count}")
                print(f"{'='*60}\n")
                
                # Check retry limit
                if checkpoint.retry_count >= self.max_retry_attempts:
                    print(f"??? Task failed after {checkpoint.retry_count} attempts, skipping...")
                    checkpoint.status = TaskStatus.FAILED.value
                    self._save_checkpoint(checkpoint)
                    self.progress_tracker.complete_task(success=False)
                    self.task_escalation_states.pop(current_task_index, None)
                    self._ensure_execution_model(self.default_execution_model)
                    current_task_index += 1
                    continue
                
                # Create savepoint before task execution
                savepoint = self._create_task_savepoint(current_task_index)
                if savepoint:
                    checkpoint.git_stash_ref = savepoint
                    self._save_checkpoint(checkpoint)
                
                try:
                    stage_ctx = self._make_stage_context(
                        task=task,
                        checkpoint=checkpoint,
                        current_task_index=current_task_index,
                        savepoint=savepoint,
                    )
                    # --- Development Phase ---
                    self._ensure_execution_model(self._resolve_task_model(current_task_index))
                    dev_stage_result = await execute_development_stage(stage_ctx)
                    if dev_stage_result.should_retry:
                        self._observe_task_retry_and_maybe_escalate(
                            current_task_index,
                            checkpoint,
                            "DeveloperAgent",
                        )
                        continue

                    # --- Review Phase ---
                    self._ensure_execution_model(self._resolve_task_model(current_task_index))
                    review_stage_result = await execute_review_stage(stage_ctx)
                    issue_summary = review_stage_result.issue_summary
                    task = review_stage_result.updated_task
                    if review_stage_result.should_retry:
                        self._observe_task_retry_and_maybe_escalate(
                            current_task_index,
                            checkpoint,
                            "CodeReviewerAgent",
                        )
                        continue

                    # --- Testing Phase (if enabled) ---
                    stage_ctx = self._make_stage_context(
                        task=task,
                        checkpoint=checkpoint,
                        current_task_index=current_task_index,
                        savepoint=savepoint,
                    )
                    testing_stage_result = execute_testing_stage(stage_ctx)
                    if testing_stage_result.should_retry:
                        continue

                    # --- Task Completed Successfully ---
                    checkpoint.status = TaskStatus.COMPLETED.value
                    checkpoint.timestamp = datetime.now().isoformat()

                    if checkpoint.retry_count > 0:  # Only print if there were retries
                        print(f"???? Clearing conversation history ({checkpoint.retry_count} retries)")
                        dev_stats = self.dev_agent.get_stats()
                        print(f"   Developer: {dev_stats['active_conversations']} conversations, {dev_stats['call_count']} total calls")

                    # Clear conversations for next task
                    self.dev_agent.clear_conversation("CodeReviewerAgent")
                    self.dev_agent.clear_conversation("orchestrator")
                    self.reviewer_agent.clear_conversation("DeveloperAgent")
                                        
                    # Commit changes
                    commit_sha = self._git_commit(f"Complete task {current_task_index + 1}: {task}")
                    if commit_sha:
                        checkpoint.git_commit_sha = commit_sha
                    
                    self._save_checkpoint(checkpoint)

                    try:
                        task_summary = (
                            f"Completed task {current_task_index + 1}: {task}. "
                            f"Files modified: {', '.join(checkpoint.files_modified[:10])}. "
                            f"Review summary: {issue_summary}"
                        )
                        self._remember_memory(
                            content=self._truncate_text(task_summary, 1200),
                            agent_name="DeveloperAgent",
                            memory_type="event",
                            tags=["task_complete", f"project:{self.project_name}"],
                            importance=0.6,
                        )
                    except Exception:
                        pass

                    self.logger.log("INFO", f"Task {current_task_index + 1} completed successfully")
                    self.metrics_tracker.complete_task(task, success=True, review_passed_on_first_try=(checkpoint.retry_count == 0))
                    
                    # Update RAG index
                    self._update_index_incrementally(checkpoint.files_modified)
                    
                    # Update state
                    self.last_completed_task_index = current_task_index
                    self._save_state(self.last_completed_task_index)
                    
                    # Mark progress as complete
                    self.progress_tracker.complete_task(success=True)
                    self.task_escalation_states.pop(current_task_index, None)
                    self._ensure_execution_model(self.default_execution_model)
                    
                    current_task_index += 1
                
                except Exception as e:
                    print(f"\n??? Task failed with error: {e}")
                    traceback.print_exc()
                    
                    # Rollback if savepoint exists
                    if savepoint:
                        print("?????? Rolling back changes...")
                        self._rollback_to_savepoint(savepoint)
                    
                    checkpoint.add_retry("exception", str(e))
                    self._remember_memory(
                        content=f"Task failed with exception for '{task}': {str(e)}",
                        agent_name="DeveloperAgent",
                        memory_type="event",
                        tags=["retry", "exception", f"project:{self.project_name}"],
                        importance=0.8,
                        store_global=True
                    )
                    checkpoint.status = TaskStatus.PENDING.value
                    self._save_checkpoint(checkpoint)
                    
                    self.progress_tracker.complete_task(success=False)
                    self._observe_task_retry_and_maybe_escalate(
                        current_task_index,
                        checkpoint,
                        "DeveloperAgent",
                    )
                    
                    # Don't increment - retry same task
            
            failed_or_blocked = [
                cp for cp in self.task_checkpoints.values()
                if cp.status in {
                    TaskStatus.FAILED.value,
                    TaskStatus.BLOCKED.value,
                    TaskStatus.SKIPPED.value,
                    TaskStatus.PENDING.value,
                    TaskStatus.IN_PROGRESS.value,
                }
            ]
            project_completed_successfully = (
                len(failed_or_blocked) == 0
                and self.last_completed_task_index >= len(self.plan) - 1
            )
            if project_completed_successfully:
                print("\n??? All tasks completed successfully!")
            else:
                print("\n?????? Development loop finished with failed/skipped tasks.")
        
        except Exception as e:
            self.logger.log("ERROR", f"Fatal error in orchestration: {e}")
            traceback.print_exc()
            print(f"\n??? Orchestration failed: {e}")
        
        finally:
            # --- Finalization Phase ---
            execute_finalization_stage(
                self._make_stage_context(),
                project_completed_successfully=project_completed_successfully,
                clarified_prompt=clarified_prompt,
            )

    def _create_simple_plan(self, architecture: Dict) -> List[str]:
        """
        Create a simple task plan from architecture.
        Fallback when SADT planner is not available.
        
        Args:
            architecture: Architecture dict from SoftwareArchitectAgent
        
        Returns:
            List of task strings
        """
        plan = []
        
        file_structure = architecture.get("file_structure", [])
        component_breakdown = architecture.get("component_breakdown", {})
        
        # Task 1: Setup project structure
        plan.append("Create project directory structure and configuration files")
        
        # Task 2-N: Create each file
        for filepath in file_structure:
            if filepath in component_breakdown:
                purpose = component_breakdown[filepath]
                plan.append(f"Create {filepath}: {purpose}")
            else:
                plan.append(f"Create {filepath}")
        
        # Final task: Integration
        plan.append("Integrate all components and verify application runs")
        
        return plan


# ==================== ENTRY POINT ====================

def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="AgentForge multi-agent coding orchestrator")
    parser.add_argument("project_name")
    parser.add_argument("--prompt", dest="initial_prompt_file")
    providers = parser.add_mutually_exclusive_group()
    providers.add_argument("--provider", choices=("openai", "openai-compatible", "ollama", "google"))
    providers.add_argument("--google", action="store_true", help="Legacy alias for --provider google")
    parser.add_argument("--new", action="store_true", dest="force_new")
    parser.add_argument("--with-tests", action="store_true", dest="run_tests")
    parser.add_argument("--planning-model")
    parser.add_argument("--execution-model")
    args = parser.parse_args(argv)
    provider = "google" if args.google else resolve_provider(args.provider)
    orchestrator = Orchestrator(
        args.project_name,
        args.initial_prompt_file,
        provider=provider,
        force_new=args.force_new,
        run_tests=args.run_tests,
        planning_model=args.planning_model,
        execution_model=args.execution_model,
    )
    asyncio.run(orchestrator.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
