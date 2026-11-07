"""Thin Ollama client. One job: send messages + tool schemas, return the reply."""
import json
import urllib.request
import urllib.error

OLLAMA_URL = "http://localhost:11434/api/chat"


class ModelError(RuntimeError):
    pass


def chat(model: str, messages: list[dict], tools: list[dict]) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 8192},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read())["message"]
    except urllib.error.URLError as e:
        raise ModelError(f"Can't reach Ollama at {OLLAMA_URL}. Is it running? ({e})")
