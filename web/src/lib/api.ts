const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

function baseUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}/api${p}`;
}

export async function fetchRuns(): Promise<unknown> {
  const res = await fetch(baseUrl("/runs"));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchRun(runId: string): Promise<unknown> {
  const res = await fetch(baseUrl(`/runs/${runId}`));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** 5 minutes: large CSVs can take a long time to process */
const CREATE_RUN_TIMEOUT_MS = 5 * 60 * 1000;

export async function createRun(entityType: string, file: File): Promise<unknown> {
  const form = new FormData();
  form.set("entity_type", entityType);
  form.set("file", file);
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CREATE_RUN_TIMEOUT_MS);
  try {
    const res = await fetch(baseUrl("/runs"), {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  } catch (e) {
    if (e instanceof Error) {
      if (e.name === "AbortError") throw new Error("Request timed out. Large files may take 1–2 minutes. Try again or use a smaller CSV.");
      if (e.message === "Failed to fetch" || e.cause?.toString?.().includes("fetch")) throw new Error("Could not reach the server. Make sure the API is running (uvicorn server.main:app --reload on port 8000) and NEXT_PUBLIC_API_URL is correct.");
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchMatches(
  runId: string,
  opts?: { min_score?: number; max_score?: number; status?: string; limit?: number; offset?: number }
): Promise<unknown> {
  const params = new URLSearchParams();
  if (opts?.min_score != null) params.set("min_score", String(opts.min_score));
  if (opts?.max_score != null) params.set("max_score", String(opts.max_score));
  if (opts?.status) params.set("status", opts.status);
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  const q = params.toString();
  const url = baseUrl(`/runs/${runId}/matches`) + (q ? `?${q}` : "");
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function approveMatch(runId: string, matchId: string): Promise<void> {
  const res = await fetch(baseUrl(`/runs/${runId}/matches/${matchId}/approve`), { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
}

export async function rejectMatch(runId: string, matchId: string): Promise<void> {
  const res = await fetch(baseUrl(`/runs/${runId}/matches/${matchId}/reject`), { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
}

export async function fetchClusters(runId: string): Promise<unknown> {
  const res = await fetch(baseUrl(`/runs/${runId}/clusters`));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchCluster(runId: string, clusterId: string): Promise<unknown> {
  const res = await fetch(baseUrl(`/runs/${runId}/clusters/${clusterId}`));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function approveCluster(runId: string, clusterId: string): Promise<void> {
  const res = await fetch(baseUrl(`/runs/${runId}/clusters/${clusterId}/approve`), { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
}

export async function exportCsv(runId: string): Promise<Blob> {
  const res = await fetch(baseUrl(`/runs/${runId}/export/csv`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selection: "approved_survivors" }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

export async function exportClay(runId: string): Promise<unknown> {
  const res = await fetch(baseUrl(`/runs/${runId}/export/clay`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved_survivors: true }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function exportN8n(runId: string): Promise<unknown> {
  const res = await fetch(baseUrl(`/runs/${runId}/export/n8n`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved_survivors: true }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
