# mini-agent

Setup (M1 Mac):
    brew install ollama
    ollama serve            # leave running (or use the menu-bar app)
    ollama pull qwen2.5-coder:7b
    python3 -m venv .venv && source .venv/bin/activate
    pip install pytest
    python main.py

Try:  "Run the tests, find why they fail, and fix it."


BASELINE: 14/25 for qwen2.5-coder:7b
