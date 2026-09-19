"use client";

export function EmptyState({ running }: { running: boolean }) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-lg text-center">
        <Sketch />
        <h2 className="mt-6 text-[17px] font-semibold tracking-[-0.01em]">
          {running ? "Preparing the base checkpoint…" : "Nothing searched yet"}
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-2">
          {running
            ? "Dependencies are installing once. Every branch will fork the result, so this cost is paid a single time."
            : "Point Arborist at a repository whose tests fail. It prepares the environment once, then forks that checkpoint for every candidate patch — so rival theories are tested from an identical state and a regression costs nothing to abandon."}
        </p>
        {!running && (
          <p className="mono mt-4 text-[11.5px] text-ink-3">
            examples/broken-invoice — nine tests, four red, three unrelated bugs
          </p>
        )}
      </div>
    </div>
  );
}

/** The idea in one drawing: one trunk, four attempts, one survives. */
function Sketch() {
  return (
    <svg
      width="188"
      height="104"
      viewBox="0 0 188 104"
      aria-hidden
      className="mx-auto opacity-90"
    >
      {[
        { y: 18, tone: "var(--line-2)", dash: "4 4" },
        { y: 40, tone: "var(--critical)" },
        { y: 62, tone: "var(--good)" },
        { y: 84, tone: "var(--warning)" },
      ].map((branch, index) => (
        <g key={index}>
          <path
            d={`M40,52 C82,52 82,${branch.y} 124,${branch.y}`}
            fill="none"
            stroke={branch.tone}
            strokeWidth={branch.y === 62 ? 2 : 1.5}
            strokeDasharray={branch.dash}
            strokeLinecap="round"
            opacity={branch.y === 62 ? 1 : 0.55}
          />
          <rect
            x={124}
            y={branch.y - 7}
            width={46}
            height={14}
            rx={7}
            fill="var(--surface)"
            stroke={branch.tone}
            strokeWidth={branch.y === 62 ? 1.5 : 1}
            strokeDasharray={branch.dash}
            opacity={branch.y === 62 ? 1 : 0.6}
          />
        </g>
      ))}
      <rect x={10} y={42} width={30} height={20} rx={7} fill="var(--surface)" stroke="var(--line-2)" />
      <circle cx={25} cy={52} r={3} fill="var(--ink-3)" />
    </svg>
  );
}
