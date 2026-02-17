"""
HippocampAI memory wrapper with safe imports and local-only defaults.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, List, Optional


class MemoryManager:
    """
    Thin wrapper around HippocampAI MemoryClient that:
    - Defaults to local Qdrant + Ollama
    - Supports project/agent/global scopes
    - Falls back gracefully if the dependency is missing
    """

    def __init__(
        self,
        enabled: bool = True,
        qdrant_url: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        logger: Optional[Any] = None,
        enable_global_memory: bool = True,
    ) -> None:
        self.enabled = enabled
        self.logger = logger
        self.enable_global_memory = enable_global_memory
        self.debug = os.getenv("HIPPOCAMP_AI_DEBUG", "false").lower() == "true"
        self._client = None

        if not self.enabled:
            self._log("INFO", "HippocampAI memory disabled by config.")
            return

        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.llm_provider = llm_provider or os.getenv("HIPPOCAMP_AI_LLM_PROVIDER") or os.getenv("LLM_PROVIDER", "ollama")
        self.llm_model = llm_model or os.getenv("HIPPOCAMP_AI_LLM_MODEL") or os.getenv("LLM_MODEL")
        self.ollama_base_url = os.getenv("HIPPOCAMP_AI_OLLAMA_BASE_URL") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.default_visibility = os.getenv("HIPPOCAMP_AI_VISIBILITY", "private")
        self.run_id = os.getenv("HIPPOCAMP_AI_RUN_ID")

        self._client = self._init_client()
        if self._client:
            self._log(
                "INFO",
                f"HippocampAI memory initialized (provider={self.llm_provider}, model={self.llm_model}, qdrant={self.qdrant_url}, ollama={self.ollama_base_url})."
            )

    def _init_client(self):
        try:
            # Attempt common import paths
            try:
                from hippocampai import MemoryClient  # type: ignore
                from hippocampai.adapters import OllamaLLM  # type: ignore
            except Exception as e:
                if self.debug:
                    self._log("WARNING", f"HippocampAI import failed (hippocampai.MemoryClient): {e}")
                MemoryClient = None
                OllamaLLM = None
                try:
                    from hippocampai.memory_client import MemoryClient  # type: ignore
                except Exception as e2:
                    if self.debug:
                        self._log("WARNING", f"HippocampAI import failed (hippocampai.memory_client): {e2}")
                    try:
                        from hippocampai.core import MemoryClient  # type: ignore
                        from hippocampai.adapters import OllamaLLM  # type: ignore
                    except Exception as e3:
                        if self.debug:
                            self._log("WARNING", f"HippocampAI import failed (hippocampai.core): {e3}")
                        MemoryClient = None

            if MemoryClient is None:
                self._log("WARNING", "HippocampAI not available; memory disabled.")
                self.enabled = False
                return None

            # Prefer adapter-based initialization per getting-started guide
            try:
                llm_adapter = None
                if self.llm_provider == "ollama" and OllamaLLM is not None:
                    llm_adapter = OllamaLLM(
                        base_url=self.ollama_base_url,
                        model=self.llm_model or "gemma3:4b",
                    )
                if llm_adapter is not None:
                    return MemoryClient(
                        llm_provider=llm_adapter,
                        qdrant_url=self.qdrant_url,
                    )
            except Exception as e:
                if self.debug:
                    self._log("WARNING", f"HippocampAI adapter init failed, falling back to kwargs: {e}")

            # Fallback: try direct kwargs
            try:
                return MemoryClient(
                    qdrant_url=self.qdrant_url,
                )
            except Exception:
                return MemoryClient()
        except Exception as e:
            self._log("WARNING", f"Failed to initialize HippocampAI: {e}")
            self.enabled = False
            return None

    def _log(self, level: str, msg: str) -> None:
        if self.logger and hasattr(self.logger, "log"):
            try:
                self.logger.log(level, msg)
            except Exception:
                pass
        elif self.debug:
            print(f"[{level}] {msg}")

    def _try_get_stats(self, user_id: str) -> str:
        if not self._client:
            return ""
        try:
            if hasattr(self._client, "get_memory_statistics"):
                stats = self._client.get_memory_statistics(user_id=user_id)
                return f"stats={stats}"
        except Exception as e:
            return f"stats_error={e}"
        try:
            if hasattr(self._client, "get_memories"):
                memories = self._client.get_memories(user_id=user_id, limit=5, offset=0)
                return f"memories_sample_count={len(memories)}"
        except Exception as e:
            return f"memories_error={e}"
        return ""

    @staticmethod
    def _build_user_id(project_name: str, agent_name: Optional[str] = None) -> str:
        if agent_name:
            return f"project:{project_name}|agent:{agent_name}"
        return f"project:{project_name}"

    def _global_user_id(self) -> str:
        return "global"

    def recall_combined(
        self,
        query: str,
        project_name: str,
        agent_name: Optional[str] = None,
        top_k: int = 5,
        max_chars: int = 2000,
    ) -> str:
        if not self.enabled or not self._client:
            return ""

        blocks: List[str] = []

        # Project scope
        project_id = self._build_user_id(project_name)
        blocks.extend(self._recall_for_user(query, project_id, top_k, agent_name))

        # Agent-in-project scope
        if agent_name:
            agent_id = self._build_user_id(project_name, agent_name)
            blocks.extend(self._recall_for_user(query, agent_id, top_k, agent_name))

        # Global scope (optional)
        if self.enable_global_memory:
            blocks.extend(self._recall_for_user(query, self._global_user_id(), top_k, agent_name))

        combined = self._format_memories(blocks)
        if self.debug:
            self._log(
                "INFO",
                f"Memory recall: project={project_name} agent={agent_name} items={len(blocks)} chars={len(combined)}"
            )
            if len(blocks) == 0:
                user_id = self._build_user_id(project_name, agent_name) if agent_name else self._build_user_id(project_name)
                stats = self._try_get_stats(user_id)
                if stats:
                    self._log("INFO", f"Memory recall debug: user_id={user_id} {stats}")
        if max_chars and len(combined) > max_chars:
            combined = combined[:max_chars] + "..."
        return combined

    def remember(
        self,
        content: str,
        project_name: str,
        agent_name: Optional[str] = None,
        memory_type: str = "note",
        importance: float = 0.5,
        tags: Optional[Iterable[str]] = None,
        store_global: bool = False,
    ) -> None:
        if not self.enabled or not self._client or not content:
            return True

        payload = self._decorate_memory(content, memory_type, tags)
        user_id = self._build_user_id(project_name, agent_name)

        stored = self._safe_remember(payload, user_id, importance, memory_type, tags, agent_name)
        if self.debug:
            self._log(
                "INFO",
                f"Memory store: user_id={user_id} type={memory_type} importance={importance} global={store_global}"
            )
            if not stored:
                self._log("WARNING", "Memory store reported failure.")

        if store_global and self.enable_global_memory:
            self._safe_remember(payload, self._global_user_id(), importance, memory_type, tags, agent_name)

    def _decorate_memory(
        self,
        content: str,
        memory_type: str,
        tags: Optional[Iterable[str]],
    ) -> str:
        tag_str = ""
        if tags:
            tag_str = " | Tags: " + ", ".join(sorted(set(t for t in tags if t)))
        return f"[{memory_type}] {content}{tag_str}"

    def _normalize_type(self, memory_type: str, tags: Optional[Iterable[str]]) -> tuple[str, List[str]]:
        allowed = {"fact", "preference", "goal", "habit", "event", "context", "procedural"}
        mt = (memory_type or "context").lower()
        tag_list = list(tags) if tags else []
        if mt not in allowed:
            tag_list.append(f"orig_type:{mt}")
            mt = "context"
        return mt, tag_list

    def _safe_remember(
        self,
        payload: str,
        user_id: str,
        importance: float,
        memory_type: str,
        tags: Optional[Iterable[str]],
        agent_id: Optional[str],
    ) -> bool:
        normalized_type, normalized_tags = self._normalize_type(memory_type, tags)
        try:
            result = self._client.remember(
                text=payload,
                user_id=user_id,
                type=normalized_type,
                importance=importance,
                tags=normalized_tags or None,
                agent_id=agent_id,
                run_id=self.run_id,
                visibility=self.default_visibility,
            )
            if self.debug:
                meta = []
                if hasattr(result, "id"):
                    meta.append(f"id={getattr(result, 'id', None)}")
                if hasattr(result, "extracted_facts"):
                    meta.append(f"facts={len(getattr(result, 'extracted_facts', []) or [])}")
                if meta:
                    self._log("INFO", f"Memory store result: {', '.join(meta)}")
            return True
        except TypeError:
            pass
        except Exception as e:
            if self.debug:
                self._log("WARNING", f"Memory store failed: {e}")
            return False

        try:
            result = self._client.remember(text=payload, user_id=user_id)
            if self.debug and hasattr(result, "id"):
                self._log("INFO", f"Memory store fallback result: id={getattr(result, 'id', None)}")
            return True
        except Exception as e:
            if self.debug:
                self._log("WARNING", f"Memory store fallback failed: {e}")
            return False

    def _recall_for_user(
        self,
        query: str,
        user_id: str,
        top_k: int,
        agent_id: Optional[str],
    ) -> List[str]:
        try:
            filters = {"agent_id": agent_id} if agent_id else None
            result = self._client.recall(query=query, user_id=user_id, k=top_k, filters=filters)
        except TypeError:
            try:
                result = self._client.recall(query, user_id)
            except Exception:
                return []
        except Exception:
            return []

        return self._coerce_memories(result)

    @staticmethod
    def _coerce_memories(result: Any) -> List[str]:
        if result is None:
            return []
        if isinstance(result, str):
            return [result]
        if isinstance(result, dict):
            for key in ("memories", "results", "items", "data"):
                if key in result and isinstance(result[key], list):
                    return [MemoryManager._coerce_item(x) for x in result[key]]
            return [str(result)]
        if isinstance(result, list):
            return [MemoryManager._coerce_item(x) for x in result]
        return [str(result)]

    @staticmethod
    def _coerce_item(item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            for key in ("memory", "content", "text", "summary"):
                if key in item and item[key]:
                    return str(item[key])
            return str(item)
        if hasattr(item, "memory") and hasattr(item.memory, "text"):
            try:
                return str(item.memory.text)
            except Exception:
                return str(item)
        return str(item)

    @staticmethod
    def _format_memories(memories: List[str]) -> str:
        if not memories:
            return ""
        lines = ["MEMORY CONTEXT:"]
        for mem in memories:
            if mem:
                lines.append(f"- {mem}")
        return "\n".join(lines) + "\n"
