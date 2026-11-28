"""LangGraph Agent for Nexus AI Assistant.

Implements the autonomous tool-calling loop using LangGraph StateGraph, ToolNode,
human-in-the-loop approval interrupts, bidirectional screening guardrails,
local and LangSmith tracing, and checkpointed state persistence.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command

from agent.lc_tools import LANGGRAPH_TOOLS, _CURRENT_USER_ID, _CURRENT_USER_QUERY
from agent.persistence import get_checkpointer
from agent.prompts import COMPACT_SYSTEM_PROMPT, SYSTEM_PROMPT
from agent.screening import screen_input, screen_output
from agent.tracing import get_active_callbacks, trace_span

load_dotenv(override=False)

logger = logging.getLogger("nexus.lc_agent")


class AgentState(TypedDict):
    """LangGraph agent state containing conversational message history."""
    messages: Annotated[List[BaseMessage], add_messages]


def get_default_checkpointer() -> BaseCheckpointSaver:
    """Create or connect to persistent SQLite checkpointer."""
    return get_checkpointer()


def _is_local_ollama(base_url: Optional[str] = None) -> bool:
    url = base_url if base_url is not None else os.getenv("OPENAI_BASE_URL", "")
    return bool(url and "11434" in str(url))


def get_model(custom_llm: Optional[Any] = None) -> Any:
    """Get the LLM model instance bound to all LangGraph tools."""
    if custom_llm is not None:
        return custom_llm

    api_key = os.getenv("OPENAI_API_KEY", "").strip() or "dummy"
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    is_local = _is_local_ollama(base_url)
    default_model = "qwen2.5:1.5b" if is_local else "gpt-4o"
    model_name = os.getenv("OPENAI_MODEL", default_model).strip() or default_model

    llm_kwargs: Dict[str, Any] = {
        "model": model_name,
        "base_url": base_url,
        "api_key": api_key,
        "temperature": 0.2,
        "timeout": 25.0,
        "max_retries": 1,
    }
    if is_local:
        extra_body: Dict[str, Any] = {"options": {"num_ctx": 4096}, "keep_alive": "30m"}
        if "qwen3" in model_name.lower():
            extra_body["think"] = False
        llm_kwargs["extra_body"] = extra_body

    llm = ChatOpenAI(**llm_kwargs)
    return llm.bind_tools(LANGGRAPH_TOOLS)


def _extract_executed_tools(messages: List[BaseMessage], start_idx: int = 0) -> List[Dict[str, Any]]:
    """Collect tool call records from new turn messages."""
    slice_msgs = list(messages or [])[max(0, start_idx):]
    tool_outputs: Dict[str, str] = {}
    for msg in slice_msgs:
        if isinstance(msg, ToolMessage):
            tool_outputs[getattr(msg, "tool_call_id", "") or msg.name or ""] = str(msg.content)

    executed: List[Dict[str, Any]] = []
    for msg in slice_msgs:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                t_name = tc.get("name") or ""
                if t_name == "search_web":
                    t_name = "web_search"
                t_args = tc.get("args") or {}
                t_id = tc.get("id") or t_name
                raw_out = tool_outputs.get(t_id) or tool_outputs.get(tc.get("name") or "", "")
                executed.append({
                    "tool": t_name,
                    "args": t_args,
                    "result": {"success": True, "spoken": raw_out},
                })
    return executed


def build_agent_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    custom_llm: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
) -> Any:
    """Construct and compile the LangGraph agent StateGraph."""
    active_tools = tools if tools is not None else LANGGRAPH_TOOLS
    model = custom_llm if custom_llm is not None else get_model()
    prompt_to_use = COMPACT_SYSTEM_PROMPT if _is_local_ollama() else SYSTEM_PROMPT

    def agent_node(state: AgentState) -> Dict[str, List[BaseMessage]]:
        raw_msgs = state.get("messages", [])
        if not raw_msgs or not isinstance(raw_msgs[0], SystemMessage):
            msgs_to_send = [SystemMessage(content=prompt_to_use)] + list(raw_msgs)
        else:
            msgs_to_send = list(raw_msgs)
        response = model.invoke(msgs_to_send)
        return {"messages": [response]}

    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("tools", ToolNode(active_tools))

    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition)
    g.add_edge("tools", "agent")

    active_checkpointer = checkpointer if checkpointer is not None else get_default_checkpointer()
    return g.compile(checkpointer=active_checkpointer)


# Singleton graph initialized at startup
graph = build_agent_graph()


def run_langgraph_turn(
    message: str,
    session_id: str,
    user_id: str = "guest",
    graph_instance: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute a single conversational turn through the LangGraph agent.

    Integrates:
    - Input screening (prompt injection, toxicity, physical realm, PII masking)
    - Active tracing callbacks (local SQLite spans + optional LangSmith)
    - Output screening (zero-markdown voice compliance, medical disclaimer)

    Args:
        message: The user's input prompt.
        session_id: Session identifier used as LangGraph thread_id.
        user_id: Active user identifier.
        graph_instance: Optional graph instance (for testing).

    Returns:
        Dict containing reply, spoken, needs_confirmation, and screening data.
    """
    active_graph = graph_instance if graph_instance is not None else graph

    # 1. Input Screening
    input_screen = screen_input(user_text=message, user_id=user_id)
    if not input_screen.passed:
        blocked_msg = input_screen.sanitized_text or "I cannot assist with this request."
        return {
            "reply": blocked_msg,
            "spoken": blocked_msg,
            "needs_confirmation": False,
            "status": "blocked",
            "session_id": session_id,
            "screening": input_screen.to_dict(),
        }

    clean_prompt = input_screen.sanitized_text
    callbacks = get_active_callbacks(session_id=session_id, user_id=user_id)
    cfg = {"configurable": {"thread_id": session_id}, "callbacks": callbacks}

    try:
        prev_state = active_graph.get_state(cfg)
        start_idx = len(prev_state.values.get("messages", [])) if prev_state and prev_state.values else 0
    except Exception:
        start_idx = 0

    uid_tok = _CURRENT_USER_ID.set(user_id or "guest")
    q_tok = _CURRENT_USER_QUERY.set(clean_prompt)
    with trace_span(
        name=f"turn:{session_id}",
        session_id=session_id,
        user_id=user_id,
        inputs={"message": clean_prompt},
    ) as span:
        try:
            out = active_graph.invoke(
                {"messages": [HumanMessage(content=clean_prompt)]},
                cfg,
            )
            executed_tools = _extract_executed_tools(out.get("messages", []), start_idx=start_idx)
            if out.get("__interrupt__"):
                interrupt_val = out["__interrupt__"][0].value
                prompt_text = (
                    interrupt_val.get("prompt")
                    if isinstance(interrupt_val, dict)
                    else str(interrupt_val)
                )
                screened_prompt = screen_output(prompt_text, tool_calls=executed_tools).sanitized_text
                span["outputs"] = {"interrupt": screened_prompt}
                return {
                    "reply": screened_prompt,
                    "spoken": screened_prompt,
                    "needs_confirmation": True,
                    "confirmation_data": interrupt_val,
                    "tool_calls_executed": executed_tools,
                    "status": "pending_confirmation",
                    "session_id": session_id,
                    "screening": input_screen.to_dict(),
                }

            last_msg = out["messages"][-1]
            raw_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
            screened_content = screen_output(raw_content, tool_calls=executed_tools).sanitized_text

            span["outputs"] = {"reply": screened_content}
            return {
                "reply": screened_content,
                "spoken": screened_content,
                "needs_confirmation": False,
                "tool_calls_executed": executed_tools,
                "status": "success",
                "session_id": session_id,
                "screening": input_screen.to_dict(),
            }
        except Exception as exc:
            span["status"] = "error"
            span["outputs"] = {"error": str(exc)}
            logger.error(f"LangGraph execution error on session {session_id}: {exc}", exc_info=True)
            return {
                "reply": f"I encountered an error executing this request: {exc}",
                "spoken": "I encountered an error processing your request.",
                "needs_confirmation": False,
                "tool_calls_executed": [],
                "status": "error",
                "session_id": session_id,
            }
        finally:
            _CURRENT_USER_ID.reset(uid_tok)
            _CURRENT_USER_QUERY.reset(q_tok)


def resume_langgraph_turn(
    decision: str,
    session_id: str,
    graph_instance: Optional[Any] = None,
    user_id: str = "guest",
) -> Dict[str, Any]:
    """Resume a halted LangGraph agent run with user's approval decision.

    Args:
        decision: 'yes' or 'no' (or affirmative/declining text).
        session_id: Session identifier used as LangGraph thread_id.
        graph_instance: Optional graph instance (for testing).
        user_id: Active user identifier.

    Returns:
        Dict containing final assistant reply or not_found status.
    """
    active_graph = graph_instance if graph_instance is not None else graph
    callbacks = get_active_callbacks(session_id=session_id, user_id=user_id)
    cfg = {"configurable": {"thread_id": session_id}, "callbacks": callbacks}

    try:
        current_state = active_graph.get_state(cfg)
        start_idx = len(current_state.values.get("messages", [])) if current_state and current_state.values else 0
        has_pending_interrupt = (
            any(t.interrupts for t in current_state.tasks)
            if current_state and current_state.tasks
            else False
        )
        if not has_pending_interrupt:
            return {
                "reply": "No pending confirmation found for this session.",
                "spoken": "No pending confirmation found for this session.",
                "needs_confirmation": False,
                "tool_calls_executed": [],
                "status": "not_found",
                "session_id": session_id,
            }

        uid_tok = _CURRENT_USER_ID.set(user_id or "guest")
        with trace_span(
            name=f"resume:{session_id}",
            session_id=session_id,
            user_id=user_id,
            inputs={"decision": decision},
        ) as span:
            try:
                out = active_graph.invoke(Command(resume=decision), cfg)
                executed_tools = _extract_executed_tools(out.get("messages", []), start_idx=start_idx)
                if out.get("__interrupt__"):
                    interrupt_val = out["__interrupt__"][0].value
                    prompt_text = (
                        interrupt_val.get("prompt")
                        if isinstance(interrupt_val, dict)
                        else str(interrupt_val)
                    )
                    screened_prompt = screen_output(prompt_text, tool_calls=executed_tools).sanitized_text
                    span["outputs"] = {"interrupt": screened_prompt}
                    return {
                        "reply": screened_prompt,
                        "spoken": screened_prompt,
                        "needs_confirmation": True,
                        "confirmation_data": interrupt_val,
                        "tool_calls_executed": executed_tools,
                        "status": "pending_confirmation",
                        "session_id": session_id,
                    }

                last_msg = out["messages"][-1]
                raw_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                screened_content = screen_output(raw_content, tool_calls=executed_tools).sanitized_text

                span["outputs"] = {"reply": screened_content}
                return {
                    "reply": screened_content,
                    "spoken": screened_content,
                    "needs_confirmation": False,
                    "tool_calls_executed": executed_tools,
                    "status": "success",
                    "session_id": session_id,
                }
            finally:
                _CURRENT_USER_ID.reset(uid_tok)
    except Exception as exc:
        logger.error(f"LangGraph resume error on session {session_id}: {exc}", exc_info=True)
        return {
            "reply": f"Error resuming execution: {exc}",
            "spoken": "Error resuming execution.",
            "needs_confirmation": False,
            "tool_calls_executed": [],
            "status": "error",
            "session_id": session_id,
        }
