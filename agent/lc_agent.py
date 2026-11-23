"""LangGraph Agent for Nexus AI Assistant.

Implements the autonomous tool-calling loop using LangGraph StateGraph, ToolNode,
human-in-the-loop approval interrupts, bidirectional screening guardrails,
local and LangSmith tracing, and checkpointed state persistence.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command

from agent.lc_tools import LANGGRAPH_TOOLS
from agent.persistence import get_checkpointer
from agent.prompts import SYSTEM_PROMPT
from agent.screening import screen_input, screen_output
from agent.tracing import get_active_callbacks, trace_span

logger = logging.getLogger("nexus.lc_agent")


class AgentState(TypedDict):
    """LangGraph agent state containing conversational message history."""
    messages: Annotated[List[BaseMessage], add_messages]


def get_default_checkpointer() -> BaseCheckpointSaver:
    """Create or connect to persistent SQLite checkpointer."""
    return get_checkpointer()


def get_model(custom_llm: Optional[Any] = None) -> Any:
    """Get the LLM model instance bound to all LangGraph tools."""
    if custom_llm is not None:
        return custom_llm

    api_key = os.getenv("OPENAI_API_KEY", "").strip() or "dummy"
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o").strip()

    llm = ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.2,
    )
    return llm.bind_tools(LANGGRAPH_TOOLS)


def build_agent_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    custom_llm: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
) -> Any:
    """Construct and compile the LangGraph agent StateGraph.

    Args:
        checkpointer: Custom or memory checkpointer instance.
        custom_llm: Optional mocked or custom LLM for testing.
        tools: Optional tool list (defaults to LANGGRAPH_TOOLS).
    """
    active_tools = tools if tools is not None else LANGGRAPH_TOOLS
    model = custom_llm if custom_llm is not None else get_model()

    def agent_node(state: AgentState) -> Dict[str, List[BaseMessage]]:
        raw_msgs = state.get("messages", [])
        # Ensure system prompt is present at head of message history
        if not raw_msgs or not isinstance(raw_msgs[0], SystemMessage):
            msgs_to_send = [SystemMessage(content=SYSTEM_PROMPT)] + list(raw_msgs)
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
            if out.get("__interrupt__"):
                interrupt_val = out["__interrupt__"][0].value
                prompt_text = (
                    interrupt_val.get("prompt")
                    if isinstance(interrupt_val, dict)
                    else str(interrupt_val)
                )
                screened_prompt = screen_output(prompt_text).sanitized_text
                span["outputs"] = {"interrupt": screened_prompt}
                return {
                    "reply": screened_prompt,
                    "spoken": screened_prompt,
                    "needs_confirmation": True,
                    "confirmation_data": interrupt_val,
                    "status": "pending_confirmation",
                    "session_id": session_id,
                    "screening": input_screen.to_dict(),
                }

            last_msg = out["messages"][-1]
            raw_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
            screened_content = screen_output(raw_content).sanitized_text

            span["outputs"] = {"reply": screened_content}
            return {
                "reply": screened_content,
                "spoken": screened_content,
                "needs_confirmation": False,
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
                "status": "error",
                "session_id": session_id,
            }


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
                "status": "not_found",
                "session_id": session_id,
            }

        with trace_span(
            name=f"resume:{session_id}",
            session_id=session_id,
            user_id=user_id,
            inputs={"decision": decision},
        ) as span:
            out = active_graph.invoke(Command(resume=decision), cfg)
            if out.get("__interrupt__"):
                interrupt_val = out["__interrupt__"][0].value
                prompt_text = (
                    interrupt_val.get("prompt")
                    if isinstance(interrupt_val, dict)
                    else str(interrupt_val)
                )
                screened_prompt = screen_output(prompt_text).sanitized_text
                span["outputs"] = {"interrupt": screened_prompt}
                return {
                    "reply": screened_prompt,
                    "spoken": screened_prompt,
                    "needs_confirmation": True,
                    "confirmation_data": interrupt_val,
                    "status": "pending_confirmation",
                    "session_id": session_id,
                }

            last_msg = out["messages"][-1]
            raw_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
            screened_content = screen_output(raw_content).sanitized_text

            span["outputs"] = {"reply": screened_content}
            return {
                "reply": screened_content,
                "spoken": screened_content,
                "needs_confirmation": False,
                "status": "success",
                "session_id": session_id,
            }
    except Exception as exc:
        logger.error(f"LangGraph resume error on session {session_id}: {exc}", exc_info=True)
        return {
            "reply": f"Error resuming execution: {exc}",
            "spoken": "Error resuming execution.",
            "needs_confirmation": False,
            "status": "error",
            "session_id": session_id,
        }
