"""
Fixed DeveloperAgent with:
- Loop detection (stops trying same failed tool)
- Simpler prompts (gemma3:4b can't handle 200+ lines)
- Better error understanding
- Explicit fallback strategies
"""
import asyncio
import traceback
import time
import re
import os
from typing import List, Dict, Optional, Tuple
from collections import defaultdict, deque
from .base_agent import BaseAgent
from .llama_compat import (
    AgentOutput,
    AgentStream,
    Context,
    FunctionTool,
    ReActAgent,
    StopEvent,
    ToolCallResult,
)
from .prompt_router import detect_task_type
from aidev_orchestrator.skill_manager import inject_skills_into_system_message
from aidev_orchestrator.prompt_loader import load_versioned_prompt


class DeveloperAgent(BaseAgent):
    def __init__(self, llm_class, llm_args, orchestrator_tools, logger, skill_manager=None):
        super().__init__(llm_class, llm_args, temperature=0.1, agent_name="DeveloperAgent")
        
        self.logger = logger
        self.streaming = True
        self.orchestrator_tools = orchestrator_tools
        self.skill_manager = skill_manager
        
        tools = [
            FunctionTool.from_defaults(
                fn=orchestrator_tools.add_code_block,
                name="add_code_block",
                description="Add a code block at a semantic location. Use AST for placement."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.write_file,
                name="write_file",
                description="Create a NEW file. ONLY for files that don't exist yet!"
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.delete_code_block,
                name="delete_code_block",
                description="Delete a code block by name."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.read_file,
                name="read_file",
                description="Read an existing file."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.insert_text,
                name="insert_text",
                description="Add text to an existing file."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.replace_text,
                name="replace_text",
                description="Replace text in an existing file."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.list_files,
                name="list_files",
                description="See all files in project."
            ),
            FunctionTool.from_defaults(
                fn=lambda query, top_k=5, max_chars=2000: orchestrator_tools.recall_memory(
                    query=query,
                    agent_name="DeveloperAgent",
                    top_k=top_k,
                    max_chars=max_chars,
                ),
                name="recall_memory",
                description="Read-only: recall relevant project and agent memory context."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.delete_file,
                name="delete_file",
                description="Delete a file (PERMANENT)."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.create_directory,
                name="create_directory",
                description="Create a new directory."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.directory_exists,
                name="directory_exists",
                description="Check if a directory is present."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.get_code_summary,
                name="get_code_summary",
                description="Get structure of a file (classes, functions)."
            ),
            FunctionTool.from_defaults(
                fn=orchestrator_tools.refactor_rename_symbol,
                name="refactor_rename_symbol",
                description="Safely rename a symbol using AST."
            ),
        ]
        
        self.available_tool_names = {tool.metadata.name for tool in tools}
        
        self.base_system_message = load_versioned_prompt(
            "developer",
            "base",
            DEFAULT_DEVELOPER_BASE_PROMPT,
        )
        self.enhanced_system_message = load_versioned_prompt(
            "developer",
            "enhanced",
            DEFAULT_DEVELOPER_ENHANCED_PROMPT,
        )
        self.system_message = self.base_system_message + "\n\n" + self.enhanced_system_message


        self.agent = ReActAgent(
            llm=self.llm,
            tools=tools,
            system_prompt=self.system_message,
            verbose=True,
            max_iterations=20,  # Reduced from 30
            streaming=self.streaming
        )

    @staticmethod
    def _stream_looks_like_inflight_tool_call(stream_buffer: str) -> bool:
        if not stream_buffer:
            return False
        lower = stream_buffer.lower()
        if "action:" not in lower or "action input:" not in lower:
            return False

        # If Action Input appears to contain an opening JSON payload without a closing brace yet,
        # treat it as in-flight and avoid premature no-tool circuit breaking.
        idx = lower.rfind("action input:")
        payload_tail = stream_buffer[idx:] if idx >= 0 else stream_buffer
        open_braces = payload_tail.count("{")
        close_braces = payload_tail.count("}")
        if open_braces > close_braces:
            return True
        # Even when braces are balanced, recent Action/Input text indicates active tool formatting.
        return True

    def _should_abort_for_no_tool_calls(
        self,
        *,
        elapsed: float,
        stream_event_count: int,
        tool_call_count: int,
        stream_buffer: str,
        timeout_seconds: int,
        max_stream_events: int,
        min_elapsed_for_event_guard: int,
    ) -> bool:
        if tool_call_count > 0:
            return False
        if elapsed > timeout_seconds:
            return True
        if max_stream_events <= 0:
            return False
        if elapsed <= min_elapsed_for_event_guard:
            return False
        if stream_event_count <= max_stream_events:
            return False
        if self._stream_looks_like_inflight_tool_call(stream_buffer):
            return False
        return True
    
    async def run(
        self,
        task: str,
        retry_context: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> Tuple[bool, Optional[str], List[Dict]]:
        """Execute development task with loop detection"""
        
        if self.logger:
            self.logger.log("INFO", f"DeveloperAgent starting: {task[:100]}")
        
        full_prompt = task
        task_type = detect_task_type(task, default="modify_file")
        task_type_guidance = load_versioned_prompt(
            "developer",
            f"task_types/{task_type}",
            default_text="",
        )
        routed_system_message = (
            self.base_system_message
            + "\n\n"
            + self.enhanced_system_message
            + (f"\n\n{task_type_guidance}" if task_type_guidance else "")
        )
        allow_skill_injection = True
        if system_prompt is not None:
            self.agent.system_prompt = system_prompt
            allow_skill_injection = False
        else:
            self.agent.system_prompt = routed_system_message

        if self.skill_manager and allow_skill_injection:
            improved_system_message = inject_skills_into_system_message(
                routed_system_message,
                task,
                self.skill_manager,
                token_budget=32000
            )
            self.agent.system_prompt = improved_system_message

        
        if retry_context:
            full_prompt = f"""PREVIOUS ATTEMPT HAD ISSUES:
{retry_context}

NOW TRY AGAIN:
{task}

Fix the issues mentioned above."""
        
        ctx = Context(self.agent)
        handler = self.agent.run(full_prompt, ctx=ctx)
        
        tool_calls = []
        final_answer_str = ""
        files_created = set()
        files_modified = set()
        run_start = time.monotonic()
        stream_event_count = 0

        # Loop detection
        tool_failure_counts = defaultdict(int)
        last_tool_name = None
        consecutive_same_tool = 0
        invalid_tool_calls = 0
        # Detect repeated text-mode pseudo tool calls (no real ToolCallResult events)
        recent_action_chunks = deque(maxlen=12)
        repeated_action_streak = 0
        action_signature_streak = 0
        last_action_signature = None
        stream_buffer = ""
        no_tool_call_timeout_seconds = int(os.getenv("DEV_NO_TOOL_CALL_TIMEOUT_SECONDS", "45"))
        no_tool_call_max_stream_events = int(os.getenv("DEV_NO_TOOL_CALL_MAX_STREAM_EVENTS", "0"))
        no_tool_call_event_guard_min_elapsed_seconds = int(
            os.getenv("DEV_NO_TOOL_CALL_EVENT_GUARD_MIN_ELAPSED_SECONDS", "8")
        )
        
        if self.streaming:
            try:
                async for ev in handler.stream_events():
                    if isinstance(ev, ToolCallResult):
                        tool_name = ev.tool_name
                        tool_kwargs = ev.tool_kwargs
                        tool_output = ev.tool_output
                        
                        # Validate tool exists
                        if tool_name not in self.available_tool_names:
                            print(f"\n??? ERROR: Tool '{tool_name}' DOES NOT EXIST!")
                            print(f"Available tools: {', '.join(sorted(self.available_tool_names))}")
                            print("This tool will not be executed. Try a different approach.")
                            tool_failure_counts[tool_name] += 1
                            invalid_tool_calls += 1
                            if invalid_tool_calls >= 3:
                                print("\n?????????? CIRCUIT BREAKER: Too many invalid tool calls")
                                return False, "Agent tried invalid tools repeatedly", tool_calls
                            continue
                        
                        # Loop detection
                        if tool_name == last_tool_name:
                            consecutive_same_tool += 1
                        else:
                            consecutive_same_tool = 1
                            last_tool_name = tool_name
                        
                        # Circuit breaker: If same tool fails 3 times in a row, stop
                        output_str = str(tool_output.content) if hasattr(tool_output, 'content') else str(tool_output)
                        is_error = ("error" in output_str.lower() or 
                                   "fail" in output_str.lower() or 
                                   "rejected" in output_str.lower() or
                                   "success" in output_str.lower() and "false" in output_str.lower())
                        
                        if is_error:
                            tool_failure_counts[tool_name] += 1
                            
                            if consecutive_same_tool >= 3:
                                print(f"\n???? CIRCUIT BREAKER: Same tool '{tool_name}' failed {consecutive_same_tool} times in a row")
                                print(f"Stopping to prevent infinite loop. Last error: {output_str[:200]}")
                                return False, f"Agent stuck in loop trying '{tool_name}' repeatedly", tool_calls
                        
                        print(f"\n[Developer] ???? {tool_name}({tool_kwargs})")
                        print(f"[Developer] ??? {output_str[:150]}...")
                        
                        # Track file operations
                        if tool_name == "write_file" and "success" in output_str.lower() and "true" in output_str.lower():
                            filename = tool_kwargs.get('filename', '')
                            if filename:
                                files_created.add(filename)
                        
                        elif tool_name in ["insert_text", "replace_text"]:
                            if "success" in output_str.lower() and "true" in output_str.lower():
                                filename = tool_kwargs.get('filename', '')
                                if filename:
                                    files_modified.add(filename)
                        
                        tool_calls.append({
                            "tool_name": tool_name,
                            "tool_args": tool_kwargs
                        })
                    
                    elif isinstance(ev, StopEvent):
                        print("\n[Developer] ???? Complete")
                        break
                    
                    elif isinstance(ev, AgentOutput):
                        final_answer_str = str(ev.response)
                    
                    elif isinstance(ev, AgentStream):
                        delta = str(ev.delta or "")
                        print(f"{delta}", end="", flush=True)
                        stream_event_count += 1
                        if delta:
                            stream_buffer += delta
                            if len(stream_buffer) > 12000:
                                stream_buffer = stream_buffer[-12000:]

                        # Heuristic: repeated "Action: ..." text without real tool calls indicates stuck formatting loop.
                        normalized = re.sub(r"\s+", " ", delta).strip().lower()
                        if normalized and ("action:" in normalized or "action input:" in normalized):
                            recent_action_chunks.append(normalized[:240])
                            if len(recent_action_chunks) >= 2 and recent_action_chunks[-1] == recent_action_chunks[-2]:
                                repeated_action_streak += 1
                            else:
                                repeated_action_streak = 0
                            if len(tool_calls) == 0 and repeated_action_streak >= 6:
                                print("\n???? CIRCUIT BREAKER: Repeated text-mode Action loop without real tool calls.")
                                return False, "Agent stuck repeating Action text without invoking tools", tool_calls

                        # Stronger loop detection: repeated Action + Action Input signature in streamed text
                        action_matches = re.findall(
                            r"Action:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\n|\r\n?)\s*Action Input:\s*(\{[\s\S]*?\})",
                            stream_buffer,
                            flags=re.IGNORECASE
                        )
                        if action_matches and len(tool_calls) == 0:
                            action_name, action_payload = action_matches[-1]
                            payload_norm = re.sub(r"\s+", " ", action_payload).strip().lower()[:500]
                            signature = f"{action_name.lower()}|{payload_norm}"
                            if signature == last_action_signature:
                                action_signature_streak += 1
                            else:
                                last_action_signature = signature
                                action_signature_streak = 1
                            if action_signature_streak >= 5:
                                print("\n[Developer] CIRCUIT BREAKER: Repeated Action signature without any tool execution.")
                                return False, "Agent repeating identical Action/Action Input without invoking tools", tool_calls

                        elapsed = time.monotonic() - run_start
                        if self._should_abort_for_no_tool_calls(
                            elapsed=elapsed,
                            stream_event_count=stream_event_count,
                            tool_call_count=len(tool_calls),
                            stream_buffer=stream_buffer,
                            timeout_seconds=no_tool_call_timeout_seconds,
                            max_stream_events=no_tool_call_max_stream_events,
                            min_elapsed_for_event_guard=no_tool_call_event_guard_min_elapsed_seconds,
                        ):
                            print("\n???? CIRCUIT BREAKER: No tool calls executed within safety window.")
                            return False, "No tool calls executed (timeout/iteration guard)", tool_calls
                
                print(f"\n[Developer] ??? Used {len(tool_calls)} tools")
                
                # Basic file verification
                if files_created:
                    print(f"[Developer] ???? Created: {', '.join(files_created)}")
                if files_modified:
                    print(f"[Developer] ???? Modified: {', '.join(files_modified)}")
            
            except asyncio.TimeoutError:
                print("\n??? Timeout")
                return False, None, tool_calls
            
            except Exception as e:
                print(f"\n??? Error: {type(e).__name__}: {e}")
                traceback.print_exc()
                return False, None, tool_calls
        
        if not self.streaming:
            # Non-streaming fallback path
            try:
                result = await handler
                if isinstance(result, AgentOutput):
                    final_answer_str = str(result.response)
                return True, final_answer_str, tool_calls
            except Exception as e:
                print(f"\n?????? Error (non-streaming): {type(e).__name__}: {e}")
                traceback.print_exc()
                return False, None, tool_calls

        return True, final_answer_str, tool_calls
    
    async def chat(self, message: str) -> str:
        """Handle consultation"""
        chat_system_message = """You are a developer. Answer questions directly and helpfully."""
        
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

DEFAULT_DEVELOPER_BASE_PROMPT = """You are an expert software developer. You write code by creating and modifying files.

Use only available tools and finish tasks with concrete code changes."""

DEFAULT_DEVELOPER_ENHANCED_PROMPT = """Build production-ready code with no placeholders.
Use real logic, handle failure paths, and keep edits scoped to task requirements."""

