import type { DemoResponse, Health, RunEvent, RunResult, StartRunRequest } from "./types";

/**
 * In development Next proxies /api to the FastAPI service (see next.config.ts).
 * The static export is served by that same service, so the relative path is
 * correct in both cases and there is never a cross-origin request.
 */
const base = "";

/**
 * A static build (`NEXT_PUBLIC_STATIC_DEMO=1`) has no server behind it -- it is
 * what GitHub Pages hosts. It reads recorded runs shipped beside the page by
 * `scripts/bundle-demo.mjs`, and reports that nothing can be started, so the
 * rest of the interface behaves exactly as it does against a server with no key.
 */
export const STATIC_DEMO = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL ?? "https://github.com/ZNLong2203/Nebius-Nvidia";
const shipped = `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/demo`;

const STATIC_HEALTH: Health = {
  ok: true,
  llm_configured: false,
  tavily_configured: false,
  can_run: false,
  backend: "contree",
  models: {},
  saved_runs: 0,
  static: true,
};

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${base}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: ${response.status} ${response.statusText}`);
  return (await response.json()) as T;
}

export const getHealth = () =>
  STATIC_DEMO ? Promise.resolve(STATIC_HEALTH) : get<Health>("/api/health");
export const getDemo = () => get<DemoResponse>(STATIC_DEMO ? `${shipped}/demo.json` : "/api/demo");
export const getRun = (id: string) =>
  get<{ run_id: string; done: boolean; error: string; result: RunResult | null; recorded_at?: number | null }>(
    STATIC_DEMO ? `${shipped}/runs/${encodeURIComponent(id)}.json` : `/api/runs/${id}`,
  );

/** Ask the server to stop a run. Closing the stream alone would not. */
export async function cancelRun(runId: string): Promise<void> {
  await fetch(`${base}/api/runs/${runId}/cancel`, { method: "POST" }).catch(() => {
    /* the run may already have finished */
  });
}

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
