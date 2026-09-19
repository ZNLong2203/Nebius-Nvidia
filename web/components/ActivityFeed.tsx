"use client";

import { useEffect, useRef } from "react";
import { TIER_META } from "@/lib/tree";
import type { Activity } from "@/lib/useRun";
import { TierDot } from "./Primitives";

const ICON: Record<Activity["kind"], string> = {
  checkpoint: "◈",
  diagnosing: "◌",
  diagnosed: "⑂",
  search: "⌕",
  adjudicated: "⚖",
  error: "!",
  done: "✓",
};

/**
 * What the agent is doing, as it does it. This is where the model routing
 * becomes visible: which tier was asked, and what it decided.
 */
export function ActivityFeed({ activity, running }: { activity: Activity[]; running: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activity.length]);

  if (activity.length === 0 && !running) return null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
        <span className="eyebrow">Activity</span>
        {running && (
          <span className="ml-auto flex items-center gap-1.5 text-[11px] text-ink-3">
            <span className="size-1.5 animate-pulse rounded-full bg-[var(--accent)]" />
            live
          </span>
        )}
      </div>

      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-4 py-3">
        <ol className="space-y-2.5">
          {activity.map((item) => (
            <li key={item.id} className="flex gap-2.5">
              <span
                aria-hidden
                className="mono mt-[3px] w-3 shrink-0 text-center text-[11px]"
                style={{ color: item.kind === "error" ? "var(--critical)" : "var(--ink-3)" }}
              >
                {ICON[item.kind]}
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-[12.5px] text-ink">{item.text}</span>
                  {item.tier && (
                    <span className="inline-flex items-center gap-1 text-[10.5px] text-ink-3">
                      <TierDot tier={item.tier} />
                      {TIER_META[item.tier]?.label ?? item.tier}
                    </span>
                  )}
                </div>
                {item.detail && (
                  <p className="mt-0.5 line-clamp-3 text-[11.5px] leading-relaxed text-ink-3">
                    {item.detail}
                  </p>
                )}
              </div>
            </li>
          ))}
          {running && (
            <li className="flex gap-2.5">
              <span aria-hidden className="mono mt-[3px] w-3 shrink-0 text-center text-[11px] text-ink-3">
                ◌
              </span>
              <div className="h-3 w-32 shimmer rounded" />
            </li>
          )}
        </ol>
        <div ref={endRef} />
      </div>
    </div>
  );
}
