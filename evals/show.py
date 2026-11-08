import json
import sys
from pathlib import Path

name = sys.argv[1] if len(sys.argv) > 1 else "01_off_by_one"
runs = sorted(Path(__file__).parent.glob(f"results/{name}-*"))
if not runs:
    sys.exit(f"No saved failures for {name}. Check evals/results/")

d = runs[-1]
print("reading", d.name, "\n")
for m in json.loads((d / "transcript.json").read_text()):
    role = m["role"]
    if role == "system":
        continue
    if role == "user":
        print(f"USER: {m['content'][:200]!r}")
    elif role == "tool":
        print(f"  <- {m['content'][:200]!r}")
    elif role == "assistant":
        for c in m.get("tool_calls") or []:
            print(f"-> {c['function']['name']}({c['function']['arguments']})")
        if m.get("content"):
            print(f"   says: {m['content'][:200]!r}")