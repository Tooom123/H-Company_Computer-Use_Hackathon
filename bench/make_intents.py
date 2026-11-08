"""Give every task a user request, the way a person would say it to the assistant (the "intent" signal).

The benchmark tasks name the control ("the "Log in" link"). A user says what they want ("I need to sign in to
my account"). Holo (text only) rewrites each task into such a request, about the goal, in English or French, and
is told not to quote the control's label: otherwise matching the request to the label would be trivially easy.
The original label is kept apart; a check reports how many requests still contain it verbatim.

    set -a; . backend/.env; set +a
    .venv/bin/python bench/make_intents.py --data bench/data-intent
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent" / "src"))
from hcs_agent.grounding import H_MODELS_URL  # noqa: E402

PROMPT = """A person is using a web page titled "{title}". The next thing they need is the {role} labelled "{label}".
Write the request they would say out loud to a computer assistant, in {lang}: one sentence, 6 to 16 words, about
their goal (what they want to achieve), as a real user would phrase it. Do NOT quote the label "{label}" word for
word; use your own words. Answer with the sentence only."""


def ask(http: httpx.Client, model: str, prompt: str) -> str:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 60,
            "chat_template_kwargs": {"enable_thinking": False}}
    import time

    for attempt in range(10):
        r = http.post(f"{H_MODELS_URL}/chat/completions", json=body)
        if r.status_code in (429, 502, 503):
            time.sleep(min(float(r.headers.get("retry-after") or 0) or 2.0 * (attempt + 1), 15))
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip().strip('"').splitlines()[0]
    raise RuntimeError("rate limited")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="bench/data-intent")
    ap.add_argument("--model", default="holo4-35b-a3b")
    a = ap.parse_args()
    path = Path(a.data) / "dataset.json"
    data = json.loads(path.read_text())
    titles = {s["name"]: s.get("title") or s["name"] for s in data["screens"]}
    http = httpx.Client(timeout=60, headers={"Authorization": f"Bearer {os.environ['HAI_API_KEY']}"})
    rnd = random.Random(5)
    langs = {t["id"]: ("French" if rnd.random() < 0.4 else "English") for t in data["tasks"]}

    def one(t):
        role = "link" if " link" in t["instruction"] else "button"
        return t["id"], ask(http, a.model, PROMPT.format(title=titles[t["screen"]], role=role, label=t["label"], lang=langs[t["id"]]))

    with ThreadPoolExecutor(2) as pool:
        got = dict(pool.map(one, data["tasks"]))
    verbatim = 0
    for t in data["tasks"]:
        t["intent"] = got[t["id"]]
        t["intent_lang"] = langs[t["id"]]
        if t["label"] and re.search(re.escape(t["label"].lower()), t["intent"].lower()):
            verbatim += 1
    path.write_text(json.dumps(data, indent=1))
    print(f"{len(got)} requests written; {verbatim} still contain the exact label")
    for t in data["tasks"][:: max(1, len(data["tasks"]) // 8)]:
        print(f"  {t['label'][:28]:28} -> {t['intent']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
