"""
Enhanced CodeReviewerAgent with:
- Crystal-clear submit_review format with multiple examples
- Faster review process
- Better error messages
"""
import asyncio
import traceback
from typing import List, Dict, Optional, Tuple
from .base_agent import BaseAgent
from .prompt_router import detect_task_type
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent
from llama_index.core.workflow import Context, StopEvent
from llama_index.core.agent.workflow import AgentStream, ToolCallResult, AgentOutput
from skill_manager import inject_skills_into_system_message
from prompt_loader import load_versioned_prompt


class CircuitBreakerError(RuntimeError):
    """Raised when the reviewer gets stuck in a repeated tool-call loop."""
    pass


class CodeReviewerAgent(BaseAgent):
    def __init__(self, llm_class, llm_args, orchestrator_tools, logger, skill_manager=None):
        super().__init__(llm_class, llm_args, temperature=0.1, agent_name="CodeReviewerAgent")
        
        self.logger = logger
        self.review_timeout = 60
        self.streaming = True
        self.skill_manager = skill_manager
        self.last_tool_calls = []
        self.tool_call_counts = {}
        self.used_tools = set()

        read_only_tools = [
            FunctionTool.from_defaults(
                fn=self._wrap_tool(orchestrator_tools.read_file, "read_file"),
                name="read_file",
                description="Read a file's content."
            ),
            FunctionTool.from_defaults(
                fn=self._wrap_tool(orchestrator_tools.list_files, "list_files"),
                name="list_files",
                description="List all files in the project."
            ),
            FunctionTool.from_defaults(
                fn=self._wrap_tool(orchestrator_tools.get_code_summary, "get_code_summary"),
                name="get_code_summary",
                description="Get file structure (classes, functions)."
            ),
            FunctionTool.from_defaults(
                fn=self._wrap_tool(orchestrator_tools.directory_exists, "directory_exists"),
                name="directory_exists",
                description="Check if a directory exists in the project."
            ),
            FunctionTool.from_defaults(
                fn=self._wrap_tool(
                    lambda query, top_k=5, max_chars=2000: orchestrator_tools.recall_memory(
                        query=query,
                        agent_name="CodeReviewerAgent",
                        top_k=top_k,
                        max_chars=max_chars,
                    ),
                    "recall_memory",
                ),
                name="recall_memory",
                description="Read-only: recall relevant project and reviewer memory context."
            ),
            FunctionTool.from_defaults(
                fn=self._wrap_tool(orchestrator_tools.submit_review, "submit_review"),
                name="submit_review",
                description="**MANDATORY** - Submit your review. This is the ONLY way to complete a review."
            )
        ]
        
        self.system_message_template = load_versioned_prompt(
            "reviewer",
            "system_template",
            DEFAULT_REVIEWER_SYSTEM_TEMPLATE,
        )
        self.system_message = self.system_message_template.replace("__TIMEOUT__", str(self.review_timeout))
        
        self.agent = ReActAgent(
            llm=self.llm,
            tools=read_only_tools,
            system_prompt=self.system_message,
            verbose=True,
            max_iterations=10,
            streaming=self.streaming
        )
    
    async def review_code(
        self, 
        task: str, 
        project_structure: str, 
        git_diff: str, 
        previous_issues: Optional[List[Dict]] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """Trigger code review with strict timeout"""
        # Reset circuit breaker history and tool usage for each review run
        self.last_tool_calls = []
        self.tool_call_counts = {}
        self.used_tools = set()
        
        prompt = f"""**QUICK REVIEW NEEDED**

Task: {task}

Files:
{project_structure}

Changes:
```diff
{git_diff[:500]}...
```

**YOU HAVE {self.review_timeout} SECONDS TO:**
1. Quick check (list_files, read 1-2 files max)
2. CALL submit_review with findings

**REMEMBER THE FORMAT:**
Action: submit_review
Action Input: {{"report": {{"issues": [...]}}}}

**START NOW. CALL submit_review WITHIN {self.review_timeout} SECONDS.**
Include a confidence score (0.0-1.0) in the report if possible.
"""
        task_type = detect_task_type(task, default="review")
        task_type_guidance = load_versioned_prompt(
            "reviewer",
            f"task_types/{task_type}",
            default_text="",
        )
        
        if self.logger:
            self.logger.log("INFO", f"Starting code review (timeout: {self.review_timeout}s)")
        
        self.system_message = self.system_message_template.replace("__TIMEOUT__", str(self.review_timeout))
        if task_type_guidance:
            self.system_message = f"{self.system_message}\n\n{task_type_guidance}"
        self.agent.system_prompt = self.system_message
        if self.skill_manager:
            improved_system_message = inject_skills_into_system_message(self.system_message, task, self.skill_manager, token_budget=32000)
            self.agent.system_prompt = improved_system_message
            
        tool_usage_history = []
        final_issues = None
        submit_review_called = False
        
        ctx = Context(self.agent)
        handler = self.agent.run(prompt, ctx=ctx)
        
        try:
            async def collect_events():
                nonlocal final_issues, submit_review_called
                
                async for ev in handler.stream_events():
                    if isinstance(ev, ToolCallResult):
                        tool_usage_history.append({
                            "tool_name": ev.tool_name,
                            "arguments": ev.tool_kwargs,
                            "result": str(ev.tool_output)[:500]
                        })
                        
                        print(f"\n[Reviewer] 🔧 {ev.tool_name}({ev.tool_kwargs})")
                        
                        if ev.tool_name == 'submit_review':
                            submit_review_called = True
                            report = ev.tool_kwargs.get('report', {})
                            
                            if isinstance(report, dict):
                                final_issues = report.get('issues', [])
                            else:
                                final_issues = []
                            
                            if self.logger:
                                self.logger.log("INFO", f"submit_review called with {len(final_issues)} issues")
                            
                            print(f"\n[Reviewer] ✅ Review submitted: {len(final_issues)} issues found")
                    
                    elif isinstance(ev, StopEvent):
                        print("\n[Reviewer] 🛑 Agent stopped")
                        break
                    
                    elif isinstance(ev, AgentOutput):
                        final_answer = str(ev.response)
                        if self.logger:
                            self.logger.log_event_in_step("llm_response", {"response": final_answer})
                    
                    elif isinstance(ev, AgentStream):
                        print(f"{ev.delta}", end="", flush=True)
            
            await asyncio.wait_for(collect_events(), timeout=self.review_timeout)
            
        except asyncio.TimeoutError:
            print(f"\n⚠️  Review TIMEOUT after {self.review_timeout}s")
            
            if not submit_review_called:
                print("❌ CRITICAL: submit_review was NOT called within timeout")
                print("❌ Reviewer failed to complete task")
                
                final_issues = [{
                    "severity": "critical",
                    "type": "integration_issue",
                    "file": "N/A",
                    "line": 0,
                    "description": "Code review agent failed to call submit_review within timeout. Manual review required.",
                    "suggestion": "Review code manually or retry review"
                }]
            try:
                handler.cancel()
            except Exception:
                pass
        
        except CircuitBreakerError as e:
            print(f"\nCircuit breaker tripped: {e}")
            if not submit_review_called:
                final_issues = [{
                    "severity": "major",
                    "type": "integration_issue",
                    "file": "N/A",
                    "line": 0,
                    "description": str(e),
                    "suggestion": "Re-run review or submit review with findings gathered so far"
                }]
            try:
                handler.cancel()
            except Exception:
                pass

        except Exception as e:
            print(f"\n❌ Error during review: {type(e).__name__}: {e}")
            traceback.print_exc()
            
            if not submit_review_called:
                final_issues = self._create_error_issue(str(e))
            try:
                handler.cancel()
            except Exception:
                pass
        
        # Validate final result
        if final_issues is None:
            if not submit_review_called:
                print("❌ No submit_review call detected; review is invalid.")
                final_issues = [{
                    "severity": "critical",
                    "type": "integration_issue",
                    "file": "N/A",
                    "line": 0,
                    "description": "Reviewer stopped without calling submit_review. Review is invalid.",
                    "suggestion": "Retry review and ensure submit_review is called exactly once."
                }]
            else:
                print("⚠️  No issues extracted, assuming clean code")
                final_issues = []
        
        if not isinstance(final_issues, list):
            print(f"⚠️  final_issues not a list (type: {type(final_issues)}), wrapping")
            final_issues = [final_issues] if final_issues else []
        
        # Validate issue structure
        final_issues = self._validate_issues(final_issues)
        
        return final_issues, tool_usage_history
    
    def _create_error_issue(self, error_msg: str) -> List[Dict]:
        """Create error issue when review fails"""
        return [{
            "severity": "critical",
            "type": "integration_issue",
            "file": "N/A",
            "line": 0,
            "description": f"Code review failed: {error_msg}",
            "suggestion": "Manual review required"
        }]
    
    def _validate_issues(self, issues: List[Dict]) -> List[Dict]:
        """Validate and clean issue structure"""
        
        required_fields = ["severity", "type", "file", "line", "description", "suggestion"]
        valid_severities = ["critical", "major", "minor", "suggestion"]
        valid_types = ["typo", "style_violation", "import_error", "naming_convention",
                       "missing_feature", "incomplete_feature", "logic_bug", "integration_issue",
                       "syntax_error"]
        
        validated = []
        
        for i, issue in enumerate(issues):
            if not isinstance(issue, dict):
                continue
            
            # Fill missing fields
            for field in required_fields:
                if field not in issue:
                    if field == "severity":
                        issue[field] = "minor"
                    elif field == "type":
                        issue[field] = "logic_bug"
                    elif field == "file":
                        issue[field] = "unknown"
                    elif field == "line":
                        issue[field] = 0
                    elif field == "description":
                        issue[field] = "No description"
                    elif field == "suggestion":
                        issue[field] = "No suggestion"
            
            # Validate severity
            if issue["severity"] not in valid_severities:
                issue["severity"] = "minor"
            
            # Validate type
            if issue["type"] not in valid_types:
                issue["type"] = "logic_bug"
            
            # Ensure line is integer
            try:
                issue["line"] = int(issue["line"])
            except (ValueError, TypeError):
                issue["line"] = 0
            
            validated.append(issue)
        
        return validated

    def _wrap_tool(self, tool_fn, tool_name: str):
        """Wrap tool calls to detect repeated tool-call loops."""
        def wrapper(*args, **kwargs):
            args, kwargs = self._normalize_tool_invocation(tool_name, args, kwargs)
            call_signature = f"{tool_name}({repr(kwargs) if kwargs else repr(args)})"
            self.last_tool_calls.append(call_signature)
            if len(self.last_tool_calls) > 3:
                self.last_tool_calls.pop(0)

            if len(self.last_tool_calls) == 3 and len(set(self.last_tool_calls)) == 1:
                raise CircuitBreakerError(
                    f"Tool call loop detected: {call_signature} called 3 times in a row. "
                    "Submit your review now with what you've found so far."
                )

            self.tool_call_counts[tool_name] = self.tool_call_counts.get(tool_name, 0) + 1
            self.used_tools.add(tool_name)

            if tool_name == "submit_review":
                # Inject confidence into the review report if missing
                report = kwargs.get("report")
                if isinstance(report, dict) and "confidence" not in report:
                    report["confidence"] = self._compute_confidence()
                    kwargs["report"] = report
                elif hasattr(report, "confidence") and report.confidence is None:
                    try:
                        report.confidence = self._compute_confidence()
                    except Exception:
                        pass

            return tool_fn(*args, **kwargs)
        return wrapper

    def _normalize_tool_invocation(self, tool_name: str, args, kwargs):
        """Normalize common malformed tool payloads emitted by model tool-calling."""
        normalized_args = list(args or [])
        normalized_kwargs = dict(kwargs or {})

        if not normalized_kwargs and len(normalized_args) == 1 and isinstance(normalized_args[0], dict):
            normalized_kwargs = dict(normalized_args[0])
            normalized_args = []

        nested_kwargs = normalized_kwargs.get("kwargs")
        if isinstance(nested_kwargs, dict):
            normalized_kwargs = {
                **nested_kwargs,
                **{k: v for k, v in normalized_kwargs.items() if k != "kwargs"},
            }

        wrapped_args = normalized_kwargs.pop("args", None)
        key_by_tool = {
            "read_file": "filename",
            "get_code_summary": "filename",
            "directory_exists": "dirname",
        }
        target_key = key_by_tool.get(tool_name)
        if target_key and target_key not in normalized_kwargs:
            if isinstance(wrapped_args, str):
                normalized_kwargs[target_key] = wrapped_args
            elif isinstance(wrapped_args, (list, tuple)) and wrapped_args:
                normalized_kwargs[target_key] = wrapped_args[0]
            elif normalized_args:
                normalized_kwargs[target_key] = normalized_args[0]
                normalized_args = normalized_args[1:]

        if tool_name == "submit_review" and "report" not in normalized_kwargs:
            if "issues" in normalized_kwargs:
                normalized_kwargs["report"] = {
                    "issues": normalized_kwargs.get("issues", []),
                    "confidence": normalized_kwargs.get("confidence"),
                }
            elif "summary" in normalized_kwargs:
                normalized_kwargs["report"] = {
                    "issues": [],
                    "confidence": normalized_kwargs.get("confidence"),
                }

        return tuple(normalized_args), normalized_kwargs

    def _compute_confidence(self) -> float:
        """Compute a lightweight confidence score based on tool usage."""
        score = 0.2
        if "list_files" in self.used_tools:
            score += 0.2
        if "read_file" in self.used_tools:
            score += 0.3
        if "get_code_summary" in self.used_tools:
            score += 0.1
        if sum(self.tool_call_counts.values()) >= 2:
            score += 0.1
        if sum(self.tool_call_counts.values()) >= 4:
            score += 0.1
        if score > 0.95:
            score = 0.95
        return round(score, 2)
    
    async def chat(self, message: str) -> str:
        """Handle consultation from other agents"""
        chat_system_message = """You are a code reviewer being consulted.
        Answer quickly and directly. Do NOT call submit_review in chat mode."""
        
        chat_agent = ReActAgent(
            llm=self.llm,
            tools=self.agent.tools,
            system_prompt=chat_system_message,
            verbose=False,
            streaming=True
        )
        
        ctx = Context(chat_agent)
        handler = chat_agent.run(message, ctx=ctx)
        
        final_answer_str = ""
        
        try:
            async for ev in handler.stream_events():
                if isinstance(ev, AgentOutput):
                    final_answer_str = str(ev.response)
            
            return final_answer_str
        
        except Exception as e:
            return f"Error: {str(e)}"


DEFAULT_REVIEWER_SYSTEM_TEMPLATE = """You are an expert code reviewer. Your job is to quickly review code and call submit_review.

TIME LIMIT: __TIMEOUT__ seconds.
Goal: find critical issues fast, then submit exactly one review report.

Required final call format:
Action: submit_review
Action Input: {"report": {"issues": [...], "confidence": 0.7}}

Use [] for issues if clean. Do not use alternate wrappers like {"issues": [...]}.
"""
