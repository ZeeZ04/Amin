"""Coding check for the screen overlay: the model alone, with no retrieval.

    uv run python scripts/code_eval.py edge-2-q8 > out.jsonl
    uv run python scripts/code_eval.py ollama:qwen3.6:27b > out.jsonl

`hit` only flags a keyword from expect_any. Usefulness is graded by hand.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

SYSTEM = "You are a coding assistant. Answer briefly and correctly. Give the fix or the code."
ITEMS = Path("data/eval/eval_code.jsonl")


def post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def ask(model: str, question: str) -> str:
    if model.startswith("ollama:"):  # /api/generate: Ollama's OpenAI endpoint ignores think=false (E33)
        body = {"model": model[7:], "system": SYSTEM, "prompt": question, "stream": False, "think": False,
                "options": {"num_predict": 500, "temperature": 0}}
        return post("http://localhost:11434/api/generate", body)["response"]
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    body = {"messages": messages, "max_tokens": 500, "temperature": 0}
    return post("http://localhost:8080/v1/chat/completions", body)["choices"][0]["message"]["content"]


for line in ITEMS.read_text().splitlines():
    item = json.loads(line)
    start = time.time()
    answer = ask(sys.argv[1], item["question"])
    hit = any(k.lower() in answer.lower() for k in item["expect_any"])
    print(json.dumps({"id": item["id"], "kind": item["kind"], "hit": hit, "secs": round(time.time() - start, 1),
                      "answer": answer}, ensure_ascii=False), flush=True)
