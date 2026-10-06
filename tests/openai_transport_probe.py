"""Real SDK and agent loop against a local scripted Chat Completions/SSE server."""

# ruff: noqa: E402 -- standalone probe sets the repository import path first
import asyncio
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import utils
from agents.code_reviewer_agent import CodeReviewerAgent
from agents.developer_agent import DeveloperAgent
from agents.llama_compat import ChatMessage, TokenCountingHandler
from aidev_orchestrator.orchestrator_tools import OrchestratorTools

responses = [
    "hello",
    "async-hello",
    "stream-hello",
    "Thought: I should create the requested file.\nAction: write_file\n"
    'Action Input: {"filename":"hello.txt","content":"hello"}',
    "Thought: The tool succeeded.\nAnswer: Created hello.txt.",
    'Thought: Review is complete.\nAction: submit_review\nAction Input: {"report":{"issues":[]}}',
]
requests = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append((self.path, body, self.headers.get("Authorization")))
        if self.path == "/v1/embeddings":
            inputs = body["input"]
            count = len(inputs) if isinstance(inputs, list) else 1
            data = {
                "object": "list",
                "model": body["model"],
                "data": [
                    {"object": "embedding", "index": i, "embedding": [0.1, 0.2, 0.3]}
                    for i in range(count)
                ],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            }
            payload = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/v1/chat/completions" and responses:
            content = responses.pop(0)
            base = {"id": "local-test", "created": 1, "model": body["model"]}
            self.send_response(200)
            if body.get("stream"):
                chunks = []
                # Fragmented SSE exercises streaming assembly, rather than only one full delta.
                for i in range(0, len(content), 17):
                    chunk = {
                        **base,
                        "object": "chat.completion.chunk",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": content[i : i + 17]},
                                "finish_reason": None,
                            }
                        ],
                    }
                    chunks.append("data: " + json.dumps(chunk) + "\n\n")
                chunks.append(
                    "data: "
                    + json.dumps(
                        {
                            **base,
                            "object": "chat.completion.chunk",
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        }
                    )
                    + "\n\n"
                )
                payload = ("".join(chunks) + "data: [DONE]\n\n").encode()
                self.send_header("Content-Type", "text/event-stream")
            else:
                data = {
                    **base,
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
                payload = json.dumps(data).encode()
                self.send_header("Content-Type", "application/json")
        else:
            self.send_error(400, "Unexpected request")
            return
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


async def probe(base):
    for name in list(os.environ):
        if name.startswith(("OPENAI_", "LLM_", "EMBEDDING_")):
            os.environ.pop(name)
    os.environ.update(
        OPENAI_BASE_URL=base,
        LLM_MODEL="vendor/test-model",
        OPENAI_API_KEY="local-test-key",
        EMBEDDING_PROVIDER="none",
        OPENAI_ADDITIONAL_KWARGS='{"extra_body":{"top_k":7}}',
    )
    # Deterministic test tokenizer avoids downloading tokenizer data during offline verification.
    utils.TokenCountingHandler = lambda: TokenCountingHandler(tokenizer=lambda text: text.split())
    llm_class, args, _ = utils.configure_llm_and_embed("openai")
    llm = llm_class(**args)
    messages = [ChatMessage(role="user", content="hello")]
    assert llm.chat(messages).message.content == "hello"
    assert (await llm.achat(messages)).message.content == "async-hello"
    stream = await llm.astream_chat(messages)
    assert "".join([part.delta async for part in stream]) == "stream-hello"
    with tempfile.TemporaryDirectory() as directory:
        tools = OrchestratorTools(SimpleNamespace(project_dir=directory, files={}))
        developer = DeveloperAgent(llm_class, args, tools, None)
        success, _, calls = await developer.run("Create hello.txt containing hello.")
        assert success and any(call["tool_name"] == "write_file" for call in calls)
        assert Path(directory, "hello.txt").read_text() == "hello"
        reviewer = CodeReviewerAgent(llm_class, args, tools, None)
        issues, history = await reviewer.review_code("Review hello.txt", "hello.txt", "hello", [])
        assert issues == [] and any(call["tool_name"] == "submit_review" for call in history)
    assert all(path == "/v1/chat/completions" for path, _, _ in requests)
    assert all(body["model"] == "vendor/test-model" for _, body, _ in requests)
    assert all(body["max_tokens"] == 4096 and body["top_k"] == 7 for _, body, _ in requests)
    assert all(auth == "Bearer local-test-key" for _, _, auth in requests)
    assert not responses
    os.environ.update(EMBEDDING_PROVIDER="openai", EMBEDDING_MODEL="vendor/custom-embedding")
    utils.configure_llm_and_embed("openai")
    assert utils.Settings.embed_model.get_text_embedding("hello") == [0.1, 0.2, 0.3]
    assert requests[-1][0] == "/v1/embeddings"
    assert requests[-1][1]["model"] == "vendor/custom-embedding"
    print(
        "PASS: real SDK sync/async/SSE, developer/reviewer tool loops, "
        "arbitrary models, optional embeddings"
    )


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        asyncio.run(probe(f"http://127.0.0.1:{server.server_port}/v1"))
    finally:
        server.shutdown()
        server.server_close()
