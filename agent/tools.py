"""Tool implementations + JSON schemas the model sees."""
import difflib
import re
import shlex
import subprocess
import sys
from pathlib import Path

from .safety import (SKIP_DIRS, ask_approval, command_allowed,
                     resolve_in_workspace, is_protected, truncate)


_LINENO = re.compile(r"^\d+: ")

def _strip_line_numbers(s: str) -> str:
    """Undo the 'N: ' prefixes that read_file adds, if every non-empty line has one."""
    lines = s.split("\n")
    nonempty = [l for l in lines if l.strip()]
    if nonempty and all(_LINENO.match(l) for l in nonempty):
        return "\n".join(_LINENO.sub("", l, count=1) for l in lines)
    return s

class Tools:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.read_since_edit = set()

    def _source_hint(self, output: str) -> str:
        files = []
        for m in re.finditer(r"^([\w./-]+\.py):\d+", output, re.M):
            f = m.group(1)
            if f.startswith("/") or "site-packages" in f or f in files:
                continue
            try:
                if is_protected(self.root, resolve_in_workspace(self.root, f)):
                    continue
            except Exception:
                continue
            files.append(f)
        if not files:
            return ""
        return (f"\nHint: the failing code runs through {', '.join(files)}. "
                "read_file it and fix the bug there. Do not edit the tests.")

    def source_files(self) -> list[str]:
        out = []
        for p in sorted(self.root.rglob("*.py")):
            rel = p.relative_to(self.root)
            if any(part in SKIP_DIRS for part in rel.parts) or is_protected(self.root, p):
                continue
            out.append(str(rel))
        return out

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
        self.read_since_edit.add(str(p))
        chunk = lines[start - 1 : end]
        numbered = [f"{i}: {l}" for i, l in enumerate(chunk, start)]
        return truncate("\n".join(numbered)) or "(empty file)"

    def _grep(self, base, rx):
        hits = []
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(self.root)
            if p.is_dir() or any(part in SKIP_DIRS for part in rel.parts):
                continue
            try:
                for n, line in enumerate(p.read_text().splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{rel}:{n}: {line.strip()}")
            except (UnicodeDecodeError, OSError):
                continue
            if len(hits) >= 50:
                break
        return hits

    def search_files(self, pattern: str, path: str = ".") -> str:
        base = resolve_in_workspace(self.root, path)
        try:
            hits = self._grep(base, re.compile(pattern))
        except re.error:
            hits = []
        if not hits:  # model probably meant a literal string
            hits = self._grep(base, re.compile(re.escape(pattern)))
        return truncate("\n".join(hits)) or f"no matches for {pattern!r} (tried regex and literal)"

    # mutating tools (gated by the human)
    def edit_file(self, path: str, old: str, new: str) -> str:
        p = resolve_in_workspace(self.root, path)
        if is_protected(self.root, p):
            return ("ERROR: test files are read-only. The tests define the correct behavior, so do "
                "not change the test or how it calls the function. Fix the code under test. "
                f"Source files you can edit: {', '.join(self.source_files())}. "
                "read_file one of them, then edit it.")
        if str(p) not in self.read_since_edit:
            return "ERROR: read_file this file first, then retry the edit."

        text = p.read_text()
        if text.count(old) != 1:
            s_old = _strip_line_numbers(old)
            if s_old != old and text.count(s_old) == 1:
                old, new = s_old, _strip_line_numbers(new)

        if old == new:
            return "ERROR: 'old' and 'new' are identical. This edit changes nothing."

        count = text.count(old)
        if count != 1:
            return (f"ERROR: 'old' matched {count} times; it must match exactly once. "
                    "'old' and 'new' should be whole lines including leading indentation.\n"
                    f"Current content of {path} (no line numbers). Copy 'old' exactly from here:\n"
                    f"{truncate(text)}")

        updated = text.replace(old, new)
        if p.suffix == ".py":
            try:
                compile(updated, str(p), "exec")
            except SyntaxError as e:
                return (f"ERROR: this edit would create a syntax error ({e.msg}, line {e.lineno}), "
                        "so the file was NOT changed. 'old' and 'new' must be whole lines including "
                        "their leading spaces. Copy the full original line(s) from read_file.")

        diff = "".join(difflib.unified_diff(
            text.splitlines(True), updated.splitlines(True),
            f"a/{path}", f"b/{path}"))
        print("\n" + diff)
        if not ask_approval(f"Apply this edit to {path}?"):
            return "REJECTED by user. Do not retry the same edit; ask what they want."
        p.write_text(updated)
        numbered = "\n".join(f"{i}: {l}" for i, l in enumerate(updated.splitlines(), 1))
        return (f"Edited {path}. The file now reads exactly as follows, so do not read it again:\n"
            f"{truncate(numbered)}\nNow call run_tests.")

    def create_file(self, path: str, content: str) -> str:
        p = resolve_in_workspace(self.root, path)
        if is_protected(self.root, p):
                    return ("ERROR: test files are read-only. The tests define the correct behavior, so do "
                            "not change the test or how it calls the function. Fix the code under test. "
                            f"Source files you can edit: {', '.join(self.source_files())}. "
                            "read_file one of them, then edit it.")
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
        if "pytest" in argv and not any(a.startswith("--tb") for a in argv):
            argv.append("--tb=short")
        if argv[0] in ("python", "python3"):
            argv[0] = sys.executable
        if not ask_approval(f"Run: {command}?"):
            return "REJECTED by user."
        try:
            r = subprocess.run(argv, cwd=self.root, capture_output=True,
                               text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return "ERROR: timed out after 120s."
        out = truncate(f"exit code {r.returncode}\n{r.stdout}\n{r.stderr}")
        if r.returncode != 0:
            out += self._source_hint(r.stdout)
        return out

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
    _tool("edit_file", "Replace one exact snippet in a file. 'old' and 'new' must be whole lines including leading "
      "indentation. 'old' must appear exactly once. User approves.",
          {"path": S, "old": S, "new": S}, ["path", "old", "new"]),
    _tool("create_file", "Create a new file. User approves.",
          {"path": S, "content": S}, ["path", "content"]),
    _tool("run_tests", "Run the test suite (pytest/unittest/npm test only). User approves.",
          {"command": S}),
]
