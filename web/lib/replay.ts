"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SearchNode } from "./types";

export interface ReplayStep {
  /** Nodes visible at this step. */
  nodes: SearchNode[];
  /** The node this step revealed, if any. */
  revealed: SearchNode | null;
  depth: number;
}

const SPEEDS = [0.5, 1, 2, 4] as const;
export type Speed = (typeof SPEEDS)[number];
export const REPLAY_SPEEDS = SPEEDS;

const BASE_INTERVAL = 900;

/**
 * Play a finished run back one branch at a time.
 *
 * A recorded run arrives as a finished tree, which shows the answer but not the
 * search. Reconstructing the order the nodes were created in turns it back into
 * something that happens -- which is the only way to see the thing the project
 * is actually about, without waiting several minutes for a live run.
 *
 * The order is breadth-first by depth, which is the order the search expands
 * in: every sibling of a level is evaluated before the winner of that level is
 * forked.
 */
export function useReplay(allNodes: SearchNode[], enabled: boolean) {
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const ordered = useMemo(() => {
    if (allNodes.length === 0) return [];
    const byParent = new Map<string | null, SearchNode[]>();
    for (const node of allNodes) {
      const list = byParent.get(node.parent_id) ?? [];
      list.push(node);
      byParent.set(node.parent_id, list);
    }
    const out: SearchNode[] = [];
    let level = byParent.get(null) ?? [];
    while (level.length > 0) {
      out.push(...level);
      level = level.flatMap((node) => byParent.get(node.id) ?? []);
    }
    // Anything unreachable from a root still belongs on the end.
    for (const node of allNodes) if (!out.includes(node)) out.push(node);
    return out;
  }, [allNodes]);

  const total = ordered.length;

  /* A new run resets the playhead to the end: a finished tree shows whole. */
  useEffect(() => {
    setCursor(total);
    setPlaying(false);
  }, [total]);

  useEffect(() => {
    if (!playing || !enabled) return;
    if (cursor >= total) {
      setPlaying(false);
      return;
    }
    timer.current = setTimeout(() => setCursor((c) => Math.min(total, c + 1)), BASE_INTERVAL / speed);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [playing, enabled, cursor, total, speed]);

  const visible = useMemo(() => ordered.slice(0, cursor), [ordered, cursor]);
  const revealed = cursor > 0 ? (ordered[cursor - 1] ?? null) : null;

  const play = useCallback(() => {
    // Replaying from the end starts over rather than doing nothing.
    setCursor((c) => (c >= total ? 1 : c));
    setPlaying(true);
  }, [total]);

  const pause = useCallback(() => setPlaying(false), []);
  const seek = useCallback((value: number) => {
    setPlaying(false);
    setCursor(value);
  }, []);
  const step = useCallback(
    (delta: number) => {
      setPlaying(false);
      setCursor((c) => Math.max(0, Math.min(total, c + delta)));
    },
    [total],
  );

  return {
    /** The BFS order the ticks and the playhead both index into. */
    ordered,
    nodes: cursor >= total ? allNodes : visible,
    revealed,
    cursor,
    total,
    playing,
    speed,
    setSpeed,
    play,
    pause,
    seek,
    step,
    atEnd: cursor >= total,
  };
}
