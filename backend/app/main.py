import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import crud, service
from .database import SessionLocal, get_db, migrate
from .llm import extract_with_llm
from .models import ChecklistItem, Deadline, Event
from .parser import extract_event
from .schemas import ChecklistIn, ChecklistPatch, DeadlineHook, EventIn, ExtractIn, OrderIn, TaskHook, utc_naive
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    if os.getenv("SEED_DATA", "1") == "1":
        with SessionLocal() as db:
            seed(db)
    yield


app = FastAPI(title="HackPilot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def get_event_or_404(db: Session, event_id: int) -> Event:
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, f"Event {event_id} not found")
    return ev


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/events")
def list_events(db: Session = Depends(get_db)):
    now = service.now_utc()
    return [service.serialize(e, now) for e in service.sort_events(db.query(Event).all(), now)]


@app.post("/api/extract")
def extract(body: ExtractIn):
    result = extract_with_llm(body.text) if body.use_llm else extract_event(body.text)
    if not result["deadlines"]:
        result["warning"] = "No dates were found. Add at least one deadline by hand before saving."
    return result


@app.post("/api/events", status_code=201)
def create(body: EventIn, db: Session = Depends(get_db)):
    return service.serialize(crud.create_event(db, body))


@app.get("/api/events/{event_id}")
def read(event_id: int, db: Session = Depends(get_db)):
    return service.serialize(get_event_or_404(db, event_id))


@app.put("/api/events/{event_id}")
def update(event_id: int, body: EventIn, db: Session = Depends(get_db)):
    ev = crud.apply_event(db, get_event_or_404(db, event_id), body, keep_checklist=True)
    db.commit()
    return service.serialize(ev)


@app.delete("/api/events/{event_id}", status_code=204)
def delete(event_id: int, db: Session = Depends(get_db)):
    db.delete(get_event_or_404(db, event_id))
    db.commit()


@app.post("/api/events/{event_id}/checklist", status_code=201)
def add_item(event_id: int, body: ChecklistIn, db: Session = Depends(get_db)):
    ev = get_event_or_404(db, event_id)
    ev.checklist.append(ChecklistItem(label=body.label.strip(), position=crud.next_position(ev)))
    db.commit()
    return service.serialize(ev)


@app.put("/api/events/{event_id}/checklist/order")
def order_items(event_id: int, body: OrderIn, db: Session = Depends(get_db)):
    ev = get_event_or_404(db, event_id)
    if not crud.reorder(ev, body.ids):
        raise HTTPException(422, "ids must list every checklist item of this event exactly once")
    db.commit()
    db.refresh(ev)
    return service.serialize(ev)


@app.patch("/api/checklist/{item_id}")
def patch_item(item_id: int, body: ChecklistPatch, db: Session = Depends(get_db)):
    item = db.get(ChecklistItem, item_id)
    if not item:
        raise HTTPException(404, "Checklist item not found")
    if body.done is not None:
        item.done = body.done
    if body.label is not None:
        item.label = body.label.strip()
    db.commit()
    return service.serialize(get_event_or_404(db, item.event_id))


@app.delete("/api/checklist/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ChecklistItem, item_id)
    if not item:
        raise HTTPException(404, "Checklist item not found")
    event_id = item.event_id
    db.delete(item)
    db.commit()
    return service.serialize(get_event_or_404(db, event_id))


def check_secret(given: str):
    if not hmac.compare_digest(given.encode(), os.getenv("WEBHOOK_SECRET", "dev-secret").encode()):
        raise HTTPException(401, "Bad or missing X-Webhook-Secret header")


@app.post("/api/webhook/tasks")
def webhook_task(body: TaskHook, x_webhook_secret: str = Header(default=""), db: Session = Depends(get_db)):
    """Bot endpoint: create or update one checklist task, matched by external_id."""
    check_secret(x_webhook_secret)
    ev = get_event_or_404(db, body.event_id)
    item = db.query(ChecklistItem).filter_by(external_id=body.external_id).first()
    if item and item.event_id != ev.id:
        raise HTTPException(409, "external_id already belongs to another event")
    created = item is None
    if created:
        if not body.label:
            raise HTTPException(422, "label is required to create a task")
        item = ChecklistItem(label=body.label.strip(), external_id=body.external_id, position=crud.next_position(ev))
        ev.checklist.append(item)
    if body.label is not None:
        item.label = body.label.strip()
    if body.done is not None:
        item.done = body.done
    db.commit()
    return {"created": created, "event": service.serialize(ev)}


@app.post("/api/webhook/deadlines")
def webhook_deadline(body: DeadlineHook, x_webhook_secret: str = Header(default=""), db: Session = Depends(get_db)):
    """Bot endpoint: create or move one deadline, matched by external_id. The live countdown follows it."""
    check_secret(x_webhook_secret)
    ev = get_event_or_404(db, body.event_id)
    d = db.query(Deadline).filter_by(external_id=body.external_id).first()
    if d and d.event_id != ev.id:
        raise HTTPException(409, "external_id already belongs to another event")
    created = d is None
    if created:
        if not (body.label and body.due_at):
            raise HTTPException(422, "label and due_at are required to create a deadline")
        d = Deadline(label=body.label.strip(), kind=body.kind or "other", due_at=utc_naive(body.due_at), external_id=body.external_id)
        ev.deadlines.append(d)
    else:
        if body.label is not None: d.label = body.label.strip()
        if body.kind is not None: d.kind = body.kind
        if body.due_at is not None: d.due_at = utc_naive(body.due_at)
    db.commit()
    db.refresh(ev)
    return {"created": created, "event": service.serialize(ev)}


@app.get("/api/ics")
def ics_all(db: Session = Depends(get_db)):
    return Response(service.ics_for(db.query(Event).all()), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="hackpilot.ics"'})


@app.get("/api/events/{event_id}/ics")
def ics_one(event_id: int, db: Session = Depends(get_db)):
    ev = get_event_or_404(db, event_id)
    return Response(service.ics_for([ev]), media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="hackpilot-{ev.id}.ics"'})


# Serve the built frontend if present (optional single-process mode)
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Unknown API route")
        return FileResponse(DIST / "index.html")
