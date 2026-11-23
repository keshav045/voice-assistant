"""Tracing and Observability Engine for Nexus AI Assistant.

Supports:
1. LangSmith Cloud Tracing: Automatically pipes traces to LangSmith when
   LANGCHAIN_TRACING_V2 or LANGSMITH_TRACING is true and LANGSMITH_API_KEY is configured.
2. 100% Offline Local Tracing: Captures execution waterfalls, LLM calls, tool spans,
   latencies, token counts, and errors into SQLite (execution_traces table) without
   requiring any external API keys or cloud egress.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from db.models import db_clear_traces, db_get_trace, db_list_traces, db_record_trace

logger = logging.getLogger("nexus.tracing")

# Configuration from environment
LANGSMITH_PROJECT = os.environ.get("LANGSMITH_PROJECT", "nexus-ai-assistant").strip()
LANGSMITH_API_KEY = os.environ.get("LANGSMITH_API_KEY", "").strip()
LANGCHAIN_TRACING_ENABLED = (
    os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() in {"1", "true", "yes"} or
    os.environ.get("LANGSMITH_TRACING", "false").lower() in {"1", "true", "yes"}
)


class NexusTracer(BaseCallbackHandler):
    """Local SQLite-backed execution tracer for LangGraph and LangChain pipelines.

    Captures chain, LLM, and tool spans with timing, arguments, outputs, and errors
    for 100% local, offline observability.
    """

    def __init__(self, session_id: str = "default", user_id: str = "guest"):
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id
        self._active_spans: Dict[str, Dict[str, Any]] = {}

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        name = (serialized or {}).get("name") or (metadata or {}).get("langgraph_node") or "Chain"
        meta = dict(metadata or {})
        if tags:
            meta["tags"] = tags
        if parent_run_id:
            meta["parent_run_id"] = str(parent_run_id)

        self._active_spans[rid] = {
            "name": name,
            "run_type": "chain",
            "start_time": time.time(),
            "inputs": inputs,
            "metadata": meta,
        }

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        span = self._active_spans.pop(rid, None)
        if not span:
            return

        end_t = time.time()
        lat = (end_t - span["start_time"]) * 1000.0

        clean_out = {}
        if isinstance(outputs, dict):
            for k, v in outputs.items():
                if k == "messages" and isinstance(v, list) and v:
                    clean_out[k] = [getattr(m, "content", str(m)) for m in v[-3:]]
                else:
                    clean_out[k] = str(v)[:300]
        else:
            clean_out = {"output": str(outputs)[:300]}

        db_record_trace(
            trace_id=rid,
            session_id=self.session_id,
            user_id=self.user_id,
            name=span["name"],
            run_type="chain",
            start_time=span["start_time"],
            end_time=end_t,
            latency_ms=round(lat, 2),
            status="success",
            inputs={"input_keys": list((span.get("inputs") or {}).keys())},
            outputs=clean_out,
            metadata=span.get("metadata", {}),
        )

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        span = self._active_spans.pop(rid, None)
        if not span:
            return
        end_t = time.time()
        lat = (end_t - span["start_time"]) * 1000.0
        meta = span.get("metadata", {})
        meta["error"] = str(error)

        db_record_trace(
            trace_id=rid,
            session_id=self.session_id,
            user_id=self.user_id,
            name=span["name"],
            run_type="chain",
            start_time=span["start_time"],
            end_time=end_t,
            latency_ms=round(lat, 2),
            status="error",
            inputs={},
            outputs={"error": str(error)},
            metadata=meta,
        )

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        name = (serialized or {}).get("name") or "Tool"
        meta = dict(metadata or {})
        if tags:
            meta["tags"] = tags

        self._active_spans[rid] = {
            "name": name,
            "run_type": "tool",
            "start_time": time.time(),
            "inputs": {"input": str(input_str)[:300]},
            "metadata": meta,
        }

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        span = self._active_spans.pop(rid, None)
        if not span:
            return
        end_t = time.time()
        lat = (end_t - span["start_time"]) * 1000.0

        db_record_trace(
            trace_id=rid,
            session_id=self.session_id,
            user_id=self.user_id,
            name=span["name"],
            run_type="tool",
            start_time=span["start_time"],
            end_time=end_t,
            latency_ms=round(lat, 2),
            status="success",
            inputs=span.get("inputs", {}),
            outputs={"output": str(output)[:400]},
            metadata=span.get("metadata", {}),
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        span = self._active_spans.pop(rid, None)
        if not span:
            return
        end_t = time.time()
        lat = (end_t - span["start_time"]) * 1000.0
        meta = span.get("metadata", {})
        meta["error"] = str(error)

        db_record_trace(
            trace_id=rid,
            session_id=self.session_id,
            user_id=self.user_id,
            name=span["name"],
            run_type="tool",
            start_time=span["start_time"],
            end_time=end_t,
            latency_ms=round(lat, 2),
            status="error",
            inputs=span.get("inputs", {}),
            outputs={"error": str(error)},
            metadata=meta,
        )

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        name = (serialized or {}).get("name") or "LLM"
        meta = dict(metadata or {})
        if tags:
            meta["tags"] = tags

        self._active_spans[rid] = {
            "name": name,
            "run_type": "llm",
            "start_time": time.time(),
            "inputs": {"prompt_count": len(prompts)},
            "metadata": meta,
        }

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        span = self._active_spans.pop(rid, None)
        if not span:
            return
        end_t = time.time()
        lat = (end_t - span["start_time"]) * 1000.0

        meta = span.get("metadata", {})
        if hasattr(response, "llm_output") and response.llm_output:
            meta["token_usage"] = response.llm_output.get("token_usage", {})

        db_record_trace(
            trace_id=rid,
            session_id=self.session_id,
            user_id=self.user_id,
            name=span["name"],
            run_type="llm",
            start_time=span["start_time"],
            end_time=end_t,
            latency_ms=round(lat, 2),
            status="success",
            inputs=span.get("inputs", {}),
            outputs={"generations": len(response.generations) if hasattr(response, "generations") else 1},
            metadata=meta,
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        span = self._active_spans.pop(rid, None)
        if not span:
            return
        end_t = time.time()
        lat = (end_t - span["start_time"]) * 1000.0
        meta = span.get("metadata", {})
        meta["error"] = str(error)

        db_record_trace(
            trace_id=rid,
            session_id=self.session_id,
            user_id=self.user_id,
            name=span["name"],
            run_type="llm",
            start_time=span["start_time"],
            end_time=end_t,
            latency_ms=round(lat, 2),
            status="error",
            inputs=span.get("inputs", {}),
            outputs={"error": str(error)},
            metadata=meta,
        )


@contextmanager
def trace_span(
    name: str,
    session_id: str = "default",
    inputs: Any = None,
    metadata: Any = None,
    user_id: str = "guest",
) -> Generator[Dict[str, Any], None, None]:
    """Context manager to record a local timing trace span for custom procedures."""
    span_id = f"span-{uuid.uuid4().hex[:10]}"
    start_t = time.time()
    span_data: Dict[str, Any] = {
        "id": span_id,
        "name": name,
        "session_id": session_id,
        "status": "success",
        "outputs": {},
        "metadata": dict(metadata or {}),
    }
    try:
        yield span_data
    except Exception as exc:
        span_data["status"] = "error"
        span_data["outputs"] = {"error": str(exc)}
        raise
    finally:
        end_t = time.time()
        lat = (end_t - start_t) * 1000.0
        db_record_trace(
            trace_id=span_id,
            session_id=session_id,
            user_id=user_id,
            name=name,
            run_type="span",
            start_time=start_t,
            end_time=end_t,
            latency_ms=round(lat, 2),
            status=span_data["status"],
            inputs=inputs or {},
            outputs=span_data["outputs"],
            metadata=span_data["metadata"],
        )


def is_langsmith_enabled() -> bool:
    """Check if LangSmith tracing is enabled and configured with an API key."""
    api_key = os.environ.get("LANGSMITH_API_KEY", "").strip()
    tracing = (
        os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() in {"1", "true", "yes"} or
        os.environ.get("LANGSMITH_TRACING", "false").lower() in {"1", "true", "yes"}
    )
    return bool(tracing and api_key and not api_key.startswith("your-"))


def get_langsmith_status() -> Dict[str, Any]:
    """Inspect current LangSmith connectivity and configuration status."""
    project = os.environ.get("LANGSMITH_PROJECT", "nexus-ai-assistant").strip()
    endpoint = os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").strip()
    api_key = os.environ.get("LANGSMITH_API_KEY", "").strip()
    enabled = is_langsmith_enabled()

    client_ready = False
    if enabled:
        try:
            from langsmith import Client
            client = Client(api_url=endpoint, api_key=api_key)
            client_ready = True
        except Exception as exc:
            logger.debug(f"Could not initialize LangSmith client: {exc}")

    return {
        "enabled": enabled,
        "project": project,
        "endpoint": endpoint,
        "has_api_key": bool(api_key and not api_key.startswith("your-")),
        "client_ready": client_ready,
    }


def get_active_callbacks(
    session_id: str = "default",
    user_id: str = "guest",
) -> List[BaseCallbackHandler]:
    """Get active tracing callbacks combining local SQLite tracer and optional LangSmith tracer."""
    callbacks: List[BaseCallbackHandler] = [NexusTracer(session_id=session_id, user_id=user_id)]

    # Add LangSmith tracer if configured and enabled
    if is_langsmith_enabled():
        try:
            from langchain_core.tracers import LangChainTracer
            project = os.environ.get("LANGSMITH_PROJECT", "nexus-ai-assistant").strip()
            callbacks.append(LangChainTracer(project_name=project))
            logger.info(f"LangSmith cloud tracing active for project: {project}")
        except Exception as e:
            logger.debug(f"Could not load LangChainTracer: {e}")

    return callbacks


def list_traces(limit: int = 50, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query recent execution traces from SQLite."""
    return db_list_traces(limit=limit, session_id=session_id)


def get_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    """Query a single trace by ID."""
    return db_get_trace(trace_id=trace_id)


def clear_traces() -> bool:
    """Clear all stored traces."""
    return db_clear_traces()
