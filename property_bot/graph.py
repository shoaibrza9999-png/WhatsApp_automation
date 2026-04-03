import os
import json
from typing import Annotated, Literal, TypedDict, Dict, Any
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from tools import LogRent, LogPowerBill, UpdateMeter, EditTxn, GetGlobalHistory, GetMyLedger
from whatsapp import send_whatsapp_text

# Configure LLM
# Using "llama-3.1-70b-versatile" as approximation for Groq OSS 120b since 120b identifier may vary.
# You requested gpt-oss-120b with disabled reasoning, adjust the model string as needed for your specific Groq access.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
llm = ChatGroq(model_name="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0, api_key=GROQ_API_KEY)

# --- Admin Graph ---
admin_tools = [LogRent, LogPowerBill, UpdateMeter, EditTxn, GetGlobalHistory]
admin_llm = llm.bind_tools(admin_tools)

class AgentState(MessagesState):
    sender_id: str
    tenant_id: int

def admin_agent_node(state: AgentState):
    messages = state["messages"]
    system_prompt = SystemMessage(content="You are a helpful property management assistant for the admin. Your job is to clarify missing data and use tools to log transactions or answer queries.")

    # We only send the last 70 messages to Groq as requested
    msg_history = [system_prompt] + messages[-70:]
    response = admin_llm.invoke(msg_history)
    return {"messages": [response]}

def should_continue_admin(state: AgentState) -> Literal["tools", "human_review", END]:
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        # If the tool call modifies state (not GetGlobalHistory), we might want HITL
        # For simplicity, we interrupt before ANY tool execution in this example, or selectively:
        modifying_tools = {"LogRent", "LogPowerBill", "UpdateMeter", "EditTxn"}
        for tc in last_message.tool_calls:
            if tc["name"] in modifying_tools:
                return "human_review"
        return "tools"
    return END

def execute_tools_node(state: AgentState):
    """Execute tools (bypassing HITL, e.g., for read-only tools)."""
    tool_node = ToolNode(admin_tools)
    return tool_node.invoke(state)

def ask_human_approval(state: AgentState):
    """
    This node simply pauses the graph using the built-in LangGraph interrupt mechanism.
    Before returning, it would realistically send a WhatsApp message to the admin.
    """
    last_message = state["messages"][-1]
    sender_id = state.get("sender_id")

    # Send a message to admin (or dashboard) about pending tool call
    tool_calls_str = json.dumps(last_message.tool_calls, indent=2)
    send_whatsapp_text(sender_id, f"PENDING APPROVAL: I'm about to execute the following actions:\n{tool_calls_str}\n\nRespond with 'approve' to proceed.")

    # LangGraph will pause here until state is updated externally
    return state

# Build Admin Graph
admin_workflow = StateGraph(AgentState)
admin_workflow.add_node("agent", admin_agent_node)
admin_workflow.add_node("human_review", ask_human_approval)
admin_workflow.add_node("tools", ToolNode(admin_tools))

admin_workflow.add_edge(START, "agent")
admin_workflow.add_conditional_edges("agent", should_continue_admin)
admin_workflow.add_edge("human_review", "tools") # After approval, proceed to tools
admin_workflow.add_edge("tools", "agent")

# Use MemorySaver for checkpointing state (necessary for HITL interrupts)
memory = MemorySaver()
admin_graph = admin_workflow.compile(checkpointer=memory, interrupt_before=["tools"])


# --- Tenant Graph ---
tenant_tools = [GetMyLedger]
tenant_llm = llm.bind_tools(tenant_tools)

def tenant_agent_node(state: AgentState):
    messages = state["messages"]
    system_prompt = SystemMessage(content="You are a helpful property management assistant for tenants. Answer queries strictly using the provided tools. Explain ledgers clearly in conversational Hinglish/Hindi. You are read-only and cannot modify data.")
    msg_history = [system_prompt] + messages[-70:]
    response = tenant_llm.invoke(msg_history)
    return {"messages": [response]}

def should_continue_tenant(state: AgentState) -> Literal["tools", END]:
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        return "tools"
    return END

# Build Tenant Graph
tenant_workflow = StateGraph(AgentState)
tenant_workflow.add_node("agent", tenant_agent_node)
tenant_workflow.add_node("tools", ToolNode(tenant_tools))

tenant_workflow.add_edge(START, "agent")
tenant_workflow.add_conditional_edges("agent", should_continue_tenant)
tenant_workflow.add_edge("tools", "agent")

tenant_graph = tenant_workflow.compile(checkpointer=memory)

async def run_admin_agent(sender_id: str, text: str, thread_id: str):
    """Run the admin agent for a given input."""
    config = {"configurable": {"thread_id": thread_id}}

    # Check if graph is paused
    state = admin_graph.get_state(config)

    if state and state.next and "tools" in state.next:
        # We are paused waiting for approval
        if text.strip().lower() == "approve":
            # Resume graph execution
            send_whatsapp_text(sender_id, "Action approved. Executing...")
            result = admin_graph.invoke(None, config=config)

            # Send final response
            final_msg = result["messages"][-1].content
            if final_msg:
                send_whatsapp_text(sender_id, final_msg)

            # Note: At this point, we'd trigger the HF Manim worker if a transaction was logged.
            # (In a full implementation, you'd inspect the executed tool outputs here or in the node)
        else:
            send_whatsapp_text(sender_id, "Action not approved. Please reply 'approve' or start a new query.")
    else:
        # Normal execution
        inputs = {
            "messages": [HumanMessage(content=text)],
            "sender_id": sender_id,
            "tenant_id": 0 # Admin doesn't have a tenant ID
        }

        result = admin_graph.invoke(inputs, config=config)

        # Check if we hit an interrupt
        new_state = admin_graph.get_state(config)
        if new_state.next and "tools" in new_state.next:
            # We hit an interrupt, ask_human_approval node handles the WhatsApp message
            pass
        else:
            # Agent finished without interrupt
            final_msg = result["messages"][-1].content
            if final_msg:
                send_whatsapp_text(sender_id, final_msg)


async def run_tenant_agent(sender_id: str, tenant_id: int, text: str, thread_id: str):
    """Run the read-only tenant agent."""
    config = {"configurable": {"thread_id": thread_id}}

    inputs = {
        "messages": [HumanMessage(content=text)],
        "sender_id": sender_id,
        "tenant_id": tenant_id
    }

    result = tenant_graph.invoke(inputs, config=config)

    final_msg = result["messages"][-1].content
    if final_msg:
        send_whatsapp_text(sender_id, final_msg)
