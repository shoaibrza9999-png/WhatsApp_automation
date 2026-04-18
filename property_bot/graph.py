import os
import json
from typing import Annotated, Literal, TypedDict, Dict, Any, Sequence
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from tools import add_tenant, electricity_increase, fill_rent, fill_electricity, remove_tenant
from db import get_tenant_by_room, update_tenant_balances, log_transaction, archive_tenant
from whatsapp import send_whatsapp_text

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0, api_key=GROQ_API_KEY)

tools = [add_tenant, electricity_increase, fill_rent, fill_electricity, remove_tenant]
llm_with_tools = llm.bind_tools(tools)

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    pending_tool_call: Dict[str, Any]
    tenant_context: str
    sender_id: str

def agent_node(state: AgentState):
    messages = state["messages"]
    tenant_context = state.get("tenant_context", "")

    system_prompt = f"""You are 'PropManage AI', an elite property management assistant communicating exclusively with the Property Owner.
Your job is to parse the Owner's commands,

TONE & BEHAVIOR:
- Concise, subservient, and highly accurate.
- If the Owner provides incomplete data (e.g., "Add 500 to room 2" but doesn't specify which house or if it's rent/electricity), you MUST ask the Owner for clarification before calling a tool.

TRANSACTION HISTORY CONTEXT:
If the Owner asks about a tenant's status, use the provided transaction history markdown table to answer them.
[System Note: Backend will inject the markdown table here dynamically based on the active conversation context]
{tenant_context}
"""

    msg_history = [SystemMessage(content=system_prompt)] + list(messages)
    response = llm_with_tools.invoke(msg_history)
    return {"messages": [response]}

def should_continue(state: AgentState) -> Literal["tools", "ask_confirmation", END]:
    messages = state["messages"]
    last_message = messages[-1]

    if getattr(last_message, 'tool_calls', None):
        for tc in last_message.tool_calls:
            if tc["name"] in ["electricity_increase", "remove_tenant"]:
                return "ask_confirmation"
        return "tools"
    return END

def tools_node(state: AgentState):
    tool_node = ToolNode(tools)
    return tool_node.invoke(state)

def ask_confirmation_node(state: AgentState):
    last_message = state["messages"][-1]
    sender_id = state.get("sender_id", "")

    pending_calls = {}
    for tc in last_message.tool_calls:
        if tc["name"] == "electricity_increase":
            args = tc["args"]
            house_no = args.get("house_no")
            room_no = args.get("room_no")
            current_unit = float(args.get("current_unit", 0))

            tenant = get_tenant_by_room(house_no, room_no)
            if tenant:
                last_reading = float(tenant.get("last_meter_reading", 0))
                units_consumed = current_unit - last_reading
                amount_due = units_consumed * 7

                msg = f"You are about to charge House {house_no} Room {room_no} for Rs{amount_due} ( {units_consumed} units). Reply YES to confirm or NO to cancel."
                send_whatsapp_text(sender_id, msg)

                pending_calls["electricity_increase"] = {
                    "tool_call_id": tc["id"],
                    "tenant_id": tenant["id"],
                    "phone_number": tenant["phone_number"],
                    "amount_due": amount_due,
                    "units_consumed": units_consumed,
                    "current_unit": current_unit
                }
            else:
                send_whatsapp_text(sender_id, f"Could not find tenant in House {house_no} Room {room_no}.")

        elif tc["name"] == "remove_tenant":
            args = tc["args"]
            house_no = args.get("house_no")
            room_no = args.get("room_no")

            tenant = get_tenant_by_room(house_no, room_no)
            if tenant:
                rent_bal = tenant.get("rent_balance", 0)
                elec_bal = tenant.get("electricity_balance", 0)
                msg = f"You are about to remove tenant from House {house_no} Room {room_no}. Balances - Rent: {rent_bal}, Elec: {elec_bal}. Reply YES to confirm or NO to cancel."
                send_whatsapp_text(sender_id, msg)

                pending_calls["remove_tenant"] = {
                    "tool_call_id": tc["id"],
                    "tenant_id": tenant["id"],
                    "phone_number": tenant["phone_number"],
                    "rent_balance": rent_bal,
                    "electricity_balance": elec_bal
                }
            else:
                send_whatsapp_text(sender_id, f"Could not find tenant in House {house_no} Room {room_no}.")

    return {"pending_tool_call": pending_calls}

def process_confirmation(state: AgentState):
    """Called after HITL interrupt if user replies YES/NO."""
    pending = state.get("pending_tool_call", {})
    messages = list(state["messages"])

    last_human_msg = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if not last_human_msg:
        return state

    reply = last_human_msg.content.strip().lower()

    new_messages = []

    if reply == "yes":
        if "electricity_increase" in pending:
            data = pending["electricity_increase"]
            tenant_id = data["tenant_id"]
            amount_due = data["amount_due"]
            units = data["units_consumed"]
            current_unit = data["current_unit"]

            # Update DB
            import db
            t = db.supabase.table("tenants").select("electricity_balance").eq("id", tenant_id).execute()
            if t.data:
                curr_bal = float(t.data[0].get("electricity_balance", 0))
                db.supabase.table("tenants").update({
                    "electricity_balance": curr_bal + amount_due,
                    "last_meter_reading": current_unit
                }).eq("id", tenant_id).execute()

            log_transaction(tenant_id, "ELEC_CHARGE", amount_due, f"Meter reading updated. {units} units consumed.")
            send_whatsapp_text(data["phone_number"], f"Your new electricity bill is Rs{amount_due} for {units} units.")

            new_messages.append(ToolMessage(content=f"Successfully charged {amount_due} for {units} units.", tool_call_id=data["tool_call_id"]))
            send_whatsapp_text(state["sender_id"], f"Confirmed. Charged Rs{amount_due}.")

        elif "remove_tenant" in pending:
            data = pending["remove_tenant"]
            tenant_id = data["tenant_id"]
            archive_tenant(tenant_id)

            summary = f"Your tenancy has ended. Final balances - Rent: {data['rent_balance']}, Electricity: {data['electricity_balance']}"
            send_whatsapp_text(data["phone_number"], summary)

            new_messages.append(ToolMessage(content="Tenant successfully removed.", tool_call_id=data["tool_call_id"]))
            send_whatsapp_text(state["sender_id"], "Confirmed. Tenant removed.")

    else:
        # Cancelled
        for key, data in pending.items():
            new_messages.append(ToolMessage(content="Action cancelled by user.", tool_call_id=data["tool_call_id"]))
        send_whatsapp_text(state["sender_id"], "Action cancelled.")

    return {"messages": new_messages, "pending_tool_call": {}}

# Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)
workflow.add_node("ask_confirmation", ask_confirmation_node)
workflow.add_node("process_confirmation", process_confirmation)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")
workflow.add_edge("ask_confirmation", "process_confirmation")  # Edge added
workflow.add_edge("process_confirmation", "agent")

memory = MemorySaver()
# Interrupt before processing the confirmation to wait for human input
admin_graph = workflow.compile(checkpointer=memory, interrupt_before=["process_confirmation"])

async def run_admin_agent(sender_id: str, text: str, thread_id: str, tenant_context: str = ""):
    config = {"configurable": {"thread_id": thread_id}}

    state = admin_graph.get_state(config)

    if state and state.next and "process_confirmation" in state.next:
        # We are paused, waiting for YES/NO from user
        admin_graph.update_state(config, {"messages": [HumanMessage(content=text)]}, as_node="ask_confirmation")

        # Resume the graph from process_confirmation
        result = admin_graph.invoke(None, config=config)

        final_msg = result["messages"][-1]
        if isinstance(final_msg, AIMessage) and final_msg.content:
            send_whatsapp_text(sender_id, final_msg.content)

    else:
        # Normal execution
        inputs = {
            "messages": [HumanMessage(content=text)],
            "sender_id": sender_id,
            "tenant_context": tenant_context
        }

        result = admin_graph.invoke(inputs, config=config)

        new_state = admin_graph.get_state(config)
        if new_state.next and "process_confirmation" in new_state.next:
            # We hit an interrupt, the ask_confirmation node already sent the message
            pass
        else:
            final_msg = result["messages"][-1]
            if isinstance(final_msg, AIMessage) and final_msg.content:
                send_whatsapp_text(sender_id, final_msg.content)

