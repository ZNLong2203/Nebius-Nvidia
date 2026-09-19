import type { DemoResponse, Health, RunEvent, RunResult, StartRunRequest } from "./types";

/**
 * In development Next proxies /api to the FastAPI service (see next.config.ts).
 * The static export is served by that same service, so the relative path is
 * correct in both cases and there is never a cross-origin request.
 */
const base = "";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${base}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: ${response.status} ${response.statusText}`);
  return (await response.json()) as T;
}

export const getHealth = () => get<Health>("/api/health");
export const getDemo = () => get<DemoResponse>("/api/demo");
export const getRun = (id: string) =>
  get<{ run_id: string; done: boolean; error: string; result: RunResult | null }>(`/api/runs/${id}`);

export async function startRun(request: StartRunRequest): Promise<string> {
  const response = await fetch(`${base}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.detail ?? response.statusText);
  return payload.run_id as string;
}

/**
 * Subscribe to a run. The server replays every event from the beginning before
 * streaming live ones, so a late subscriber still draws the whole tree.
 */
export function streamRun(
  runId: string,
  onEvent: (event: RunEvent) => void,
  onClose: () => void,
): () => void {
  const source = new EventSource(`${base}/api/runs/${runId}/events`);

  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as RunEvent);
    } catch {
      /* a malformed frame should not tear down the stream */
    }
  };
  source.onerror = () => {
    source.close();
    onClose();
  };

  return () => source.close();
}
