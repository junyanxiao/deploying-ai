from __future__ import annotations

from pathlib import Path
from typing import Annotated
import operator
import os

if os.getenv("ASSIGNMENT_CHAT_ENABLE_LANGSMITH", "FALSE").upper() != "TRUE":
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt.tool_node import ToolNode
from typing_extensions import TypedDict

from assignment_chat.guardrails import check_user_message
from assignment_chat.prompts import return_instructions
from assignment_chat.tools_places import search_toronto_places
from assignment_chat.tools_planner import build_weekend_plan
from assignment_chat.tools_weather import get_weather
from utils.logger import get_logger


_logs = get_logger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
load_dotenv(SRC_DIR / ".env")
load_dotenv(SRC_DIR / ".secrets")

TOOLS = [get_weather, search_toronto_places, build_weekend_plan]
MAX_LLM_CALLS = 4


class AssignmentChatState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int


def _init_model():
    model_name = os.getenv("ASSIGNMENT_CHAT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    if ":" in model_name:
        model_name = model_name.split(":", 1)[1]

    if os.getenv("USE_GATEWAY", "FALSE").upper() == "TRUE":
        return init_chat_model(
            model_name,
            model_provider="openai",
            base_url="https://k7uffyg03f.execute-api.us-east-1.amazonaws.com/prod/openai/v1",
            api_key="any value",
            default_headers={"x-api-key": os.getenv("API_GATEWAY_KEY", "")},
        )

    if ":" in model_name:
        return init_chat_model(model_name)
    return init_chat_model(model_name, model_provider="openai")


chat_agent = _init_model()
model_with_tools = chat_agent.bind_tools(TOOLS)
instructions = return_instructions()


def call_model(state: AssignmentChatState):
    response = model_with_tools.invoke(
        [SystemMessage(content=instructions)] + state["messages"]
    )
    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def should_continue(state: AssignmentChatState):
    if state.get("llm_calls", 0) >= MAX_LLM_CALLS:
        _logs.warning("Stopping tool loop after %s LLM calls", state.get("llm_calls"))
        return END

    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


def get_graph():
    builder = StateGraph(AssignmentChatState)
    builder.add_node("call_model", call_model)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges("call_model", should_continue, ["tools", END])
    builder.add_edge("tools", "call_model")
    return builder.compile()


graph = get_graph()


def _history_to_messages(history: list[dict]) -> list[AnyMessage]:
    langchain_messages = []
    for msg in history or []:
        if isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content")
            if not isinstance(content, str):
                continue
            if role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
        elif isinstance(msg, (list, tuple)) and len(msg) >= 2:
            user_content, assistant_content = msg[0], msg[1]
            if isinstance(user_content, str) and user_content:
                langchain_messages.append(HumanMessage(content=user_content))
            if isinstance(assistant_content, str) and assistant_content:
                langchain_messages.append(AIMessage(content=assistant_content))
    return langchain_messages


def assignment_chat(message: str, history: list[dict] | None = None) -> str:
    _logs.info("User message: %s", message)

    guardrail_result = check_user_message(message)
    if guardrail_result.blocked:
        _logs.info("Guardrail blocked message: %s", guardrail_result.reason)
        return guardrail_result.response or "I cannot help with that request."

    langchain_messages = _history_to_messages(history or [])
    langchain_messages.append(HumanMessage(content=message))

    try:
        response = graph.invoke(
            {"messages": langchain_messages, "llm_calls": 0},
            config={"recursion_limit": 10},
        )
    except Exception as exc:
        _logs.error("Assignment chat failed with %s", type(exc).__name__)
        return (
            "I'm sorry, something went wrong while I was putting that together. "
            "I can still help with Toronto weather, places, or a simple weekend plan if you try again."
        )

    messages = response.get("messages", [])
    if not messages:
        return "I could not generate a response this time. Please try again."

    final_message = messages[-1]
    final_content = getattr(final_message, "content", "")
    if isinstance(final_content, list):
        final_content = "\n".join(str(item) for item in final_content)
    if not final_content:
        return "I could not generate a response this time. Please try again."
    return str(final_content)
