import argparse
from agent.loop import Agent
from agent.model import ModelError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="sandbox")
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    a = ap.parse_args()
    agent = Agent(a.model, a.workspace)
    print(f"mini-agent | model={a.model} | workspace={agent.tools.root}\n(ctrl-d to quit)")
    while True:
        try:
            q = input("\nyou> ").strip()
        except EOFError:
            break
        if not q:
            continue
        try:
            print("\n" + agent.run(q))
        except ModelError as e:
            print(e)


if __name__ == "__main__":
    main()
