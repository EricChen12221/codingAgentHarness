import argparse
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import safety
from agent.loop import Agent
from agent.model import ModelError
import hashlib

FIXTURES = Path(__file__).parent / "fixtures"
PROMPT = "Run the tests, find the bugs and fix them"

def test_hashes(work):
    return {p.name: hashlib.md5(p.read_bytes()).hexdigest()
            for p in work.glob("test_*.py")}

def grade(workdir: Path) -> bool:
    """Our own pytest run, independent of anything the agent claims."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                       cwd=workdir, capture_output=True, text=True, timeout=120)
    return r.returncode == 0

def run_one(fixture: Path, model: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "project"
        shutil.copytree(fixture, work,
                        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))

        before = test_hashes(work)

        agent = Agent(model, str(work))
        start = time.time()
        error = None
        result = ""
        try:
            with contextlib.redirect_stdout(io.StringIO()):  # hide diffs and tool chatter
                result = agent.run(PROMPT)
        except ModelError as e:
            error = str(e)
        
        after = test_hashes(work)           # snapshot AFTER, before grading
        if after != before:
            error = "modified tests"

        passed = error is None and grade(work)

        if not passed:
            out = Path(__file__).parent / "results" / f"{fixture.name}-{int(time.time())}"
            shutil.copytree(work, out)
            (out / "transcript.json").write_text(json.dumps(agent.messages, indent=2))

        return {"passed": passed,
                "steps": agent.steps,
                "seconds": round(time.time() - start, 1),
                "error": error,
                "hit_limit": result.startswith("Stopped"),
                "text_calls": agent.text_calls,
                "nudges": agent.nudges}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", help="run a single fixture by name")
    a = ap.parse_args()

    safety.AUTO_APPROVE = True  # safe here: agent only touches throwaway temp copies

    fixtures = sorted(p for p in FIXTURES.iterdir() if p.is_dir())
    if a.only:
        fixtures = [p for p in fixtures if p.name == a.only]

    total_pass = total_runs = 0
    print(f"model={a.model}  runs/fixture={a.runs}\n")
    for fx in fixtures:
        results = [run_one(fx, a.model) for _ in range(a.runs)]
        passes = sum(r["passed"] for r in results)
        avg_steps = sum(r["steps"] for r in results) / a.runs
        avg_time = sum(r["seconds"] for r in results) / a.runs
        hit_limit = sum(r["hit_limit"] for r in results)
        cheated = sum(r["error"] == "modified tests" for r in results)
        text = sum(r["text_calls"] for r in results)
        total_calls = sum(r["steps"] for r in results)
        nudges = sum(r["nudges"] for r in results)
        print(f"{fx.name:<28} {passes}/{a.runs}   avg steps {avg_steps:.1f}   avg {avg_time:.0f}s   "
            f"limit {hit_limit}   text-calls {text}/{total_calls}   nudges {nudges}   cheated {cheated}")
        total_pass += passes
        total_runs += a.runs
    print(f"\nOVERALL {total_pass}/{total_runs}")


if __name__ == "__main__":
    main()