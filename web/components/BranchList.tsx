"use client";

import { loadFailure } from "@/lib/report";
import { STATUS_META, winningPathIds } from "@/lib/tree";
import type { SearchNode } from "@/lib/types";

const TONE_VAR: Record<string, string> = {
  good: "var(--good)",
  warning: "var(--warning)",
  critical: "var(--critical)",
  muted: "var(--ink-3)",
  accent: "var(--accent)",
};

/**
 * The tree as a list, for screens too narrow to read it.
 *
 * On a phone the whole tree fits only at a zoom where no card can be read,
 * so the shape is shown there and the words here: every state in search
 * order, indented by depth, each one a tap away from its patch.
 */
export function BranchList({
  nodes,
  winnerId,
  selectedId,
  onSelect,
}: {
  nodes: SearchNode[];
  winnerId: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (nodes.length < 2) return null;
  const winning = winningPathIds(nodes, winnerId);
  const children = new Map<string | null, SearchNode[]>();
  for (const node of nodes) children.set(node.parent_id, [...(children.get(node.parent_id) ?? []), node]);
  const ordered: SearchNode[] = [];
  const walk = (node: SearchNode) => {
    ordered.push(node);
    for (const child of children.get(node.id) ?? []) walk(child);
  };
  for (const root of children.get(null) ?? []) walk(root);

  return (
    <nav aria-label="Every branch, as a list" className="border-t border-edge bg-surface px-4 py-3">
      <h2 className="eyebrow mb-2">Every branch · tap for its change</h2>
      <ul className="space-y-1">
        {ordered.map((node) => {
          const meta = STATUS_META[node.status] ?? STATUS_META.running;
          const tone = TONE_VAR[meta.tone] ?? TONE_VAR.muted;
          const title = node.depth === 0 ? "Starting state" : node.hypothesis?.title || node.note || "patch";
          const passing = !node.report
            ? "—"
            : loadFailure(node.report, node.stdout_tail)
              ? "no load"
              : `${node.report.passed}/${node.report.total}`;
          const selected = node.id === selectedId;
          return (
            <li key={node.id} style={{ paddingLeft: `${Math.min(node.depth, 5) * 14}px` }}>
              <button
                type="button"
                onClick={() => onSelect(node.id)}
                aria-current={selected ? "true" : undefined}
                className="flex w-full items-start gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-colors"
                style={{
                  borderColor: selected ? "var(--accent)" : "var(--line-2)",
                  background: winning.has(node.id) && node.depth > 0
                    ? "color-mix(in srgb, var(--good) 7%, transparent)"
                    : "var(--surface)",
                }}
              >
                <span aria-hidden className="mt-[3px] h-3.5 w-1 shrink-0 rounded-full" style={{ background: tone }} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="text-[11px] font-semibold" style={{ color: tone }}>
                      {meta.icon} {meta.label}
                    </span>
                    <span className="mono tnum text-[11px] text-ink-3">{passing}</span>
                  </span>
                  <span className="mt-0.5 block text-[13px] leading-snug text-ink">{title}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
