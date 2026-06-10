/** HTTP client per contracts/http_api.md — Session C1 owns; panels import read-only. */

const API_BASE: string = import.meta.env.VITE_API_BASE ?? "http://localhost:8080";

export async function postWhatif(scenario: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/whatif`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario }),
  });
  return res.json() as Promise<{ accepted: boolean; run_id: string; event_id: string }>;
}

export async function postApproval(approval_id: string, approved: boolean, note?: string) {
  const res = await fetch(`${API_BASE}/approval`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id, approved, note }),
  });
  return res.json() as Promise<{ ok: boolean; approval_id: string; applied: boolean }>;
}

export function reportUrl(runId: string, format?: "md") {
  return `${API_BASE}/report/${runId}${format ? `?format=${format}` : ""}`;
}

export { API_BASE };
