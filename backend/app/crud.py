import json
from sqlalchemy.orm import Session
from .models import Event, Deadline, ChecklistItem
from .schemas import EventIn


def apply_event(db: Session, ev: Event, data: EventIn, keep_checklist: bool = False):
    ev.name, ev.url = data.name.strip(), data.url.strip()
    ev.tracks, ev.prizes = json.dumps(data.tracks), json.dumps(data.prizes)
    ev.deadlines.clear()
    for d in data.deadlines:
        ev.deadlines.append(Deadline(label=d.label.strip(), kind=d.kind, due_at=d.due_at))
    if not keep_checklist:
        ev.checklist.clear()
        for i, label in enumerate(data.checklist):
            ev.checklist.append(ChecklistItem(label=label.strip(), position=i))
    return ev


def create_event(db: Session, data: EventIn) -> Event:
    ev = apply_event(db, Event(), data)
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def next_position(ev: Event) -> int:
    return max((c.position for c in ev.checklist), default=-1) + 1


def reorder(ev: Event, ids: list[int]) -> bool:
    existing = {c.id: c for c in ev.checklist}
    if set(ids) != set(existing):
        return False
    for pos, cid in enumerate(ids):
        existing[cid].position = pos
    return True
