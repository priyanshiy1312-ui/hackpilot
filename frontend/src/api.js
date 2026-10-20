async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`/api${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new Error("Cannot reach the HackPilot server. Check that the backend is running on port 8000.");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const msg = Array.isArray(d) ? d.map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`).join("; ") : d;
    throw new Error(msg || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  list: async () => { const r = await request("/events"); if (!Array.isArray(r)) throw new Error("Unexpected reply from the server."); return r; },
  extract: (text, use_llm) => request("/extract", { method: "POST", body: { text, use_llm } }),
  create: (body) => request("/events", { method: "POST", body }),
  update: (id, body) => request(`/events/${id}`, { method: "PUT", body }),
  remove: (id) => request(`/events/${id}`, { method: "DELETE" }),
  addItem: (id, label) => request(`/events/${id}/checklist`, { method: "POST", body: { label } }),
  patchItem: (itemId, body) => request(`/checklist/${itemId}`, { method: "PATCH", body }),
  removeItem: (itemId) => request(`/checklist/${itemId}`, { method: "DELETE" }),
  reorder: (id, ids) => request(`/events/${id}/checklist/order`, { method: "PUT", body: { ids } }),
};
