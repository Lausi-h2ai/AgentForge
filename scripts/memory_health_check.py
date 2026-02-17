#!/usr/bin/env python3
"""
Memory health check for HippocampAI + Qdrant + Ollama.
Writes a test memory and immediately recalls it.
"""

import os
import sys
import time
import json

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    import httpx
except Exception:
    httpx = None

from memory.hippocampai_client import MemoryManager


def main() -> int:
    project = os.getenv("MEMORY_HEALTH_PROJECT", "memory_health_check")
    agent = os.getenv("MEMORY_HEALTH_AGENT", "HealthCheckAgent")
    query = "health check memory"
    payload = os.getenv(
        "MEMORY_HEALTH_TEXT",
        "I prefer oat milk in my coffee and work remotely from San Francisco."
    )

    mem = MemoryManager(enabled=True)
    if not mem.enabled:
        print("MemoryManager disabled or failed to initialize.")
        return 1

    payload = f"{payload} (timestamp={time.time()})"
    mem.remember(
        content=payload,
        project_name=project,
        agent_name=agent,
        memory_type="preference",
        importance=1.0,
        tags=["health_check"],
        store_global=False,
    )
    print("Wrote memory.")

    recalled = mem.recall_combined(query, project_name=project, agent_name=agent, top_k=5)
    print("Recall result:")
    print(recalled or "<empty>")

    # Debug stats if available
    if hasattr(mem, "_try_get_stats"):
        user_id = f"project:{project}|agent:{agent}"
        stats = mem._try_get_stats(user_id)
        if stats:
            print(f"Memory stats: {stats}")

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    if httpx:
        try:
            r = httpx.get(f"{qdrant_url}/collections", timeout=5.0)
            print(f"Qdrant collections: {r.status_code}")
            if r.status_code == 200:
                print(json.dumps(r.json(), indent=2))
        except Exception as e:
            print(f"Qdrant check failed: {e}")
    else:
        print("httpx not installed; skipping Qdrant REST check.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
