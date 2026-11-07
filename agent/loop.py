"""The agent loop: model -> tool calls -> results -> model, until it answers."""
from . import model
from .tools import SCHEMAS, Tools
import json

SYSTEM = """You are a careful coding assistant working inside one project directory.
Rules:
- ALWAYS call read_file on a file immediately before editing it. Never edit from memory.
- In edit_file, copy ‘old’ exactly from read_file output, without the line-number prefix.
- Always use the tool-calling mechanism. Never write tool calls as JSON in your message.
- Explore before editing: list_files, search_files, read_file.
- Make small, targeted edits with edit_file. Never guess file contents; read first.
- After changing code, run_tests if tests exist.
- If the user rejects an action, stop and ask what they want instead.
- When done, reply with a short summary and no tool call."""

MAX_STEPS = 12
def extract_text_tool_call(content: str):
    """Fallback: find a {"name":..., "arguments":...} object anywhere in the text."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(content):
        if ch != "{":
            continue
        try:
            data, _ = decoder.raw_decode(content[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "name" in data and "arguments" in data:
            return [{"function": {"name": data["name"],
                                  "arguments": data["arguments"] or {}}}]
    return None

class Agent:
    def __init__(self, model_name: str, workspace: str, verbose: bool = False):
        self.model_name = model_name
        self.tools = Tools(workspace)
        self.seen = set()
        self.verbose = verbose
        self.messages = [{"role": "system", "content": SYSTEM}]

    def run(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})
        for _ in range(MAX_STEPS):
            reply = model.chat(self.model_name, self.messages, SCHEMAS)
            self.messages.append(reply)
            calls = reply.get("tool_calls") or extract_text_tool_call(reply.get("content", "")) or []
            if not calls:
                return reply.get("content", "")
            for c in calls:
                name, args = c["function"]["name"], c["function"]["arguments"]
                print(f"  [tool] {name}({args})")

                key = (name, json.dumps(args, sort_keys=True))
                if key in self.seen and name != "run_tests":
                    result = "ERROR: you already made this exact call. Try something different, or read_file first."
                else:
                    self.seen.add(key)
                    result = self.tools.call(name, args)

                if self.verbose:
                    print(f"  [result] {result[:300]}")
                    
                self.messages.append(
                    {"role": "tool", "tool_name": name, "content": result})
        return "Stopped: hit the step limit."
