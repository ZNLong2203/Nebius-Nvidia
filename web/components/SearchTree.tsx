"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { NODE_H, NODE_W, STATUS_META, ancestryIds, layoutTree, winningPathIds } from "@/lib/tree";
import type { SearchNode } from "@/lib/types";
import { MAX_K, MIN_K, useViewport } from "@/lib/viewport";
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
  const containerRef = useRef<HTMLDivElement>(null);
  const seen = useRef(new Set<string>());

  const winning = useMemo(() => winningPathIds(nodes, winnerId), [nodes, winnerId]);
  const layout = useMemo(() => layoutTree(nodes, winning), [nodes, winning]);
  const lit = useMemo(() => ancestryIds(nodes, hovered), [nodes, hovered]);

  const { view, dragging, fit, zoomBy, panBy, onPointerDown, consumedDrag } = useViewport(
    containerRef,
    layout,
  );

  /* Keyboard steering, once the canvas has focus. */
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const step = event.shiftKey ? 160 : 60;
      switch (event.key) {
        case "ArrowLeft": panBy(step, 0); break;
        case "ArrowRight": panBy(-step, 0); break;
        case "ArrowUp": panBy(0, step); break;
        case "ArrowDown": panBy(0, -step); break;
        case "+": case "=": zoomBy(1.25); break;
        case "-": case "_": zoomBy(0.8); break;
        case "0": fit(true); break;
        default: return;
      }
      event.preventDefault();
    };
    element.addEventListener("keydown", onKeyDown);
    return () => element.removeEventListener("keydown", onKeyDown);
  }, [panBy, zoomBy, fit]);

  // Below this zoom the card text is noise rather than information, so the
  // nodes drop to their shape: status colour and how much of the suite passes.
  // Zoomed out you are reading the search, not the patches.
  const detailed = view.k >= 0.45;

  if (layout.placed.length === 0) return null;

  return (
    <div className="relative h-full w-full overflow-hidden">
      <div
        ref={containerRef}
        tabIndex={0}
        role="application"
        aria-label="Search tree. Drag to pan, ctrl or command and scroll to zoom, 0 to fit."
        onPointerDown={onPointerDown}
        className="h-full w-full touch-none outline-none"
        style={{ cursor: dragging ? "grabbing" : "grab" }}
      >
        <svg
          width="100%"
          height="100%"
          role="tree"
          aria-label="Search tree of repository states"
          className="block select-none"
        >
          <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
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
                    vectorEffect="non-scaling-stroke"
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
                  hovered !== null && !lit.has(node.id)
                    ? 0.34
                    : node.status === "invalid"
                      ? 0.72
                      : 1;
                const fresh = !seen.current.has(node.id);
                seen.current.add(node.id);

                const passing = node.report ? `${node.report.passed}/${node.report.total}` : "—";
                const title =
                  node.depth === 0
                    ? "Starting state"
                    : node.hypothesis?.title || node.explanation || node.note || "patch";

                return (
                  // Two groups on purpose: the outer one carries the layout
                  // position as an SVG attribute, the inner one is animated by
                  // CSS. A CSS `transform` overrides the presentation
                  // attribute, so animating the positioned group made every
                  // node enter at the canvas origin and snap into place.
                  <g
                    key={node.id}
                    transform={`translate(${x},${y})`}
                    role="treeitem"
                    aria-selected={selected}
                    aria-label={`${meta.label}: ${title}, ${passing} tests passing`}
                    tabIndex={0}
                    cursor="pointer"
                    onMouseEnter={() => setHovered(node.id)}
                    onMouseLeave={() => setHovered(null)}
                    onFocus={() => setHovered(node.id)}
                    onBlur={() => setHovered(null)}
                    onClick={() => {
                      if (consumedDrag()) return; // the pointer was panning, not picking
                      onSelect(node.id);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelect(node.id);
                      }
                    }}
                  >
                    <g
                      className={fresh ? "node-enter" : undefined}
                      style={{ opacity: dimmed, transition: "opacity 180ms ease" }}
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
                        vectorEffect="non-scaling-stroke"
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
                      vectorEffect="non-scaling-stroke"
                      style={{
                        filter: selected ? "drop-shadow(0 6px 18px rgba(0,0,0,.22))" : undefined,
                      }}
                    />
                    <rect width={4} height={NODE_H} rx={2} fill={tone} />

                    {!detailed && node.report && (
                      <>
                        <rect
                          x={16}
                          y={NODE_H / 2 - 5}
                          width={NODE_W - 32}
                          height={10}
                          rx={5}
                          fill="color-mix(in srgb, var(--ink-3) 22%, transparent)"
                        />
                        <rect
                          x={16}
                          y={NODE_H / 2 - 5}
                          width={
                            ((NODE_W - 32) * node.report.passed) / Math.max(1, node.report.total)
                          }
                          height={10}
                          rx={5}
                          fill={tone}
                        />
                      </>
                    )}

                    {detailed && (
                    <foreignObject x={14} y={10} width={NODE_W - 28} height={NODE_H - 20}>
                      <div className="flex h-full flex-col justify-between">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="truncate text-[11px] font-semibold" style={{ color: tone }}>
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
                    )}
                    </g>
                  </g>
                );
              })}
            </g>
          </g>
        </svg>
      </div>

      <ViewportControls
        scale={view.k}
        running={running}
        onZoomIn={() => zoomBy(1.25)}
        onZoomOut={() => zoomBy(0.8)}
        onFit={() => fit(true)}
      />
    </div>
  );
}

function ViewportControls({
  scale,
  running,
  onZoomIn,
  onZoomOut,
  onFit,
}: {
  scale: number;
  running: boolean;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
}) {
  const button =
    "grid size-7 place-items-center text-[13px] text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink disabled:opacity-35 disabled:hover:bg-transparent";

  return (
    <div className="pointer-events-none absolute right-4 bottom-4 flex flex-col items-end gap-2">
      <p className="hidden text-[10.5px] text-ink-3 sm:block">
        drag to pan · ⌘/ctrl + scroll to zoom · 0 to fit
      </p>
      <div
        className="pointer-events-auto flex items-center overflow-hidden rounded-lg border border-edge bg-surface"
        style={{ boxShadow: "var(--shadow-2)" }}
      >
        <button type="button" onClick={onZoomOut} disabled={scale <= MIN_K + 0.001} aria-label="Zoom out" className={button}>
          −
        </button>
        <span className="mono tnum w-11 border-x border-edge py-1 text-center text-[10.5px] text-ink-3">
          {Math.round(scale * 100)}%
        </span>
        <button type="button" onClick={onZoomIn} disabled={scale >= MAX_K - 0.001} aria-label="Zoom in" className={button}>
          +
        </button>
        <button
          type="button"
          onClick={onFit}
          aria-label="Fit the tree to the view"
          title={running ? "Fit, and resume following the search" : "Fit the tree to the view"}
          className={`${button} border-l border-edge px-1 text-[11px]`}
        >
          ⤢
        </button>
      </div>
    </div>
  );
}
