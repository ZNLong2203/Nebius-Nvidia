"use client";

import { REPLAY_SPEEDS, type Speed } from "@/lib/replay";
import { STATUS_META } from "@/lib/tree";
import type { SearchNode } from "@/lib/types";

const TONE_VAR: Record<string, string> = {
  good: "var(--good)",
  warning: "var(--warning)",
  critical: "var(--critical)",
  muted: "var(--ink-3)",
  accent: "var(--accent)",
};

/**
 * Scrub through a finished run.
 *
 * The track is not a plain progress bar: each tick is one branch, coloured by
 * how it turned out, so the shape of the search is legible before you press
 * anything — a row of blue with two red in it says what happened.
 */
export function ReplayBar({
  ordered,
  cursor,
  total,
  playing,
  speed,
  revealed,
  onPlay,
  onPause,
  onSeek,
  onStep,
  onSpeed,
}: {
  ordered: SearchNode[];
  cursor: number;
  total: number;
  playing: boolean;
  speed: Speed;
  revealed: SearchNode | null;
  onPlay: () => void;
  onPause: () => void;
  onSeek: (value: number) => void;
  onStep: (delta: number) => void;
  onSpeed: (value: Speed) => void;
}) {
  if (total <= 1) return null;

  const label =
    revealed === null
      ? "before the search started"
      : revealed.depth === 0
        ? "the starting state"
        : revealed.hypothesis?.title || revealed.note || "a candidate patch";

  const button =
    "grid size-7 place-items-center rounded-md text-[12px] text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink disabled:opacity-35";

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-edge bg-surface px-4 py-2.5 sm:px-6">
      <div className="flex items-center gap-0.5">
        <button type="button" onClick={() => onStep(-1)} disabled={cursor <= 0} aria-label="Previous branch" className={button}>
          ⏮
        </button>
        <button
          type="button"
          onClick={playing ? onPause : onPlay}
          aria-label={playing ? "Pause the replay" : "Replay the search"}
          className="grid size-8 place-items-center rounded-md text-[13px] transition-colors hover:bg-surface-2"
          style={{ color: "var(--accent)" }}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <button type="button" onClick={() => onStep(1)} disabled={cursor >= total} aria-label="Next branch" className={button}>
          ⏭
        </button>
      </div>

      {/* One tick per branch, coloured by outcome. */}
      <div className="flex min-w-[180px] flex-1 items-center gap-2">
        <div className="relative flex h-6 flex-1 items-center">
          <div className="flex w-full gap-[2px]">
            {ordered.map((node, index) => {
              const meta = STATUS_META[node.status] ?? STATUS_META.running;
              const reached = index < cursor;
              return (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => onSeek(index + 1)}
                  aria-label={`Step ${index + 1}: ${meta.label}`}
                  title={`${meta.label} — ${node.hypothesis?.title ?? "starting state"}`}
                  className="h-4 min-w-0 flex-1 rounded-[2px] transition-opacity"
                  style={{
                    background: TONE_VAR[meta.tone] ?? TONE_VAR.muted,
                    opacity: reached ? 1 : 0.22,
                  }}
                />
              );
            })}
          </div>
        </div>
        <span className="mono tnum shrink-0 text-[11px] text-ink-3">
          {cursor}/{total}
        </span>
      </div>

      <p className="min-w-0 flex-1 basis-full truncate text-[11.5px] text-ink-3 sm:basis-auto">
        {label}
      </p>

      <div className="flex items-center gap-0.5 rounded-md border border-edge p-0.5">
        {REPLAY_SPEEDS.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => onSpeed(value)}
            aria-pressed={speed === value}
            className="mono rounded px-1.5 py-0.5 text-[10.5px] transition-colors"
            style={{
              background: speed === value ? "var(--accent-wash)" : "transparent",
              color: speed === value ? "var(--accent)" : "var(--ink-3)",
            }}
          >
            {value}×
          </button>
        ))}
      </div>
    </div>
  );
}
