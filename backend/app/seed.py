from datetime import timedelta
from sqlalchemy.orm import Session
from .models import Event
from .schemas import EventIn, DeadlineIn
from .crud import create_event
from .service import now_utc

SAMPLES = [
    ("Graph Hacks 2026", "https://graphhacks.example.com", ["Context for AI Agents", "Knowledge Graphs"], ["First place: $2,000"],
     [("Project submission closes", "submission", 2 * 24 - 5), ("Winners announced", "results", 6 * 24)], 3),
    ("Bharat Builds Tour", "https://bharatbuilds.example.com", ["Heat and Water", "Health"], ["Winner: Rs. 50,000 AWS credits"],
     [("Final submission deadline", "submission", 9 * 24), ("Demo day", "results", 12 * 24)], 1),
    ("Open Source Sprint", "", ["Developer Tools"], [],
     [("Registration closes", "registration", 3 * 24), ("Submission deadline", "submission", 26 * 24)], 0),
    ("Campus AI Challenge", "", ["Education", "Accessibility"], ["Prize pool: Rs. 1,00,000"],
     [("Submission deadline", "submission", -30)], 5),
]
BASE = ["Create the GitHub repository", "Write a README with setup steps", "Build a working prototype",
        "Record the demo video", "Prepare the presentation deck", "Submit before the final deadline"]


def seed(db: Session):
    if db.query(Event).count():
        return
    now = now_utc()
    for name, url, tracks, prizes, dls, done in SAMPLES:
        ev = create_event(db, EventIn(
            name=name, url=url, tracks=tracks, prizes=prizes, checklist=BASE,
            deadlines=[DeadlineIn(label=l, kind=k, due_at=now + timedelta(hours=h)) for l, k, h in dls]))
        for item in ev.checklist[:done]:
            item.done = True
        db.commit()
