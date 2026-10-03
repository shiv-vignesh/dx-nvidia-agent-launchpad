// The only module that talks to the ShiftGuard backend.
// Base URL: VITE_API_BASE, or the GB10 box. Same-origin when served from the backend itself.
const BASE = (
  import.meta.env?.VITE_API_BASE ?? "http://172.20.65.125:8099"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, detail) {
    super(
      typeof detail === "string" ? detail : detail?.error || `HTTP ${status}`,
    );
    this.status = status;
    this.detail = detail;
  }
}

async function call(path, { method = "GET", body } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
  return data;
}

export const listPatients = () => call("/patients");
export const deriveTasks = (pid) =>
  call(`/tasks/derive/${pid}`, { method: "POST" });
export const draftHandoff = (pid, giver = "N-02", receiver = "N-01") =>
  call(`/handoffs/${pid}/draft?giver=${giver}&receiver=${receiver}`, {
    method: "POST",
  });
export const getHandoff = (hid) => call(`/handoffs/${hid}`);
export const editField = (hid, key, value, actor = "N-02") =>
  call(`/handoffs/${hid}/fields/${key}`, {
    method: "PATCH",
    body: { value, actor },
  });
export const startCoverage = (hid, text) =>
  call(`/handoffs/${hid}/coverage`, { method: "POST", body: { text } });
export const getCoverage = (hid) => call(`/handoffs/${hid}/coverage`);
export const ackItem = (hid, kind, ref = "all", actor = "N-01") =>
  call(`/handoffs/${hid}/ack`, { method: "POST", body: { kind, ref, actor } });
export const closeCheck = (hid) => call(`/handoffs/${hid}/close-check`);

// ---------------------------------------------------------------- mapping

const SEV = { safety_block: "red", contingency: "amber", task: "teal" };

/** A backend gap item rendered in the shape App.jsx's change cards already expect. */
export function gapToChange(gap, fieldsByLabel = {}) {
  const field = fieldsByLabel[gap.text] || null;
  const value = field?.value || gap.text;
  return {
    id: String(gap.ref),
    title: gap.text.length > 72 ? gap.text.slice(0, 71) + "…" : gap.text,
    severity: SEV[gap.kind] || "teal",
    // value can be null on an unfilled required field — never call .split on it
    lines: String(value || "")
      .split(";")
      .map((s) => s.trim())
      .filter(Boolean),
    source:
      field?.source ||
      (gap.kind === "task" ? "Derived task" : "Situation awareness"),
    text: gap.text,
    kind: gap.kind,
  };
}

export function patientToCard(p) {
  return {
    id: p.id,
    name: p.name,
    bed: p.bed || p.room,
    context: [
      p.dx,
      p.post_op_day != null ? `post-op day ${p.post_op_day}` : null,
    ]
      .filter(Boolean)
      .join(" · "),
    mrn: p.mrn || "—",
    age: [p.age, p.sex].filter(Boolean).join(" "),
    attention: p.fall_risk === "HIGH" || p.weight_stale === true,
  };
}

export { BASE };
