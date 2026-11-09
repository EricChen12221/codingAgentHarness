import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import safety, model
from agent.loop import Agent
from agent.tools import Tools

safety.AUTO_APPROVE = True


def show(label, result):
    print(f"[{label}]\n{result}\n")


# ---------- 1. tools, no model involved ----------
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "calc.py").write_text("def f():\n    return 1\n")
    (root / "test_calc.py").write_text("from calc import f\n\ndef test_f():\n    assert f() == 2\n")
    t = Tools(str(root))

    show("edit before read -> expect ERROR read_file first",
         t.edit_file("calc.py", "    return 1", "    return 2"))
    show("read", t.read_file("calc.py"))
    show("mismatch -> expect ERROR + file contents",
         t.edit_file("calc.py", "return 99", "return 2"))
    show("syntax guard -> expect ERROR syntax error, file NOT changed",
         t.edit_file("calc.py", "return 1", "try:\n    return 2\nexcept TypeError:\n    return 0"))
    show("good edit -> expect Edited",
         t.edit_file("calc.py", "    return 1", "    return 2"))

    show("protected test file -> expect ERROR read-only ... Source files you can edit: calc.py",
         t.edit_file("test_calc.py", "== 2", "== 1"))

    show("literal search with parens -> expect calc.py:1: def f():",
         t.search_files("def f()"))
    show("run_tests -> expect exit code 0",
         t.run_tests("python -m pytest -q"))


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "calc.py").write_text("def f():\n    return 1 / 0\n")  
    (root / "test_calc.py").write_text("from calc import f\n\ndef test_f():\n    assert f() == 2\n")
    t = Tools(str(root))
    out = t.run_tests("python -m pytest -q")
    show("failing run -> expect output ending with 'Hint: ... calc.py ...' (not test_calc.py)",
         out[-300:])


def fake_chat(model_name, messages, tools):
    if not any(m["role"] == "tool" for m in messages):
        return {"role": "assistant", "content": '{"name": "run_tests", "arguments": {}}'}
    return {"role": "assistant", "content": "Let's proceed with these steps."}

model.chat = fake_chat

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "calc.py").write_text("def f():\n    return 1\n")
    (root / "test_calc.py").write_text("from calc import f\n\ndef test_f():\n    assert f() == 2\n")
    agent = Agent("fake", str(root))
    agent.run("Run the tests, find the bugs and fix them")
    print(f"[loop] nudges={agent.nudges} (expect 3), text_calls={agent.text_calls} (expect 1), "
          f"steps={agent.steps} (expect 1)")