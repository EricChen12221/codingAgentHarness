"""All the 'can the model do this?' decisions live here, not in the tools."""
from pathlib import Path
from fnmatch import fnmatch

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".pytest_cache"}
MAX_OUTPUT_CHARS = 6000
AUTO_APPROVE = False
ALLOWED_COMMANDS = (
    ["pytest"],
    ["python", "-m", "pytest"],
    ["python3", "-m", "pytest"],
    ["python", "-m", "unittest"],
    ["python3", "-m", "unittest"],
    ["npm", "test"],
)


def is_protected(root: Path, p: Path) -> bool:
    rel = p.relative_to(root)
    return (any(part in ("tests", "test") for part in rel.parts[:-1])
            or fnmatch(rel.name, "test_*.py")
            or fnmatch(rel.name, "*_test.py")
            or rel.name == "conftest.py")

def resolve_in_workspace(root: Path, rel: str) -> Path:
    """Resolve a model-supplied path; refuse anything that escapes the workspace."""
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise PermissionError(f"Path escapes workspace: {rel}")
    return p


def command_allowed(argv: list[str]) -> bool:
    return any(argv[: len(a)] == a for a in ALLOWED_COMMANDS)


def truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    half = MAX_OUTPUT_CHARS // 2
    return (text[:half]
            + f"\n...[truncated {len(text) - MAX_OUTPUT_CHARS} chars]...\n"
            + text[-half:])


def ask_approval(prompt: str) -> bool:
    if AUTO_APPROVE:
        return True
    return input(f"\n{prompt} [y/N] ").strip().lower() == "y"
