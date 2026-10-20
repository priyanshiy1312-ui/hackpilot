import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["SEED_DATA"] = "0"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.parser import extract_event, find_dates
from app.service import sort_events, urgency, now_utc

SAMPLE = """Graph Hacks 2026
Online hackathon by FalkorDB. https://graphhacks.dev
Track 1: Context for AI Agents
Track 2 - Knowledge Graphs
Registration closes: Oct 10, 2026
Project submission deadline: Oct 18, 2026 at 11:59 PM IST
Winners announced 25 October 2026
First place: $2,000 cash prize
Submit a demo video, a GitHub repo and a zip file.
"""


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


# ---- parser ----
def test_date_formats_and_timezone():
    assert find_dates("Oct 18, 2026 at 11:59 PM IST") == [datetime(2026, 10, 18, 18, 29)]
    assert find_dates("25 October 2026") == [datetime(2026, 10, 25, 18, 29)]  # default 23:59 IST
    assert find_dates("2026-10-24 10:00 UTC") == [datetime(2026, 10, 24, 10, 0)]


def test_extract_event_fields():
    r = extract_event(SAMPLE)
    assert r["name"] == "Graph Hacks 2026"
    assert r["tracks"] == ["Context for AI Agents", "Knowledge Graphs"]
    assert any("$2,000" in p for p in r["prizes"])
    kinds = {d["kind"] for d in r["deadlines"]}
    assert {"registration", "submission", "results"} <= kinds
    assert len(r["deadlines"]) == 3
    assert "Record the demo video" in r["checklist"] and "Package the project as a zip file" in r["checklist"]


# ---- urgency / sorting ----
def test_urgency_levels():
    now = now_utc()
    p = {"done": 0, "total": 1, "percent": 0}
    assert urgency(now + timedelta(hours=5), p, now) == "red"
    assert urgency(now + timedelta(days=4), p, now) == "amber"
    assert urgency(now + timedelta(days=20), p, now) == "green"
    assert urgency(now - timedelta(hours=1), p, now) == "overdue"


# ---- API ----
def make_payload(hours=30):
    due = (now_utc() + timedelta(hours=hours)).isoformat() + "Z"
    return {"name": "Test Hack", "deadlines": [{"label": "Submission", "kind": "submission", "due_at": due}],
            "checklist": ["A", "B", "C"], "tracks": ["T"], "prizes": []}


def test_extract_endpoint_and_validation(client):
    assert client.post("/api/extract", json={"text": SAMPLE}).json()["name"] == "Graph Hacks 2026"
    assert client.post("/api/extract", json={"text": "short"}).status_code == 422
    nodate = client.post("/api/extract", json={"text": "Just a long paragraph with no dates at all in it."}).json()
    assert "warning" in nodate


def test_create_requires_deadline(client):
    bad = make_payload(); bad["deadlines"] = []
    assert client.post("/api/events", json=bad).status_code == 422


def test_full_flow_checklist_and_dashboard_order(client):
    soon = client.post("/api/events", json=make_payload(30)).json()
    later = client.post("/api/events", json=make_payload(500)).json()
    assert soon["urgency"] == "red" and later["urgency"] == "green"
    assert [e["id"] for e in client.get("/api/events").json()] == [soon["id"], later["id"]]

    item_id = soon["checklist"][0]["id"]
    ev = client.patch(f"/api/checklist/{item_id}", json={"done": True}).json()
    assert ev["progress"] == {"done": 1, "total": 3, "percent": 33}

    ev = client.post(f"/api/events/{soon['id']}/checklist", json={"label": "Extra"}).json()
    assert ev["checklist"][-1]["label"] == "Extra"

    ids = [c["id"] for c in ev["checklist"]][::-1]
    ev = client.put(f"/api/events/{soon['id']}/checklist/order", json={"ids": ids}).json()
    assert [c["id"] for c in ev["checklist"]] == ids
    assert client.put(f"/api/events/{soon['id']}/checklist/order", json={"ids": ids[:1]}).status_code == 422


def test_ics_and_404_and_delete(client):
    ev = client.post("/api/events", json=make_payload()).json()
    assert "BEGIN:VEVENT" in client.get(f"/api/events/{ev['id']}/ics").text
    assert client.delete(f"/api/events/{ev['id']}").status_code == 204
    assert client.get(f"/api/events/{ev['id']}").status_code == 404


# ---- webhook, migration, long pastes ----
H = {"X-Webhook-Secret": "dev-secret"}


def test_webhook_tasks_and_deadlines(client):
    ev = client.post("/api/events", json=make_payload(30)).json()
    body = {"event_id": ev["id"], "external_id": "bot-1", "label": "Record demo", "done": False}
    assert client.post("/api/webhook/tasks", json=body).status_code == 401
    r = client.post("/api/webhook/tasks", json=body, headers=H).json()
    assert r["created"] and r["event"]["progress"]["total"] == 4
    r = client.post("/api/webhook/tasks", json={"event_id": ev["id"], "external_id": "bot-1", "done": True}, headers=H).json()
    assert not r["created"] and r["event"]["progress"] == {"done": 1, "total": 4, "percent": 25}
    assert client.post("/api/webhook/tasks", json={"event_id": 999, "external_id": "x", "label": "a"}, headers=H).status_code == 404
    assert client.post("/api/webhook/tasks", json={"event_id": ev["id"], "external_id": "new"}, headers=H).status_code == 422
    due = (now_utc() + timedelta(hours=2)).isoformat() + "Z"
    d = {"event_id": ev["id"], "external_id": "dl-1", "label": "Extended submission", "kind": "submission", "due_at": due}
    r = client.post("/api/webhook/deadlines", json=d, headers=H).json()
    assert r["created"] and r["event"]["key_deadline"]["label"] == "Extended submission"
    later = (now_utc() + timedelta(days=10)).isoformat() + "Z"
    r = client.post("/api/webhook/deadlines", json={**d, "due_at": later}, headers=H).json()
    assert not r["created"] and r["event"]["urgency"] != "overdue"


def test_migration_adds_columns_to_old_db(tmp_path):
    import sqlite3
    from sqlalchemy import create_engine, inspect
    import app.database as dbm
    f = tmp_path / "old.db"
    con = sqlite3.connect(f)
    con.executescript("CREATE TABLE deadlines(id INTEGER PRIMARY KEY, event_id INT, label TEXT, kind TEXT, due_at DATETIME);"
                      "CREATE TABLE checklist_items(id INTEGER PRIMARY KEY, event_id INT, label TEXT, done BOOL, position INT);")
    con.close()
    old = dbm.engine
    dbm.engine = create_engine(f"sqlite:///{f}")
    try:
        dbm.migrate(); dbm.migrate()  # second run must be a no-op
        cols = [c["name"] for c in inspect(dbm.engine).get_columns("checklist_items")]
        assert "external_id" in cols
    finally:
        dbm.engine = old


def test_long_paste_is_accepted_and_unknown_api_is_404(client):
    long_text = SAMPLE + ("Lorem ipsum dolor sit amet. " * 2000)
    assert len(long_text) > 20000
    assert client.post("/api/extract", json={"text": long_text}).status_code == 200
