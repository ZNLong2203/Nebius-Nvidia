"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  GAP_X,
  NODE_H,
  NODE_W,
  STATUS_META,
  ancestryIds,
  layoutTree,
  winningPathIds,
} from "@/lib/tree";
import type { SearchNode } from "@/lib/types";
import { Meter } from "./Primitives";

const TONE_VAR: Record<string, string> = {
  good: "var(--good)",
  warning: "var(--warning)",
  critical: "var(--critical)",
  muted: "var(--ink-3)",
  accent: "var(--accent)",
};

export function SearchTree({
  nodes,
  winnerId,
  selectedId,
  running,
  onSelect,
}: {
  nodes: SearchNode[];
  winnerId: string | null;
  selectedId: string | null;
  running: boolean;
  onSelect: (id: string) => void;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const seen = useRef(new Set<string>());

  const winning = useMemo(() => winningPathIds(nodes, winnerId), [nodes, winnerId]);
  const layout = useMemo(() => layoutTree(nodes, winning), [nodes, winning]);
  const lit = useMemo(() => ancestryIds(nodes, hovered), [nodes, hovered]);

  /* Follow the frontier while the search is live, so growth stays in view. */
  useEffect(() => {
    if (!running || !scrollRef.current || layout.placed.length === 0) return;
    const deepest = Math.max(...layout.placed.map((p) => p.x));
    const element = scrollRef.current;
    const target = deepest + NODE_W + GAP_X - element.clientWidth;
    if (target > element.scrollLeft) {
      element.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
    }
  }, [layout, running]);

  if (layout.placed.length === 0) return null;

  return (
    <div ref={scrollRef} className="scroll-thin flex h-full w-full overflow-auto">
      <svg
        className="m-auto"
        width={layout.width}
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        role="tree"
        aria-label="Search tree of repository states"
      >
        <g>
          {layout.edges.map((edge) => {
            const x1 = edge.from.x + NODE_W;
            const y1 = edge.from.y + NODE_H / 2;
            const x2 = edge.to.x;
            const y2 = edge.to.y + NODE_H / 2;
            const mid = (x1 + x2) / 2;
            const length = Math.hypot(x2 - x1, y2 - y1) + Math.abs(y2 - y1);
            const isLit = lit.has(edge.to.node.id) && lit.has(edge.from.node.id);
            const fresh = !seen.current.has(edge.id);
            return (
              <path
                key={edge.id}
                className={`edge edge--${isLit ? "lit" : edge.kind} ${fresh ? "edge--enter" : ""}`}
                style={{ "--len": length } as React.CSSProperties}
                d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`}
              />
            );
          })}
        </g>

        <g>
          {layout.placed.map(({ node, x, y }) => {
            const meta = STATUS_META[node.status] ?? STATUS_META.running;
            const tone = TONE_VAR[meta.tone] ?? TONE_VAR.muted;
            const selected = selectedId === node.id;
            const dimmed =
              hovered !== null && !lit.has(node.id) ? 0.34 : node.status === "invalid" ? 0.72 : 1;
            const fresh = !seen.current.has(node.id);
            seen.current.add(node.id);

            const passing = node.report ? `${node.report.passed}/${node.report.total}` : "—";
            const title =
              node.depth === 0
                ? "Starting state"
                : node.hypothesis?.title || node.explanation || node.note || "patch";

            return (
              <g
                key={node.id}
                transform={`translate(${x},${y})`}
                className={fresh ? "node-enter" : undefined}
                style={{ opacity: dimmed, transition: "opacity 180ms ease" }}
                role="treeitem"
                aria-selected={selected}
                aria-label={`${meta.label}: ${title}, ${passing} tests passing`}
                tabIndex={0}
                onMouseEnter={() => setHovered(node.id)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(node.id)}
                onBlur={() => setHovered(null)}
                onClick={() => onSelect(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(node.id);
                  }
                }}
                cursor="pointer"
              >
                {node.status === "green" && (
                  <rect
                    className="pulse"
                    width={NODE_W}
                    height={NODE_H}
                    rx={13}
                    fill="none"
                    stroke="var(--good)"
                    strokeWidth={2}
                  />
                )}

                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={12}
                  fill="var(--surface)"
                  stroke={
                    selected
                      ? "var(--accent)"
                      : node.status === "green"
                        ? "var(--good)"
                        : "var(--line-2)"
                  }
                  strokeWidth={selected || node.status === "green" ? 2 : 1}
                  strokeDasharray={node.status === "invalid" ? "5 4" : undefined}
                  style={{ filter: selected ? "drop-shadow(0 6px 18px rgba(0,0,0,.22))" : undefined }}
                />
                <rect width={4} height={NODE_H} rx={2} fill={tone} />

                <foreignObject x={14} y={10} width={NODE_W - 28} height={NODE_H - 20}>
                  <div className="flex h-full flex-col justify-between">
                    <div className="flex items-baseline justify-between gap-2">
                      <span
                        className="truncate text-[11px] font-semibold"
                        style={{ color: tone }}
                      >
                        <span aria-hidden>{meta.icon}</span> {meta.label}
                      </span>
                      <span className="mono tnum shrink-0 text-[11px] text-ink-2">{passing}</span>
                    </div>

                    <div
                      className="text-[12.5px] leading-[1.3] font-medium text-ink"
                      style={{
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {title}
                    </div>

                    {node.report ? (
                      <Meter
                        value={node.report.passed}
                        total={node.report.total}
                        tone={meta.tone}
                        height={3}
                      />
                    ) : (
                      <div className="h-[3px] rounded-full bg-[color-mix(in_srgb,var(--ink-3)_22%,transparent)]" />
                    )}
                  </div>
                </foreignObject>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
