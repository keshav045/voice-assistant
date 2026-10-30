"""Nexus 9-Node LangGraph Agent Orchestrator."""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI
from app.agents.policy import PolicyEngine
from app.agents.tools.tool_registry import TOOL_SCHEMAS, execute_tool_call
from app.core.config import settings
from app.workflows.state import AgentState

logger = logging.getLogger("nexus.orchestrator")


# --- Node 1: Understand Request ---
async def understand_request(state: AgentState) -> Dict[str, Any]:
    """Normalize input message and context."""
    raw_message = state.get("user_message", "").strip()
    return {
        "user_message": raw_message,
        "workflow_status": "running",
        "tool_results": state.get("tool_results", []),
        "pending_tool_calls": state.get("pending_tool_calls", []),
    }


# --- Node 2: Classify Intent ---
async def classify_intent(state: AgentState) -> Dict[str, Any]:
    """Identify the primary goal and domain."""
    msg = state.get("user_message", "").lower()

    if any(k in msg for k in ["task", "todo", "to-do", "reminder"]):
        intent = "task_management"
    elif any(k in msg for k in ["email", "mail", "gmail", "inbox"]):
        intent = "email_assistant"
    elif any(k in msg for k in ["calendar", "meeting", "schedule", "appointment"]):
        intent = "calendar_assistant"
    elif any(k in msg for k in ["desktop", "app", "window", "folder", "open"]):
        intent = "desktop_companion"
    else:
        intent = "general_assistant"

    return {"normalized_intent": intent}


# --- Node 3: Plan Actions ---
async def plan_actions(state: AgentState) -> Dict[str, Any]:
    """Formulate the action plan and decide if tool calls are needed."""
    user_msg = state.get("user_message", "")
    intent = state.get("normalized_intent", "general_assistant")

    # If OpenAI API is available, use tool calling
    if settings.OPENAI_API_KEY:
        try:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are Nexus, an agentic productivity orchestrator. "
                        "Given the user request, call the appropriate tool when needed. "
                        "Be concise and accurate."
                    ),
                },
                {"role": "user", "content": user_msg},
            ]
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.0,
            )
            msg = response.choices[0].message
            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}
                    tool_calls.append({"tool": tc.function.name, "args": args})

            if tool_calls:
                return {
                    "pending_tool_calls": tool_calls,
                    "plan": {"steps": [tc["tool"] for tc in tool_calls]},
                }
        except Exception as e:
            logger.warning(f"OpenAI planning fallback to deterministic planner: {e}")

    # Deterministic planner fallback (ensures 100% reliable local testing and offline capability)
    lower = user_msg.lower()
    tool_calls = []

    if "delete task" in lower or "remove task" in lower:
        # Extract task id if mentioned or use default sample
        words = lower.split()
        task_id = "task-sample-1"
        for w in words:
            if "task-" in w:
                task_id = w
        tool_calls.append({"tool": "delete_task", "args": {"task_id": task_id}})
    elif "list" in lower or "show" in lower or "tasks" in lower and "create" not in lower:
        tool_calls.append({"tool": "list_tasks", "args": {}})
    elif "create task" in lower or "add task" in lower or "schedule" in lower:
        title = user_msg.replace("create task", "").replace("add task", "").strip() or "New Task"
        tool_calls.append({"tool": "create_task", "args": {"title": title, "priority": "high"}})

    return {
        "pending_tool_calls": tool_calls,
        "plan": {"steps": [tc["tool"] for tc in tool_calls] if tool_calls else ["direct_reply"]},
    }


# --- Node 4: Route Agent ---
async def route_agent(state: AgentState) -> Dict[str, Any]:
    """Select the specialist agent domain."""
    intent = state.get("normalized_intent", "general_assistant")
    agent_map = {
        "task_management": "TaskAgent",
        "email_assistant": "EmailAgent",
        "calendar_assistant": "CalendarAgent",
        "desktop_companion": "DesktopAgent",
    }
    return {"current_agent": agent_map.get(intent, "GeneralAgent")}


# --- Node 5: Approval Gate (Deterministic Policy Check) ---
async def approval_gate(state: AgentState) -> Dict[str, Any]:
    """Enforce policy. Pause graph if action requires explicit user approval."""
    pending_calls = state.get("pending_tool_calls", [])
    if not pending_calls:
        return {"approval_required": False, "approval_status": "none"}

    next_call = pending_calls[0]
    tool_name = next_call["tool"]
    tool_args = next_call.get("args", {})

    # Check if this tool execution was already approved by user
    if state.get("approval_status") == "approved":
        return {
            "current_tool_call": next_call,
            "approval_required": False,
        }

    # Evaluate against deterministic policy
    decision = PolicyEngine.evaluate(tool_name, tool_args)

    if not decision.allowed:
        return {
            "workflow_status": "failed",
            "error_details": decision.reason,
            "final_response": f"Action blocked by policy: {decision.reason}",
            "approval_required": False,
        }

    if decision.requires_approval:
        approval_id = f"appr-{uuid.uuid4().hex[:8]}"
        payload = {
            "approval_id": approval_id,
            "tool_name": tool_name,
            "action_summary": decision.action_summary,
            "tool_payload": tool_args,
        }
        return {
            "approval_required": True,
            "approval_status": "pending",
            "approval_id": approval_id,
            "approval_payload": payload,
            "workflow_status": "pending_approval",
            "current_tool_call": next_call,
            "final_response": (
                f"⚠️ Confirmation Required: Nexus proposed to execute '{decision.action_summary}'. "
                f"Please review and approve or reject this action."
            ),
        }

    # Safe tool: proceed to execute
    return {
        "current_tool_call": next_call,
        "approval_required": False,
        "approval_status": "none",
    }


# --- Node 6: Execute Tool ---
async def execute_tool(state: AgentState) -> Dict[str, Any]:
    """Execute the approved tool call and collect results."""
    tool_call = state.get("current_tool_call")
    if not tool_call:
        return {}

    tool_name = tool_call["tool"]
    args = tool_call.get("args", {})

    exec_result = execute_tool_call(tool_name, args)

    results = list(state.get("tool_results", []))
    results.append({
        "tool": tool_name,
        "args": args,
        "output": exec_result,
    })

    # Pop executed tool from pending list
    pending = list(state.get("pending_tool_calls", []))
    if pending:
        pending.pop(0)

    return {
        "tool_results": results,
        "pending_tool_calls": pending,
        "current_tool_call": None,
    }


# --- Node 7: Validate Result ---
async def validate_result(state: AgentState) -> Dict[str, Any]:
    """Verify tool output and detect partial failure."""
    results = state.get("tool_results", [])
    if not results:
        return {}

    last_res = results[-1].get("output", {})
    if not last_res.get("success", False):
        error_msg = last_res.get("error", "Unknown tool execution failure")
        return {
            "workflow_status": "degraded",
            "error_details": error_msg,
        }

    return {"workflow_status": "running"}


# --- Node 8: Save Memory ---
async def save_memory(state: AgentState) -> Dict[str, Any]:
    """Persist context or audit markers."""
    # Audit trail marker saved with state
    return {"workflow_status": "completed"}


# --- Node 9: Generate Response ---
async def generate_response(state: AgentState) -> Dict[str, Any]:
    """Formulate natural language explanation of the outcome."""
    # If response was already set by approval gate or failure
    if state.get("final_response") and state.get("approval_status") == "pending":
        return {"final_response": state["final_response"]}

    results = state.get("tool_results", [])
    user_msg = state.get("user_message", "")

    if not results:
        return {
            "final_response": f"I received your request: '{user_msg}'. No specific tools were required."
        }

    last_tool = results[-1]
    tool_name = last_tool["tool"]
    output = last_tool["output"]

    if output.get("success"):
        res_data = output.get("result", {})
        msg = res_data.get("message")
        if not msg and "tasks" in res_data:
            msg = f"You currently have {len(res_data['tasks'])} tasks in your system."
        final_text = msg or f"Operation '{tool_name}' completed successfully."
    else:
        final_text = f"Operation '{tool_name}' failed: {output.get('error')}"

    return {"final_response": final_text}


# --- Conditional Routing Edge ---
def should_pause_for_approval(state: AgentState) -> str:
    """Decide whether to execute tool or pause graph at approval gate."""
    if state.get("approval_required") and state.get("approval_status") == "pending":
        return END  # Pauses execution!
    if state.get("workflow_status") == "failed":
        return "generate_response"
    if state.get("current_tool_call"):
        return "execute_tool"
    return "generate_response"


# --- Build StateGraph ---
def build_nexus_graph() -> StateGraph:
    """Construct and compile the Nexus LangGraph agent workflow."""
    workflow = StateGraph(AgentState)

    # Add 9 Nodes
    workflow.add_node("understand_request", understand_request)
    workflow.add_node("classify_intent", classify_intent)
    workflow.add_node("plan_actions", plan_actions)
    workflow.add_node("route_agent", route_agent)
    workflow.add_node("approval_gate", approval_gate)
    workflow.add_node("execute_tool", execute_tool)
    workflow.add_node("validate_result", validate_result)
    workflow.add_node("save_memory", save_memory)
    workflow.add_node("generate_response", generate_response)

    # Connect Edges
    workflow.set_entry_point("understand_request")
    workflow.add_edge("understand_request", "classify_intent")
    workflow.add_edge("classify_intent", "plan_actions")
    workflow.add_edge("plan_actions", "route_agent")
    workflow.add_edge("route_agent", "approval_gate")

    # Conditional Branch from Approval Gate
    workflow.add_conditional_edges(
        "approval_gate",
        should_pause_for_approval,
        {
            "execute_tool": "execute_tool",
            "generate_response": "generate_response",
            END: END,
        },
    )

    workflow.add_edge("execute_tool", "validate_result")
    workflow.add_edge("validate_result", "save_memory")
    workflow.add_edge("save_memory", "generate_response")
    workflow.add_edge("generate_response", END)

    return workflow.compile()


# Global orchestrator instance
nexus_orchestrator = build_nexus_graph()
