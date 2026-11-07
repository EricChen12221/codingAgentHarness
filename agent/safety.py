"""All the 'can the model do this?' decisions live here, not in the tools."""
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea"}
MAX_OUTPUT_CHARS = 6000
ALLOWED_COMMANDS = (
    ["pytest"],
    ["python", "-m", "pytest"],
    ["python3", "-m", "pytest"],
    ["python", "-m", "unittest"],
    ["python3", "-m", "unittest"],
    ["npm", "test"],
)


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
    return text[:MAX_OUTPUT_CHARS] + f"\n...[truncated {len(text) - MAX_OUTPUT_CHARS} chars]"


def ask_approval(prompt: str) -> bool:
    return input(f"\n{prompt} [y/N] ").strip().lower() == "y"
