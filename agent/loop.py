"""The agent loop: model -> tool calls -> results -> model, until it answers."""
from . import model
from .tools import SCHEMAS, Tools

SYSTEM = """You are a careful coding assistant working inside one project directory.
Rules:
- Explore before editing: list_files, search_files, read_file.
- Make small, targeted edits with edit_file. Never guess file contents; read first.
- After changing code, run_tests if tests exist.
- If the user rejects an action, stop and ask what they want instead.
- When done, reply with a short summary and no tool call."""

MAX_STEPS = 12


class Agent:
    def __init__(self, model_name: str, workspace: str):
        self.model_name = model_name
        self.tools = Tools(workspace)
        self.messages = [{"role": "system", "content": SYSTEM}]

    def run(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})
        for _ in range(MAX_STEPS):
            reply = model.chat(self.model_name, self.messages, SCHEMAS)
            self.messages.append(reply)
            calls = reply.get("tool_calls") or []
            if not calls:
                return reply.get("content", "")
            for c in calls:
                name, args = c["function"]["name"], c["function"]["arguments"]
                print(f"  [tool] {name}({args})")
                result = self.tools.call(name, args)
                self.messages.append(
                    {"role": "tool", "tool_name": name, "content": result})
        return "Stopped: hit the step limit."
