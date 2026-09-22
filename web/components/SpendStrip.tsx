"use client";

import { TIER_META } from "@/lib/tree";
import type { RunResult } from "@/lib/types";
import { Stat, TierDot } from "./Primitives";

/**
 * The cost argument, made visible. Nano does the wide disposable work, Super
 * the reasoning, Ultra almost nothing — and the bars say so at a glance.
 */
export function SpendStrip({ result }: { result: RunResult | null }) {
  const usage = result?.usage;
  const stats = result?.stats;
  const tiers = ["nano", "super", "ultra"] as const;
  const totals = tiers.map((tier) => usage?.by_tier?.[tier]?.total_tokens ?? 0);
  const max = Math.max(1, ...totals);
  const grand = totals.reduce((sum, value) => sum + value, 0);

  return (
    <div className="grid gap-x-8 gap-y-4 border-t border-edge bg-surface px-4 py-3.5 sm:px-6 lg:grid-cols-[minmax(320px,1fr)_auto]">
      <div className="min-w-0">
        <div className="eyebrow mb-2">Nemotron 3 spend</div>
        <div className="space-y-1.5">
          {tiers.map((tier, index) => {
            const usageForTier = usage?.by_tier?.[tier];
            const tokens = totals[index];
            return (
              <div key={tier} className="grid grid-cols-[92px_1fr_auto] items-center gap-3">
                <span className="flex items-center gap-2 text-[12px] text-ink-2">
                  <TierDot tier={tier} />
                  {TIER_META[tier].label}
                </span>
                <div
                  className="h-1.5 overflow-hidden rounded-full"
                  style={{ background: "color-mix(in srgb, var(--ink-3) 18%, transparent)" }}
                >
                  <div
                    className="h-full rounded-full transition-[width] duration-700 ease-out"
                    style={{
                      width: `${(tokens / max) * 100}%`,
                      background: `var(--tier-${tier})`,
                    }}
                  />
                </div>
                <span className="mono tnum w-[110px] text-right text-[11.5px] text-ink-3">
                  {usageForTier?.calls ?? 0} calls · {tokens.toLocaleString()}
                </span>
              </div>
            );
          })}
        </div>
        {grand > 0 && (
          <p className="mt-2 text-[11.5px] text-ink-3">
            {grand.toLocaleString()} tokens total
            {typeof usage?.cost_usd === "number" && usage.cost_usd > 0
              ? ` · $${usage.cost_usd.toFixed(2)} at list price`
              : ""}
            . Most branches are discarded, so the discarded work is the cheap work.
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
        <Stat
          label="Branches"
          value={stats?.patches_evaluated ?? "—"}
          hint={
            stats?.invalid_patches
              ? `${stats.invalid_patches} never reached the sandbox`
              : "patches evaluated"
          }
        />
        <Stat
          label="Sandbox runs"
          value={stats?.sandbox_executions ?? "—"}
          hint={stats?.setup_seconds ? `setup ${stats.setup_seconds}s, paid once` : " "}
        />
        {stats?.setup_seconds_saved ? (
          <Stat
            label="Saved by forking"
            value={`${stats.setup_seconds_saved}s`}
            hint="setup not re-run"
            tone="good"
          />
        ) : null}
        <Stat
          label="Wall time"
          value={stats?.wall_seconds ? `${Math.round(stats.wall_seconds)}s` : "—"}
          hint={stats?.branching === false ? "linear baseline" : "branching on"}
        />
      </div>
    </div>
  );
}
