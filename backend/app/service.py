import json
from datetime import datetime, timezone
from .models import Event


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds") + "Z"


def key_deadline(event: Event, now: datetime):
    """The deadline the dashboard counts down to: the nearest upcoming submission deadline,
    else the nearest upcoming deadline of any kind, else the most recent past one (overdue)."""
    ds = event.deadlines
    if not ds:
        return None
    for pool in ([d for d in ds if d.kind == "submission"], ds):
        upcoming = [d for d in pool if d.due_at >= now]
        if upcoming:
            return min(upcoming, key=lambda d: d.due_at)
    subs = [d for d in ds if d.kind == "submission"] or ds
    return max(subs, key=lambda d: d.due_at)


def progress(event: Event) -> dict:
    total = len(event.checklist)
    done = sum(1 for c in event.checklist if c.done)
    return {"done": done, "total": total, "percent": round(100 * done / total) if total else 0}


def urgency(due: datetime | None, prog: dict, now: datetime) -> str:
    if due is None:
        return "green"
    left = (due - now).total_seconds()
    if left < 0:
        return "overdue"
    if left < 48 * 3600:
        return "red"
    if left < 7 * 24 * 3600:
        return "amber"
    return "green"


def serialize(event: Event, now: datetime | None = None) -> dict:
    now = now or now_utc()
    key = key_deadline(event, now)
    prog = progress(event)
    return {
        "id": event.id,
        "name": event.name,
        "url": event.url,
        "tracks": json.loads(event.tracks or "[]"),
        "prizes": json.loads(event.prizes or "[]"),
        "deadlines": [{"id": d.id, "label": d.label, "kind": d.kind, "due_at": iso(d.due_at)} for d in event.deadlines],
        "checklist": [{"id": c.id, "label": c.label, "done": c.done, "position": c.position} for c in event.checklist],
        "progress": prog,
        "key_deadline": {"label": key.label, "due_at": iso(key.due_at)} if key else None,
        "urgency": urgency(key.due_at if key else None, prog, now),
        "server_time": iso(now),
    }


def sort_events(events: list[Event], now: datetime | None = None) -> list[Event]:
    """Nearest upcoming deadline first; overdue events sink to the bottom."""
    now = now or now_utc()

    def k(e: Event):
        d = key_deadline(e, now)
        if d is None:
            return (2, 0)
        return (0, d.due_at.timestamp()) if d.due_at >= now else (1, -d.due_at.timestamp())

    return sorted(events, key=k)


def ics_for(events: list[Event]) -> str:
    def esc(s): return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HackPilot//EN", "CALSCALE:GREGORIAN"]
    for e in events:
        for d in e.deadlines:
            out += ["BEGIN:VEVENT", f"UID:hp-{e.id}-{d.id}@hackpilot", f"DTSTAMP:{stamp}",
                    f"DTSTART:{d.due_at.strftime('%Y%m%dT%H%M%SZ')}", f"SUMMARY:{esc(e.name)} - {esc(d.label)}",
                    "BEGIN:VALARM", "TRIGGER:-PT24H", "ACTION:DISPLAY", "DESCRIPTION:Deadline in 24 hours", "END:VALARM",
                    "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"
