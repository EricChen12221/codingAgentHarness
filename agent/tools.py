"""Tool implementations + JSON schemas the model sees."""
import difflib
import re
import shlex
import subprocess
import sys
from pathlib import Path

from .safety import (SKIP_DIRS, ask_approval, command_allowed,
                     resolve_in_workspace, truncate)


class Tools:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def list_files(self, path: str = ".") -> str:
        base = resolve_in_workspace(self.root, path)
        out = []
        for p in sorted(base.rglob("*")):
            if any(part in SKIP_DIRS for part in p.parts) or p.is_dir():
                continue
            out.append(str(p.relative_to(self.root)))
            if len(out) >= 200:
                out.append("...[more files not shown]")
                break
        return "\n".join(out) or "(empty)"

    def read_file(self, path: str, start: int = 1, end: int = 400) -> str:
        p = resolve_in_workspace(self.root, path)
        lines = p.read_text(errors="replace").splitlines()
        chunk = lines[start - 1 : end]
        numbered = [f"{i}: {l}" for i, l in enumerate(chunk, start)]
        return truncate("\n".join(numbered)) or "(empty file)"

    def search_files(self, pattern: str, path: str = ".") -> str:
        base = resolve_in_workspace(self.root, path)
        rx = re.compile(pattern)
        hits = []
        for p in sorted(base.rglob("*")):
            if p.is_dir() or any(part in SKIP_DIRS for part in p.parts):
                continue
            try:
                for n, line in enumerate(p.read_text().splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{p.relative_to(self.root)}:{n}: {line.strip()}")
            except (UnicodeDecodeError, OSError):
                continue
            if len(hits) >= 50:
                break
        return truncate("\n".join(hits)) or "no matches"

    # mutating tools (gated by the human)
    def edit_file(self, path: str, old: str, new: str) -> str:
        p = resolve_in_workspace(self.root, path)
        text = p.read_text()
        if old == new:
            return "ERROR: 'old' and 'new' are identical. This edit changes nothing."
        if text.count(old) != 1:
            close = difflib.get_close_matches(old.strip(), text.splitlines(), n=3, cutoff=0.5)
            hint = "\n".join(close) or "(no similar lines found)"
            return (f"ERROR: 'old' matched {text.count(old)} times; it must match exactly once. "
                    f"Call read_file and copy the text exactly. Similar lines:\n{hint}")
        
        updated = text.replace(old, new)
        diff = "".join(difflib.unified_diff(
            text.splitlines(True), updated.splitlines(True),
            f"a/{path}", f"b/{path}"))
        print("\n" + diff)
        if not ask_approval(f"Apply this edit to {path}?"):
            return "REJECTED by user. Do not retry the same edit; ask what they want."
        p.write_text(updated)
        return f"Edited {path}. Now call run_tests to verify before doing anything else."

    def create_file(self, path: str, content: str) -> str:
        p = resolve_in_workspace(self.root, path)
        if p.exists():
            return "ERROR: file exists. Use edit_file instead."
        print(f"\n--- new file {path} ---\n{content}")
        if not ask_approval(f"Create {path}?"):
            return "REJECTED by user."
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Created {path}."

    def run_tests(self, command: str = "python -m pytest -q") -> str:
        argv = shlex.split(command)
        if not command_allowed(argv):
            return "ERROR: command not on the allowlist."
        if argv[0] in ("python", "python3"):
            argv[0] = sys.executable
        if not ask_approval(f"Run: {command}?"):
            return "REJECTED by user."
        try:
            r = subprocess.run(argv, cwd=self.root, capture_output=True,
                               text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return "ERROR: timed out after 120s."
        return truncate(f"exit code {r.returncode}\n{r.stdout}\n{r.stderr}")

    # dispatch 
    def call(self, name: str, args: dict) -> str:
        fn = getattr(self, name, None)
        if name not in {s["function"]["name"] for s in SCHEMAS} or fn is None:
            return f"ERROR: unknown tool '{name}'."
        try:
            return str(fn(**args))
        except TypeError as e:
            return f"ERROR: bad arguments: {e}"
        except Exception as e:  # tool errors go back to the model, not crash the loop
            return f"ERROR: {type(e).__name__}: {e}"


def _tool(name, desc, props, required=()):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props,
                       "required": list(required)}}}

S = {"type": "string"}
SCHEMAS = [
    _tool("list_files", "List files in the project.", {"path": S}),
    _tool("read_file", "Read a file with line numbers.",
          {"path": S, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path"]),
    _tool("search_files", "Regex search across project files.",
          {"pattern": S, "path": S}, ["pattern"]),
    _tool("edit_file", "Replace one exact snippet in a file. 'old' must appear exactly once. User approves.",
          {"path": S, "old": S, "new": S}, ["path", "old", "new"]),
    _tool("create_file", "Create a new file. User approves.",
          {"path": S, "content": S}, ["path", "content"]),
    _tool("run_tests", "Run the test suite (pytest/unittest/npm test only). User approves.",
          {"command": S}),
]
