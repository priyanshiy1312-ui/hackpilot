import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { fmtDate, liveUrgency, units, useNow } from "./time.js";
import EventForm from "./EventForm.jsx";

const pad = (n) => String(n).padStart(2, "0");
const KINDS = ["submission", "registration", "results", "event", "other"];

function Units({ due, now, big }) {
  const u = units(due, now);
  return (
    <div className={`units ${big ? "big" : ""}`} role="timer" aria-label={u.late ? "Time since deadline" : "Time left"}>
      {u.parts.map(([l, v]) => <div className="unit" key={l}><b>{pad(v)}</b><span>{l}</span></div>)}
    </div>
  );
}

function Hero({ event, now }) {
  if (!event) return null;
  const key = event.key_deadline, urg = liveUrgency(event, now);
  return (
    <section className={`hero u-${urg}`} aria-label="Next deadline">
      <p className="hero-kicker">{urg === "overdue" ? "Deadline passed" : "Next deadline"} · {event.name}</p>
      <Units due={key.due_at} now={now} big />
      <p className="hero-what">{key.label} · {fmtDate(key.due_at)}</p>
    </section>
  );
}

const URGENCY_LABEL = { green: "On track", amber: "Due this week", red: "Due within 48 hours", overdue: "Deadline passed" };

function Checklist({ event, onChange, onError }) {
  const [label, setLabel] = useState("");
  const run = async (fn) => {
    try { onChange(await fn()); } catch (e) { onError(e.message); }
  };
  const move = (idx, dir) => {
    const ids = event.checklist.map((c) => c.id);
    const j = idx + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[idx], ids[j]] = [ids[j], ids[idx]];
    run(() => api.reorder(event.id, ids));
  };
  const add = (e) => {
    e.preventDefault();
    if (!label.trim()) return;
    run(() => api.addItem(event.id, label.trim()));
    setLabel("");
  };
  return (
    <div className="checklist">
      <ul>
        {event.checklist.map((c, i) => (
          <li key={c.id} className={c.done ? "done" : ""}>
            <label>
              <input type="checkbox" checked={c.done} onChange={(e) => run(() => api.patchItem(c.id, { done: e.target.checked }))} />
              <span>{c.label}</span>
            </label>
            <span className="row-actions">
              <button className="icon" aria-label={`Move "${c.label}" up`} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
              <button className="icon" aria-label={`Move "${c.label}" down`} disabled={i === event.checklist.length - 1} onClick={() => move(i, 1)}>↓</button>
              <button className="icon" aria-label={`Remove "${c.label}"`} onClick={() => run(() => api.removeItem(c.id))}>✕</button>
            </span>
          </li>
        ))}
      </ul>
      {event.checklist.length === 0 && <p className="muted">No tasks yet. Add the first one below.</p>}
      <form onSubmit={add} className="add-item">
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Add a task, e.g. Record the demo video" aria-label="New checklist task" maxLength={300} />
        <button className="btn small">Add task</button>
      </form>
    </div>
  );
}

function EventCard({ event, now, onChange, onEdit, onDelete, onError }) {
  const [open, setOpen] = useState(false);
  const key = event.key_deadline;
  const urgency = liveUrgency(event, now);
  return (
    <article className={`card u-${urgency}`}>
      <header>
        <div>
          <h2>{event.name}</h2>
          <p className="status">{URGENCY_LABEL[urgency]}</p>
        </div>
        <div className="card-actions">
          <button className="btn ghost small" onClick={() => onEdit(event)}>Edit</button>
          <button className="btn ghost small" onClick={() => onDelete(event)}>Delete</button>
        </div>
      </header>

      {key && (
        <div className="clock">
          <Units due={key.due_at} now={now} />
          <span className="what">{new Date(key.due_at) < now ? "past" : "until"} {key.label}<br />{fmtDate(key.due_at)}</span>
        </div>
      )}

      <div className="progress" role="progressbar" aria-valuenow={event.progress.percent} aria-valuemin={0} aria-valuemax={100} aria-label="Checklist progress">
        <div style={{ width: `${event.progress.percent}%` }} />
      </div>
      <p className="muted small-text">{event.progress.done} of {event.progress.total} tasks done</p>

      {(event.tracks.length > 0 || event.prizes.length > 0) && (
        <div className="meta">
          {event.tracks.map((t) => <span key={t} className="chip">{t}</span>)}
          {event.prizes.map((p) => <span key={p} className="chip prize">{p}</span>)}
        </div>
      )}

      <button className="toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide checklist and dates" : "Show checklist and dates"}
      </button>
      {open && (
        <>
          <Checklist event={event} onChange={onChange} onError={onError} />
          <ul className="dates">
            {event.deadlines.map((d) => <li key={d.id}><span>{d.label}</span><span>{fmtDate(d.due_at)}</span></li>)}
          </ul>
          <div className="links">
            {event.url && <a href={event.url} target="_blank" rel="noreferrer">Event page</a>}
            <a href={`/api/events/${event.id}/ics`}>Add dates to calendar</a>
          </div>
        </>
      )}
    </article>
  );
}

export default function App() {
  const [events, setEvents] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState(null); // null | {event?: existing}
  const [theme, setTheme] = useState(() => localStorage.getItem("hp-theme") || "light");
  const [q, setQ] = useState(""), [kind, setKind] = useState("all"), [urg, setUrg] = useState("all");
  const now = useNow();

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("hp-theme", theme); }, [theme]);

  const load = useCallback(async () => {
    try { setEvents(await api.list()); setError(""); } catch (e) { setError(e.message); setEvents((p) => p ?? []); }
  }, []);
  useEffect(() => { load(); }, [load]);
  // pick up changes made by the bot webhook without a manual refresh
  useEffect(() => {
    const t = setInterval(() => { if (!document.hidden) load(); }, 10000);
    return () => clearInterval(t);
  }, [load]);

  const replace = (updated) => { setEvents((list) => list.map((e) => (e.id === updated.id ? updated : e))); };
  const remove = async (ev) => {
    if (!window.confirm(`Delete "${ev.name}" and its checklist?`)) return;
    try { await api.remove(ev.id); await load(); } catch (e) { setError(e.message); }
  };

  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (events || []).filter((ev) => {
      const hay = [ev.name, ...ev.tracks, ...ev.prizes, ...ev.deadlines.flatMap((d) => [d.label, d.kind]), ...ev.checklist.map((c) => c.label)].join(" ").toLowerCase();
      return (!s || hay.includes(s))                                          // search: name, type (deadline kind), tracks, tasks
        && (kind === "all" || ev.deadlines.some((d) => d.kind === kind))
        && (urg === "all" || liveUrgency(ev, now) === urg);
    });
  }, [events, q, kind, urg, now]);
  const filtering = q.trim() || kind !== "all" || urg !== "all";
  const hero = (events || []).find((e) => e.key_deadline && liveUrgency(e, now) !== "overdue");

  return (
    <div className="shell">
      <header className="top">
        <div>
          <h1>HackPilot</h1>
          <p className="tag">Every hackathon deadline on one board.</p>
        </div>
        <div className="top-actions">
          <button className="btn ghost" aria-pressed={theme === "dark"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "Light mode" : "Dark mode"}</button>
          <a className="btn ghost" href="/api/ics">Export all dates (.ics)</a>
          <button className="btn" onClick={() => setForm({})}>Add hackathon</button>
        </div>
      </header>

      {error && <div className="banner" role="alert">{error} <button className="link" onClick={load}>Try again</button></div>}
      {events === null && <p className="muted" aria-live="polite">Loading your hackathons…</p>}
      <Hero event={hero} now={now} />

      {events && events.length === 0 && !error && (
        <section className="empty">
          <h2>No hackathons yet</h2>
          <p>Paste the details from a Devpost or event page and HackPilot pulls out the deadlines and builds your checklist.</p>
          <button className="btn" onClick={() => setForm({})}>Add your first hackathon</button>
        </section>
      )}

      {events && events.length > 0 && (
        <div className="toolbar" role="search">
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or type (e.g. submission)" aria-label="Search the board" />
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Filter by deadline type">
            <option value="all">All types</option>{KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <select value={urg} onChange={(e) => setUrg(e.target.value)} aria-label="Filter by urgency">
            <option value="all">All urgency</option><option value="overdue">Overdue only</option>
            <option value="red">Due within 48 hours</option><option value="amber">Due this week</option><option value="green">On track</option>
          </select>
          {filtering && <button className="btn ghost small" onClick={() => { setQ(""); setKind("all"); setUrg("all"); }}>Clear filters</button>}
          <span className="muted small-text" aria-live="polite">Showing {shown.length} of {events.length}</span>
        </div>
      )}
      {events && events.length > 0 && shown.length === 0 && <p className="muted">Nothing matches these filters.</p>}

      <main className="board">
        {shown.map((ev) => (
          <EventCard key={ev.id} event={ev} now={now} onChange={replace} onEdit={(e) => setForm({ event: e })} onDelete={remove} onError={setError} />
        ))}
      </main>

      {form && <EventForm existing={form.event} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
    </div>
  );
}
