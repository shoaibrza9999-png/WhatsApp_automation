import os
import json
from typing import Annotated, Literal, TypedDict, Dict, Any
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from tools import log_rent, updatemeter, logpowerbill, deletetransection, balance
from whatsapp import send_whatsapp_interactive, send_whatsapp_text
from db import get_tenant, get_power_rate, get_transaction, insert_transaction, update_tenant, delete_transaction

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
# As requested, exact model name
llm = ChatGroq(model_name="openai/gpt-oss-120b", temperature=0, api_key=GROQ_API_KEY)

admin_tools = [log_rent, updatemeter, logpowerbill, deletetransection, balance]
admin_llm = llm.bind_tools(admin_tools)

class AgentState(MessagesState):
    sender_id: str

def admin_agent_node(state: AgentState):
    messages = state["messages"]
    system_prompt = SystemMessage(content="You are a helpful property management assistant. Use tools to log transactions or answer queries.")
    msg_history = [system_prompt] + messages[-70:]
    response = admin_llm.invoke(msg_history)
    return {"messages": [response]}

def should_continue_admin(state: AgentState) -> Literal["human_review", "tools", END]:
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        modifying_tools = {"log_rent", "updatemeter", "logpowerbill", "deletetransection"}
        for tc in last_message.tool_calls:
            if tc["name"] in modifying_tools:
                return "human_review"
        return "tools"
    return END

def execute_tools_node(state: AgentState):
    tool_node = ToolNode(admin_tools)
    return tool_node.invoke(state)

def ask_human_approval(state: AgentState):
    last_message = state["messages"][-1]
    sender_id = state["sender_id"]

    for tc in last_message.tool_calls:
        name = tc["name"]
        args = tc["args"]
        approval_text = ""

        if name == "log_rent":
            tenant = get_tenant(args["house_no"], args["room_no"])
            if not tenant:
                send_whatsapp_text(sender_id, "Tenant not found for HITL.")
                return state

            approval_text = (
                f"Name: {tenant['name']}\n"
                f"Rent per month: {tenant['rent']}\n"
                f"Filling: {args['amount']}\n"
                f"AI Note: {args.get('note', '')}"
            )

        elif name == "updatemeter":
            tenant = get_tenant(args["house_no"], args["room_no"])
            if not tenant:
                send_whatsapp_text(sender_id, "Tenant not found for HITL.")
                return state

            last_reading = tenant['last_electricity_reading']
            current_reading = args['current_reading']
            cost_per_unit = get_power_rate()
            total_cost = (current_reading - last_reading) * cost_per_unit

            approval_text = (
                f"Name: {tenant['name']}\n"
                f"Last reading: {last_reading}\n"
                f"Current reading: {current_reading}\n"
                f"Total cost of this month: {total_cost}\n"
                f"AI Note: {args.get('note', '')}"
            )

        elif name == "logpowerbill":
            tenant = get_tenant(args["house_no"], args["room_no"])
            if not tenant:
                send_whatsapp_text(sender_id, "Tenant not found for HITL.")
                return state

            prev_pending = tenant['pending_electricity']
            approval_text = f"Name: {tenant['name']}\n"
            if prev_pending > 0:
                approval_text += f"Previous pending (not paid last): {prev_pending}\n"
            approval_text += (
                f"Filling: {args['amount']}\n"
                f"AI Note: {args.get('note', '')}"
            )

        elif name == "deletetransection":
            txn = get_transaction(args["txn_id"])
            if not txn:
                send_whatsapp_text(sender_id, "Transaction not found.")
                return state

            approval_text = f"Details: {txn['type']} of {txn['amount']} for Room {txn['room_no']}"

        # Send interactive button message
        buttons = [
            {"id": "approve", "title": "Approve"},
            {"id": "reject", "title": "Reject"}
        ]

        send_whatsapp_interactive(
            sender_id,
            "Action Required",
            approval_text,
            "Reply with Note to approve, or Reject.",
            buttons
        )

    return state

# Node that executes AFTER human review
def process_approved_action(state: AgentState):
    messages = state["messages"]
    # The last message is the HumanMessage containing the approval/rejection from the webhook
    admin_reply = messages[-1].content
    # The tool call we are waiting on is in the AIMessage just before it
    ai_msg = messages[-2]

    if "reject" in admin_reply.lower() or admin_reply == "No":
        # Create a mock tool response saying it was rejected
        tool_responses = []
        for tc in ai_msg.tool_calls:
            tool_responses.append(ToolMessage(content="Action Rejected by Admin.", tool_call_id=tc["id"]))
        return {"messages": tool_responses}

    # If approved
    admin_note = admin_reply if admin_reply.lower() != "approve" else ""
    tool_responses = []

    for tc in ai_msg.tool_calls:
        name = tc["name"]
        args = tc["args"]
        res_str = ""

        if name == "log_rent":
            tenant = get_tenant(args["house_no"], args["room_no"])
            final_note = admin_note if admin_note else args.get("note", "")
            insert_transaction(tenant["tenant_id"], "rent", args["amount"], final_note)

            # Decrease pending rent
            update_tenant(args["house_no"], args["room_no"], pending_rent=tenant["pending_rent"] - args["amount"])

            send_whatsapp_text(tenant["phone_number"], f"Payment Received: {args['amount']} for Rent.")
            res_str = "Rent logged successfully."

        elif name == "updatemeter":
            tenant = get_tenant(args["house_no"], args["room_no"])
            last_reading = tenant['last_electricity_reading']
            current_reading = args['current_reading']
            cost_per_unit = get_power_rate()
            total_cost = (current_reading - last_reading) * cost_per_unit

            update_tenant(args["house_no"], args["room_no"], last_electricity_reading=current_reading, pending_electricity=tenant['pending_electricity'] + total_cost)
            res_str = "Meter updated successfully."

        elif name == "logpowerbill":
            tenant = get_tenant(args["house_no"], args["room_no"])
            final_note = admin_note if admin_note else args.get("note", "")
            insert_transaction(tenant["tenant_id"], "electricity", args["amount"], final_note)

            update_tenant(args["house_no"], args["room_no"], pending_electricity=tenant['pending_electricity'] - args["amount"])
            send_whatsapp_text(tenant["phone_number"], f"Payment Received: {args['amount']} for Electricity.")
            res_str = "Power bill logged successfully."

        elif name == "deletetransection":
            delete_transaction(args["txn_id"])
            res_str = "Transaction deleted."

        tool_responses.append(ToolMessage(content=res_str, tool_call_id=tc["id"]))

    return {"messages": tool_responses}


admin_workflow = StateGraph(AgentState)
admin_workflow.add_node("agent", admin_agent_node)
admin_workflow.add_node("human_review", ask_human_approval)
admin_workflow.add_node("process_approved", process_approved_action)
admin_workflow.add_node("tools", ToolNode(admin_tools))

admin_workflow.add_edge(START, "agent")
admin_workflow.add_conditional_edges("agent", should_continue_admin)
admin_workflow.add_edge("human_review", END) # Pauses execution, we'll resume manually
admin_workflow.add_edge("process_approved", "agent")
admin_workflow.add_edge("tools", "agent")

memory = MemorySaver()
admin_graph = admin_workflow.compile(checkpointer=memory)

async def run_admin_agent(sender_id: str, text: str, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state = admin_graph.get_state(config)

    # Check if we are waiting for human review.
    # If the last message was an AIMessage with a tool call that triggers HITL, we are waiting for approval.
    if state and state.values and len(state.values["messages"]) > 0:
        last_msg = state.values["messages"][-1]
        if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
            # We are in a paused state. User reply is the approval/rejection.
            inputs = {
                "messages": [HumanMessage(content=text)],
                "sender_id": sender_id
            }
            # Manually trigger process_approved
            admin_graph.update_state(config, inputs)
            result = admin_graph.invoke(None, config=config)

            # The agent will process the tool responses and generate a final text
            final_msg = result["messages"][-1].content
            if final_msg:
                send_whatsapp_text(sender_id, final_msg)
            return

    # Normal execution
    inputs = {
        "messages": [HumanMessage(content=text)],
        "sender_id": sender_id
    }

    result = admin_graph.invoke(inputs, config=config)
    final_msg = result["messages"][-1].content
    if final_msg:
        send_whatsapp_text(sender_id, final_msg)
