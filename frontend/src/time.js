import { useEffect, useState } from "react";

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

const pad = (n) => String(n).padStart(2, "0");

export function countdown(dueIso, now) {
  const diff = new Date(dueIso).getTime() - now;
  const abs = Math.abs(diff);
  const d = Math.floor(abs / 864e5);
  const h = Math.floor((abs % 864e5) / 36e5);
  const m = Math.floor((abs % 36e5) / 6e4);
  const s = Math.floor((abs % 6e4) / 1e3);
  return { late: diff < 0, text: `${d}d ${pad(h)}:${pad(m)}:${pad(s)}` };
}

export const fmtDate = (iso) =>
  new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

// <input type="datetime-local"> works in local time; the API stores UTC.
export function toLocalInput(iso) {
  const d = new Date(iso);
  const off = d.getTimezoneOffset() * 6e4;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
}
export const fromLocalInput = (v) => new Date(v).toISOString();

export function units(dueIso, now) {
  const diff = new Date(dueIso).getTime() - now, a = Math.abs(diff);
  return {
    late: diff < 0,
    parts: [["Days", Math.floor(a / 864e5)], ["Hours", Math.floor((a % 864e5) / 36e5)],
            ["Minutes", Math.floor((a % 36e5) / 6e4)], ["Seconds", Math.floor((a % 6e4) / 1e3)]],
  };
}

// urgency recomputed from the clock so it stays correct between server refreshes
export function liveUrgency(event, now) {
  const key = event.key_deadline;
  if (!key) return event.urgency;
  const left = new Date(key.due_at).getTime() - now;
  return left < 0 ? "overdue" : left < 48 * 36e5 ? "red" : left < 7 * 864e5 ? "amber" : "green";
}
