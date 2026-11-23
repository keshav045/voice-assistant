"""LangGraph Agent for Nexus AI Assistant.

Implements the autonomous tool-calling loop using LangGraph StateGraph, ToolNode,
and human-in-the-loop approval interrupts with checkpointed state persistence.
"""

from __future__ import annotations

import logging
import os
import sqlite3
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
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command

from agent.lc_tools import LANGGRAPH_TOOLS
from agent.prompts import SYSTEM_PROMPT

logger = logging.getLogger("nexus.lc_agent")

CHECKPOINTS_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "checkpoints.sqlite"
)


class AgentState(TypedDict):
    """LangGraph agent state containing conversational message history."""
    messages: Annotated[List[BaseMessage], add_messages]


def get_default_checkpointer() -> BaseCheckpointSaver:
    """Create or connect to persistent SQLite checkpointer."""
    try:
        os.makedirs(os.path.dirname(CHECKPOINTS_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(CHECKPOINTS_DB_PATH, check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        return saver
    except Exception as exc:
        logger.warning(f"Could not initialize SqliteSaver ({exc}); falling back to InMemorySaver")
        return InMemorySaver()


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
) -> Dict[str, Any]:
    """Execute a single conversational turn through the LangGraph agent.

    Args:
        message: The user's input prompt.
        session_id: Session identifier used as LangGraph thread_id.
        user_id: Active user identifier.

    Returns:
        Dict containing reply, needs_confirmation status, and pending approval details.
    """
    cfg = {"configurable": {"thread_id": session_id}}
    try:
        out = graph.invoke(
            {"messages": [HumanMessage(content=message)]},
            cfg,
        )
        if out.get("__interrupt__"):
            interrupt_val = out["__interrupt__"][0].value
            prompt_text = (
                interrupt_val.get("prompt")
                if isinstance(interrupt_val, dict)
                else str(interrupt_val)
            )
            return {
                "reply": prompt_text,
                "spoken": prompt_text,
                "needs_confirmation": True,
                "confirmation_data": interrupt_val,
                "status": "pending_confirmation",
                "session_id": session_id,
            }

        last_msg = out["messages"][-1]
        content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        return {
            "reply": content,
            "spoken": content,
            "needs_confirmation": False,
            "status": "success",
            "session_id": session_id,
        }
    except Exception as exc:
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
) -> Dict[str, Any]:
    """Resume a halted LangGraph agent run with user's approval decision.

    Args:
        decision: 'yes' or 'no' (or affirmative/declining text).
        session_id: Session identifier used as LangGraph thread_id.

    Returns:
        Dict containing final assistant reply or not_found status.
    """
    cfg = {"configurable": {"thread_id": session_id}}
    try:
        current_state = graph.get_state(cfg)
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

        out = graph.invoke(Command(resume=decision), cfg)
        if out.get("__interrupt__"):
            interrupt_val = out["__interrupt__"][0].value
            prompt_text = (
                interrupt_val.get("prompt")
                if isinstance(interrupt_val, dict)
                else str(interrupt_val)
            )
            return {
                "reply": prompt_text,
                "spoken": prompt_text,
                "needs_confirmation": True,
                "confirmation_data": interrupt_val,
                "status": "pending_confirmation",
                "session_id": session_id,
            }

        last_msg = out["messages"][-1]
        content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        return {
            "reply": content,
            "spoken": content,
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
