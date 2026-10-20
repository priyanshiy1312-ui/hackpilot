import { useState } from "react";
import { api } from "./api.js";
import { fromLocalInput, toLocalInput } from "./time.js";

const KINDS = ["submission", "registration", "results", "event", "other"];
const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);

function toDraft(src) {
  return {
    name: src.name, url: src.url || "",
    tracks: (src.tracks || []).join("\n"), prizes: (src.prizes || []).join("\n"),
    deadlines: (src.deadlines || []).map((d) => ({ label: d.label, kind: d.kind, due: toLocalInput(d.due_at) })),
    checklist: (src.checklist || []).map((c) => (typeof c === "string" ? c : c.label)).join("\n"),
  };
}

export default function EventForm({ existing, onClose, onSaved }) {
  const [step, setStep] = useState(existing ? "review" : "paste");
  const [text, setText] = useState("");
  const [useLlm, setUseLlm] = useState(false);
  const [draft, setDraft] = useState(existing ? toDraft(existing) : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  const extract = async () => {
    setBusy(true); setError("");
    try {
      const r = await api.extract(text, useLlm);
      setDraft(toDraft(r));
      setNote(r.warning || `Extracted with ${r.method === "llm" ? "the LLM" : "the built-in parser"}. Check every field before saving.`);
      setStep("review");
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const setD = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const setDeadline = (i, patch) => setD({ deadlines: draft.deadlines.map((d, j) => (j === i ? { ...d, ...patch } : d)) });

  const save = async (e) => {
    e.preventDefault();
    setError("");
    if (!draft.name.trim()) return setError("Give the hackathon a name.");
    if (draft.deadlines.length === 0 || draft.deadlines.some((d) => !d.label.trim() || !d.due)) {
      return setError("Every deadline needs a label and a date. Add at least one.");
    }
    const body = {
      name: draft.name.trim(), url: draft.url.trim(), tracks: lines(draft.tracks), prizes: lines(draft.prizes),
      deadlines: draft.deadlines.map((d) => ({ label: d.label.trim(), kind: d.kind, due_at: fromLocalInput(d.due) })),
      checklist: lines(draft.checklist),
    };
    setBusy(true);
    try { existing ? await api.update(existing.id, body) : await api.create(body); onSaved(); }
    catch (err) { setError(err.message); setBusy(false); }
  };

  return (
    <div className="scrim" role="dialog" aria-modal="true" aria-labelledby="form-title">
      <div className="sheet">
        <header>
          <h2 id="form-title">{existing ? "Edit hackathon" : step === "paste" ? "Add a hackathon" : "Review the details"}</h2>
          <button className="icon" onClick={onClose} aria-label="Close">✕</button>
        </header>

        {step === "paste" && (
          <div className="stack">
            <label htmlFor="paste">Paste the event page text</label>
            <textarea id="paste" rows={12} value={text} onChange={(e) => setText(e.target.value)}
              placeholder={"Graph Hacks 2026\nTrack 1: Context for AI Agents\nSubmission deadline: Oct 18, 2026 at 11:59 PM IST\nWinners announced 25 October 2026"} />
            <label className="inline"><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Use the LLM extractor when the server has an API key</label>
            {error && <p className="error" role="alert">{error}</p>}
            <div className="actions">
              <button className="btn ghost" onClick={() => { setDraft({ name: "", url: "", tracks: "", prizes: "", deadlines: [], checklist: "" }); setNote(""); setStep("review"); }}>Enter by hand</button>
              <button className="btn" disabled={busy || text.trim().length < 20} onClick={extract}>{busy ? "Extracting…" : "Extract details"}</button>
            </div>
            {text.trim().length < 20 && <p className="muted small-text">Paste at least 20 characters to extract.</p>}
          </div>
        )}

        {step === "review" && draft && (
          <form className="stack" onSubmit={save}>
            {note && <p className={note.startsWith("No dates") ? "error" : "muted"}>{note}</p>}
            <label>Name<input value={draft.name} onChange={(e) => setD({ name: e.target.value })} maxLength={200} /></label>
            <label>Event page link<input value={draft.url} onChange={(e) => setD({ url: e.target.value })} placeholder="https://" /></label>

            <fieldset>
              <legend>Deadlines</legend>
              {draft.deadlines.map((d, i) => (
                <div className="deadline-row" key={i}>
                  <input aria-label="Deadline label" value={d.label} onChange={(e) => setDeadline(i, { label: e.target.value })} />
                  <select aria-label="Deadline type" value={d.kind} onChange={(e) => setDeadline(i, { kind: e.target.value })}>
                    {KINDS.map((k) => <option key={k}>{k}</option>)}
                  </select>
                  <input aria-label="Deadline date and time" type="datetime-local" value={d.due} onChange={(e) => setDeadline(i, { due: e.target.value })} />
                  <button type="button" className="icon" aria-label="Remove deadline" onClick={() => setD({ deadlines: draft.deadlines.filter((_, j) => j !== i) })}>✕</button>
                </div>
              ))}
              <button type="button" className="btn ghost small" onClick={() => setD({ deadlines: [...draft.deadlines, { label: "Submission deadline", kind: "submission", due: toLocalInput(new Date(Date.now() + 7 * 864e5).toISOString()) }] })}>Add deadline</button>
            </fieldset>

            <div className="two">
              <label>Tracks (one per line)<textarea rows={3} value={draft.tracks} onChange={(e) => setD({ tracks: e.target.value })} /></label>
              <label>Prizes (one per line)<textarea rows={3} value={draft.prizes} onChange={(e) => setD({ prizes: e.target.value })} /></label>
            </div>
            {!existing && (
              <label>Submission checklist (one task per line)
                <textarea rows={6} value={draft.checklist} onChange={(e) => setD({ checklist: e.target.value })} />
              </label>
            )}
            {error && <p className="error" role="alert">{error}</p>}
            <div className="actions">
              {!existing && <button type="button" className="btn ghost" onClick={() => setStep("paste")}>Back</button>}
              <button className="btn" disabled={busy}>{busy ? "Saving…" : existing ? "Save changes" : "Accept details"}</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
