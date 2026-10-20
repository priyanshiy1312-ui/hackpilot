"""Optional LLM extraction. Active only when LLM_API_KEY is set; otherwise (or on any error) the rule parser is used."""
import json
import os
import urllib.request

from .parser import extract_event, build_checklist

PROMPT = ("Extract hackathon details from the text. Reply with JSON only: "
          '{"name": str, "url": str, "tracks": [str], "prizes": [str], '
          '"deadlines": [{"label": str, "kind": "submission|registration|results|event|other", "due_at": "ISO-8601 UTC ending in Z"}]}')


def extract_with_llm(text: str) -> dict:
    key = os.getenv("LLM_API_KEY")
    if not key:
        return extract_event(text)
    try:
        body = json.dumps({
            "model": os.getenv("LLM_MODEL", "claude-haiku-4-5"), "max_tokens": 1500,
            "system": PROMPT, "messages": [{"role": "user", "content": text[:8000]}]}).encode()
        req = urllib.request.Request(
            os.getenv("LLM_URL", "https://api.anthropic.com/v1/messages"), data=body,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = json.load(r)["content"][0]["text"]
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        data["checklist"] = build_checklist(text)
        data["method"] = "llm"
        return data
    except Exception:
        return extract_event(text)  # fallback keeps the app working offline
