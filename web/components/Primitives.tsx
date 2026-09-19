"use client";

import type { ReactNode } from "react";

const TONE: Record<string, { fg: string; bg: string }> = {
  good: { fg: "var(--good)", bg: "color-mix(in srgb, var(--good) 13%, transparent)" },
  warning: { fg: "var(--warning)", bg: "color-mix(in srgb, var(--warning) 16%, transparent)" },
  critical: { fg: "var(--critical)", bg: "color-mix(in srgb, var(--critical) 13%, transparent)" },
  accent: { fg: "var(--accent)", bg: "var(--accent-wash)" },
  muted: { fg: "var(--ink-3)", bg: "color-mix(in srgb, var(--ink-3) 12%, transparent)" },
};

/**
 * Status never rides on colour alone: every badge carries an icon and a word,
 * so it survives colour-blindness, print and a washed-out projector.
 */
export function Badge({
  tone = "muted",
  icon,
  children,
}: {
  tone?: keyof typeof TONE | string;
  icon?: string;
  children: ReactNode;
}) {
  const { fg, bg } = TONE[tone] ?? TONE.muted;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold whitespace-nowrap"
      style={{ color: fg, background: bg }}
    >
      {icon && <span aria-hidden>{icon}</span>}
      {children}
    </span>
  );
}

/** A thin bar for "how much of the suite passes". Reads before any number does. */
export function Meter({
  value,
  total,
  tone = "accent",
  height = 4,
}: {
  value: number;
  total: number;
  tone?: keyof typeof TONE | string;
  height?: number;
}) {
  const pct = total > 0 ? Math.max(0, Math.min(1, value / total)) : 0;
  const { fg } = TONE[tone] ?? TONE.accent;
  return (
    <div
      className="w-full overflow-hidden rounded-full"
      style={{ height, background: "color-mix(in srgb, var(--ink-3) 22%, transparent)" }}
      role="img"
      aria-label={`${value} of ${total} tests passing`}
    >
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-out"
        style={{ width: `${pct * 100}%`, background: fg }}
      />
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="eyebrow">{label}</div>
      <div
        className="mt-0.5 truncate text-[19px] leading-tight font-semibold tnum"
        style={tone ? { color: TONE[tone]?.fg } : undefined}
      >
        {value}
      </div>
      {hint !== undefined && (
        <div className="mt-0.5 truncate text-[11.5px] text-ink-3">{hint}</div>
      )}
    </div>
  );
}

export function TierDot({ tier }: { tier: string }) {
  return (
    <span
      aria-hidden
      className="inline-block size-2 shrink-0 rounded-full"
      style={{ background: `var(--tier-${tier}, var(--ink-3))` }}
    />
  );
}

export function Card({
  children,
  className = "",
  ...rest
}: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-xl border border-edge bg-surface ${className}`}
      style={{ boxShadow: "var(--shadow-1)" }}
      {...rest}
    >
      {children}
    </div>
  );
}
