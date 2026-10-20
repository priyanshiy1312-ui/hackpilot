"""Rule-based extractor: pulls event name, deadlines, tracks and prizes out of pasted text.

No external services. An optional LLM extractor lives in llm.py and falls back here.
"""
import os
import re
from datetime import datetime, timedelta, timezone

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
TZ_OFFSETS = {"IST": 330, "UTC": 0, "GMT": 0, "EST": -300, "EDT": -240, "CST": -360,
              "CDT": -300, "PST": -480, "PDT": -420, "CET": 60, "SGT": 480, "JST": 540}

MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
TIME = r"(?:\s*(?:at|,|@|-)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?:\s*(IST|UTC|GMT|EST|EDT|CST|CDT|PST|PDT|CET|SGT|JST))?)?"
DATE_PATTERNS = [
    # Oct 24, 2026 [at 11:59 PM IST]
    (re.compile(MON + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})" + TIME, re.I), "mdy"),
    # 24 October 2026 [11:59 PM]
    (re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+" + MON + r"\.?,?\s+(\d{4})" + TIME, re.I), "dmy"),
    # 2026-10-24 [23:59]
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})" + TIME, re.I), "iso"),
]

KINDS = [
    ("submission", r"submi|deadline|due\b|final|project\s+upload|code\s+freeze"),
    ("registration", r"regist|sign[\s-]?up|apply|applications?"),
    ("results", r"result|winner|announce|award|demo\s+day|judging|shortlist"),
    ("event", r"start|begin|kick[\s-]?off|open|end[s]?\b|close"),
]
CLOCK_LINE = re.compile(r"\d{1,2}:\d{2}")


def _default_offset() -> int:
    raw = os.getenv("DEFAULT_TZ_OFFSET_MIN", "330")  # IST
    try:
        return int(raw)
    except ValueError:
        return 330


def _to_utc(y, mo, d, hh, mm, ampm, tz) -> datetime | None:
    try:
        hh = int(hh) if hh is not None else 23
        mm = int(mm) if mm is not None else (59 if hh == 23 else 0)
        if ampm:
            hh = hh % 12 + (12 if ampm.lower() == "pm" else 0)
        if hh > 23 or mm > 59:
            return None
        local = datetime(int(y), int(mo), int(d), hh, mm)
    except ValueError:
        return None
    offset = TZ_OFFSETS.get((tz or "").upper(), _default_offset())
    return local - timedelta(minutes=offset)


def find_dates(line: str) -> list[datetime]:
    found, taken = [], []
    for pat, order in DATE_PATTERNS:
        for m in pat.finditer(line):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            g = m.groups()
            if order == "mdy":
                mo, d, y, hh, mm, ap, tz = MONTHS[g[0][:3].lower()], g[1], g[2], g[3], g[4], g[5], g[6]
            elif order == "dmy":
                d, mo, y, hh, mm, ap, tz = g[0], MONTHS[g[1][:3].lower()], g[2], g[3], g[4], g[5], g[6]
            else:
                y, mo, d, hh, mm, ap, tz = g[0], g[1], g[2], g[3], g[4], g[5], g[6]
            if hh is not None and mm is None and ap is None and not CLOCK_LINE.search(m.group(0)):
                hh = None  # a bare number after a date is not a time
            dt = _to_utc(y, mo, d, hh, mm, ap, tz)
            if dt:
                found.append(dt)
                taken.append((m.start(), m.end()))
    return found


def classify(label: str) -> str:
    for kind, rx in KINDS:
        if re.search(rx, label, re.I):
            return kind
    return "other"


def _clean_label(line: str) -> str:
    # strip the date text so the label reads as a plain description
    text = line
    for pat, _ in DATE_PATTERNS:
        text = pat.sub("", text)
    text = re.sub(r"^[\s\-•*\d.)]+", "", text)
    text = re.sub(r"[\s:\-–—|,@]+$", "", text).strip(" :-–—|")
    return text[:120] or "Deadline"


def extract_name(lines: list[str]) -> str:
    for ln in lines:
        m = re.match(r"(?:hackathon|event|title|name)\s*[:\-]\s*(.+)", ln, re.I)
        if m:
            return m.group(1).strip()[:200]
    for ln in lines:
        if len(ln) <= 120 and not find_dates(ln):
            return ln.strip("#*- ").strip()
    return "Untitled hackathon"


def extract_tracks(lines: list[str]) -> list[str]:
    tracks = []
    for ln in lines:
        m = re.match(r"^\W*(?:track\s*(?:\d+|[a-z])?\s*[:\-–]\s*)(.+)", ln, re.I)
        if m:
            tracks.append(m.group(1).strip()[:100])
    return list(dict.fromkeys(tracks))


def extract_prizes(lines: list[str]) -> list[str]:
    prizes = []
    for ln in lines:
        if re.search(r"[$₹€£]\s?\d|\b(?:rs\.?|inr|usd)\s?\d|\bprize|\bcash\b|\bwinner\s*[:\-]", ln, re.I):
            prizes.append(ln.strip("•*- ").strip()[:140])
    return list(dict.fromkeys(prizes))[:8]


def extract_deadlines(lines: list[str]) -> list[dict]:
    deadlines = []
    for ln in lines:
        for dt in find_dates(ln):
            label = _clean_label(ln)
            deadlines.append({"label": label, "kind": classify(label), "due_at": dt.isoformat() + "Z"})
    uniq = {(d["label"], d["due_at"]): d for d in deadlines}
    return sorted(uniq.values(), key=lambda d: d["due_at"])


def build_checklist(text: str) -> list[str]:
    t = text.lower()
    items = ["Create the GitHub repository", "Write a README with setup steps", "Build a working prototype"]
    if re.search(r"video|demo", t):
        items.append("Record the demo video")
    if re.search(r"deck|slides|presentation|pitch|ppt", t):
        items.append("Prepare the presentation deck")
    if re.search(r"\bzip\b", t):
        items.append("Package the project as a zip file")
    if re.search(r"devpost|submission form|submit", t):
        items.append("Fill in the submission form")
    items.append("Submit before the final deadline")
    return list(dict.fromkeys(items))


def extract_event(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    url = re.search(r"https?://\S+", text)
    return {
        "name": extract_name(lines),
        "url": url.group(0).rstrip(".,)") if url else "",
        "tracks": extract_tracks(lines),
        "prizes": extract_prizes(lines),
        "deadlines": extract_deadlines(lines),
        "checklist": build_checklist(text),
        "method": "rules",
    }
