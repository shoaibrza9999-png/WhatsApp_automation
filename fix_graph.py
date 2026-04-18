import re

with open("property_bot/graph.py", "r") as f:
    content = f.read()

# Fix memory saver issue
content = content.replace("from langgraph.checkpoint.memory import MemorySaver", "from langgraph.checkpoint.memory import MemorySaver\nfrom langgraph.checkpoint.sqlite import SqliteSaver\nimport sqlite3")
content = content.replace("memory = MemorySaver()", "conn = sqlite3.connect('checkpoints.sqlite', check_same_thread=False)\nmemory = SqliteSaver(conn)")

# Fix missing ToolMessage issue in process_confirmation
fix_code = """
            new_messages.append(ToolMessage(content="Tenant successfully removed.", tool_call_id=data["tool_call_id"]))
            send_whatsapp_text(state["sender_id"], "Confirmed. Tenant removed.")

    else:
        # Cancelled
        for key, data in pending.items():
            new_messages.append(ToolMessage(content="Action cancelled by user.", tool_call_id=data["tool_call_id"]))
        send_whatsapp_text(state["sender_id"], "Action cancelled.")

    # FIX: Ensure all tool calls have a corresponding ToolMessage
    last_message = state["messages"][-2] if len(state["messages"]) >= 2 else None
    if getattr(last_message, 'tool_calls', None):
        handled_tool_ids = [m.tool_call_id for m in new_messages if isinstance(m, ToolMessage)]
        for tc in last_message.tool_calls:
            if tc["id"] not in handled_tool_ids:
                new_messages.append(ToolMessage(content="Tool execution aborted or failed to find tenant.", tool_call_id=tc["id"]))

    return {"messages": new_messages, "pending_tool_call": {}}
"""
content = re.sub(r'            new_messages\.append\(ToolMessage\(content="Tenant successfully removed.", tool_call_id=data\["tool_call_id"\]\)\)\n            send_whatsapp_text\(state\["sender_id"\], "Confirmed. Tenant removed."\)\n            \n    else:\n        # Cancelled\n        for key, data in pending.items\(\):\n            new_messages.append\(ToolMessage\(content="Action cancelled by user.", tool_call_id=data\["tool_call_id"\]\)\)\n        send_whatsapp_text\(state\["sender_id"\], "Action cancelled."\)\n\n    return \{"messages": new_messages, "pending_tool_call": \{\}\}', fix_code, content)

with open("property_bot/graph.py", "w") as f:
    f.write(content)
