"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cancelRun, getDemo, getHealth, getRun, startRun, streamRun } from "./api";
import type { Health, RunEvent, RunResult, SearchNode, StartRunRequest } from "./types";

export interface Activity {
  id: string;
  at: number;
  kind: "checkpoint" | "diagnosing" | "diagnosed" | "search" | "adjudicated" | "error" | "done";
  tier?: string;
  text: string;
  detail?: string;
}

export interface RunState {
  nodes: SearchNode[];
  result: RunResult | null;
  running: boolean;
  stopping: boolean;
  recorded: { source: string; at: number | null } | null;
  health: Health | null;
  activity: Activity[];
  error: string | null;
  booted: boolean;
}

const EMPTY: RunState = {
  nodes: [],
  result: null,
  running: false,
  stopping: false,
  recorded: null,
  health: null,
  activity: [],
  error: null,
  booted: false,
};

let activitySeq = 0;

export function useRun() {
  const [state, setState] = useState<RunState>(EMPTY);
  const stopRef = useRef<(() => void) | null>(null);
  const runIdRef = useRef<string | null>(null);

  const apply = useCallback((event: RunEvent) => {
    setState((prev) => {
      const next = { ...prev };

      const push = (activity: Omit<Activity, "id" | "at">) => {
        next.activity = [
          ...next.activity,
          { id: `a${activitySeq++}`, at: event.at, ...activity },
        ].slice(-60);
      };

      switch (event.type) {
        case "node": {
          const index = next.nodes.findIndex((n) => n.id === event.node.id);
          next.nodes =
            index === -1
              ? [...next.nodes, event.node]
              : next.nodes.map((n, i) => (i === index ? event.node : n));
          break;
        }
        case "checkpoint":
          push({
            kind: "checkpoint",
            text:
              event.stage === "setup"
                ? `Environment prepared in ${event.seconds ?? "?"}s — every branch forks from here`
                : "Repository staged in the sandbox",
          });
          break;
        case "diagnosing":
          push({ kind: "diagnosing", tier: event.tier, text: "Reading the failure" });
          break;
        case "diagnosed":
          push({
            kind: "diagnosed",
            tier: event.tier,
            text: `${event.hypotheses.length} rival ${
              event.hypotheses.length === 1 ? "theory" : "theories"
            } to test`,
            detail: event.root_cause,
          });
          if (event.searched) {
            push({
              kind: "search",
              text: "Looked outside the repository",
              detail: event.search_query,
            });
          }
          break;
        case "adjudicated":
          push({ kind: "adjudicated", tier: "ultra", text: "Broke a tie between branches" });
          break;
        case "budget_exceeded":
          push({ kind: "error", text: "Token budget reached", detail: event.message });
          break;
        case "error":
          next.error = event.message;
          push({ kind: "error", text: "Run failed", detail: event.message });
          break;
        case "run_finished":
          next.result = event.result;
          next.nodes = event.result.nodes;
          break;
        case "cancelled":
          push({ kind: "error", text: "Stopped by request" });
          break;
        case "done":
          next.running = false;
          next.stopping = false;
          push({ kind: "done", text: "Search finished" });
          break;
      }
      return next;
    });
  }, []);

  const applyRef = useRef(apply);
  applyRef.current = apply;

  const attach = useCallback((runId: string) => {
    runIdRef.current = runId;
    stopRef.current?.();
    stopRef.current = streamRun(runId, applyRef.current, () =>
      // A dropped connection is not a finished run: the server keeps the whole
      // event history and will replay it, so say so rather than showing the
      // partial tree as the result.
      setState((prev) =>
        prev.result
          ? { ...prev, running: false, stopping: false }
          : {
              ...prev,
              running: false,
              stopping: false,
              error: "Lost the connection to the run. Reload to replay it from the server.",
            },
      ),
    );
  }, []);

  /*
   * Boot, in order of specificity:
   *   ?run=<id>  attach to that run -- live if it is still going, replayed if
   *              not. This is what makes a run linkable.
   *   otherwise  show the recorded demo, so a visitor with no key still gets a
   *              real finished search to explore.
   */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const requested = new URLSearchParams(window.location.search).get("run");
      const [health, existing] = await Promise.all([
        getHealth().catch(() => null),
        requested ? getRun(requested).catch(() => null) : Promise.resolve(null),
      ]);
      if (cancelled) return;

      if (requested && existing) {
        setState((prev) => ({
          ...prev,
          booted: true,
          health,
          running: !existing.done,
          error: existing.error || null,
          nodes: existing.result?.nodes ?? [],
          result: existing.result,
        }));
        attach(requested);
        return;
      }

      const demo = await getDemo().catch(() => null);
      if (cancelled) return;
      setState((prev) => ({
        ...prev,
        booted: true,
        health,
        ...(demo?.available && demo.run
          ? {
              nodes: demo.run.nodes,
              result: demo.run,
              recorded: { source: demo.source, at: demo.recorded_at },
            }
          : {}),
      }));
    })();
    return () => {
      cancelled = true;
      stopRef.current?.();
    };
  }, [attach]);

  const start = useCallback(
    async (request: StartRunRequest) => {
      stopRef.current?.();
      setState((prev) => ({
        ...EMPTY,
        booted: true,
        health: prev.health,
        running: true,
      }));
      try {
        const runId = await startRun(request)
        // Without this, Stop has no run id to cancel and falls back to merely
        // closing the stream -- which is the bug it was meant to fix.
        runIdRef.current = runId
        // Make the run linkable without reloading the page.
        const url = new URL(window.location.href);
        url.searchParams.set("run", runId);
        window.history.replaceState(null, "", url);
        stopRef.current = streamRun(runId, applyRef.current, () =>
          setState((prev) => ({ ...prev, running: false })),
        );
      } catch (error) {
        setState((prev) => ({
          ...prev,
          running: false,
          error: error instanceof Error ? error.message : String(error),
        }));
      }
    },
    [],
  );

  /*
   * Stop the run, not just the watching. The stream stays open so the tree
   * keeps filling in until the search actually stops, which is at most one
   * model call away -- closing it here would hide the branches already paid
   * for.
   */
  const stop = useCallback(() => {
    const runId = runIdRef.current;
    setState((prev) => ({ ...prev, stopping: true }));
    if (runId) void cancelRun(runId);
    else {
      stopRef.current?.();
      setState((prev) => ({ ...prev, running: false, stopping: false }));
    }
  }, []);

  return { state, start, stop };
}
