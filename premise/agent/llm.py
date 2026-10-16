"""Provider selection and the Anthropic adapter; verdicts never depend on either provider."""
from __future__ import annotations

import hashlib
import json
from anthropic import Anthropic


def make_adapter(settings, graph=None):
    if settings.llm_provider == "codex-cli":
        from .codex_cli import CodexAdapter
        return CodexAdapter(settings.codex_binary, settings.codex_model, graph, settings.codex_timeout_seconds)
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        return Adapter(settings.anthropic_api_key, settings.llm_model, graph)
    raise ValueError("No model provider configured")


def request(model, system, messages, tools=None):
    out = {"model": model, "max_tokens": 16000, "system": system, "messages": messages,
           "output_config": {"effort": "medium"}}
    if tools:
        out["tools"] = tools
    return out


def _plain(response):
    return response.model_dump(mode="json") if hasattr(response, "model_dump") else response


class Adapter:
    def __init__(self, api_key, model, graph=None, provider=None):
        self.provider = provider or Anthropic(api_key=api_key, timeout=45, max_retries=0)
        self.model, self.graph = model, graph

    def create(self, payload):
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if self.graph:
            rows = self.graph.read("MATCH (c:LLMCache {id:$id}) RETURN c.response_json AS response", {"id": key})
            if rows:
                return json.loads(rows[0]["response"])
        response = _plain(self.provider.messages.create(**payload))
        if self.graph:
            self.graph.write("MERGE (c:LLMCache {id:$id}) SET c.response_json=$response",
                             {"id": key, "response": json.dumps(response)})
        return response

    def tool_loop(self, system, question, schemas, dispatch, budget):
        messages = [{"role": "user", "content": question}]
        calls = 0
        for _ in range(budget + 1):
            response = self.create(request(self.model, system, messages, schemas))
            if response.get("stop_reason") in ("refusal", "max_tokens"):
                return None
            blocks = response.get("content", [])
            tools = [b for b in blocks if b.get("type") == "tool_use"]
            if not tools:
                raw = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                try:
                    return json.loads(raw)
                except (ValueError, TypeError):
                    return None
            if calls + len(tools) > budget:
                return None
            # Preserve thinking/signature and all earlier blocks exactly as supplied by the SDK.
            messages.append({"role": "assistant", "content": blocks})
            results = []
            for block in tools:
                calls += 1
                try:
                    value = dispatch(block["name"], block["input"])
                    content, error = json.dumps(value, default=str), False
                except (ValueError, KeyError, TypeError) as exc:
                    content, error = json.dumps({"error": type(exc).__name__}), True
                results.append({"type": "tool_result", "tool_use_id": block["id"], "content": content, "is_error": error})
            messages.append({"role": "user", "content": results})
        return None

    def structured(self, system, question):
        return self.tool_loop(system, question, [], lambda *_: None, 0)


def tool_loop(adapter, *args, **kwargs):
    return adapter.tool_loop(*args, **kwargs)


def structured(adapter, *args, **kwargs):
    return adapter.structured(*args, **kwargs)
