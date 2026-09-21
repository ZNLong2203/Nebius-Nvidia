"use client";

import { REPO_URL } from "@/lib/api";
import type { Health, RunResult } from "@/lib/types";
import { Badge } from "./Primitives";

export function ContextStrip({
  health,
  result,
  recorded,
  running,
  stopping,
  error,
}: {
  health: Health | null;
  result: RunResult | null;
  recorded: { source: string; at: number | null } | null;
  running: boolean;
  stopping: boolean;
  error: string | null;
}) {
  if (error) {
    return (
      <Strip tone="critical">
        <Badge tone="critical" icon="!">
          failed
        </Badge>
        <span className="mono text-[12px] text-ink-2">{error}</span>
      </Strip>
    );
  }

  if (running) {
    return (
      <Strip tone={stopping ? "warning" : "accent"}>
        <span className="flex items-center gap-2 text-[12.5px] font-medium">
          <span
            className="size-1.5 animate-pulse rounded-full"
            style={{ background: stopping ? "var(--warning)" : "var(--accent)" }}
          />
          {stopping ? "Stopping" : "Searching"}
        </span>
        <span className="text-[12.5px] text-ink-2">
          {stopping
            ? "Finishing the step already in flight, then keeping everything found so far."
            : "Branches open as rival theories are tested against the same checkpoint."}
        </span>
      </Strip>
    );
  }

  if (!result) return null;

  const before = result.baseline;
  const after = result.final;

  return (
    <Strip tone={result.solved ? "good" : "warning"}>
      {result.solved ? (
        <Badge tone="good" icon="✓">
          suite is green
        </Badge>
      ) : (
        <Badge tone="warning" icon="→">
          best branch kept
        </Badge>
      )}

      {before && (
        <span className="tnum text-[12.5px] text-ink-2">
          <span className="text-ink-3">tests</span>{" "}
          <span className="font-semibold text-ink">
            {before.passed}/{before.total}
          </span>
          {after && (
            <>
              {" → "}
              <span
                className="font-semibold"
                style={{ color: result.solved ? "var(--good)" : "var(--ink)" }}
              >
                {after.passed}/{after.total}
              </span>
            </>
          )}
        </span>
      )}

      {recorded && (
        <span className="text-[12px] text-ink-3">
          Recorded run — a real search that already finished
          {result.stats?.backend === "contree"
            ? ` on Nebius Sandboxes, ${result.stats.forks ?? result.stats.sandbox_executions} forked executions`
            : " on the local backend"}
          {recorded.at ? `, ${new Date(recorded.at * 1000).toLocaleString()}` : ""}.
          {health?.static ? (
            <>
              {" This page is a static recording — "}
              <a className="underline underline-offset-2 hover:text-ink" href={REPO_URL}>
                clone the repository
              </a>
              {" to run a live search."}
            </>
          ) : health?.can_run ? (
            " Press Run search to start a live one."
          ) : (
            " Live runs are disabled on this server."
          )}
        </span>
      )}

      {!recorded && health && !health.can_run && (
        <span className="text-[12px] text-ink-3">
          No <code className="mono">NEBIUS_API_KEY</code> configured, so live runs are disabled.
        </span>
      )}
    </Strip>
  );
}

function Strip({ tone, children }: { tone: string; children: React.ReactNode }) {
  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-edge px-4 py-2.5 sm:px-6"
      style={{ background: `color-mix(in srgb, var(--${tone}) 7%, var(--surface))` }}
    >
      {children}
    </div>
  );
}
