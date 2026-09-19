"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useReplay } from "@/lib/replay";
import { ReplayBar } from "@/components/ReplayBar";
import { ActivityFeed } from "@/components/ActivityFeed";
import { CommandBar } from "@/components/CommandBar";
import { ContextStrip } from "@/components/ContextStrip";
import { EmptyState } from "@/components/EmptyState";
import { Inspector } from "@/components/Inspector";
import { SearchTree } from "@/components/SearchTree";
import { SpendStrip } from "@/components/SpendStrip";
import { useRun } from "@/lib/useRun";

export default function Page() {
  const { state, start, stop } = useRun();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  /* A link can point at one branch, not just one run. */
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("node");
    if (requested) setSelectedId(requested);
  }, []);

  const select = useCallback((id: string | null) => {
    setSelectedId(id);
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("node", id);
    else url.searchParams.delete("node");
    window.history.replaceState(null, "", url);
  }, []);

  // Replay only applies to a finished run; a live one is already happening.
  const replayable = !state.running && state.nodes.length > 1;
  const replay = useReplay(state.nodes, replayable);
  const shownNodes = replayable ? replay.nodes : state.nodes;

  const selected = useMemo(
    () => shownNodes.find((node) => node.id === selectedId) ?? null,
    [shownNodes, selectedId],
  );

  // While scrubbing, an empty canvas is a position in the replay, not an
  // absent run — showing "Nothing searched yet" there is a lie.
  const hasTree = shownNodes.length > 0 || (replayable && replay.cursor === 0);
  const showActivity = state.activity.length > 0 || state.running;

  return (
    <div className="flex h-dvh flex-col">
      <CommandBar
        health={state.health}
        running={state.running}
        stopping={state.stopping}
        onRun={(request) => {
          select(null);
          start(request);
        }}
        onStop={stop}
      />

      <ContextStrip
        health={state.health}
        result={state.result}
        recorded={state.recorded}
        running={state.running}
        stopping={state.stopping}
        error={state.error}
      />

      {/* Stacked below lg, side by side above it. `overflow-hidden` plus
          `min-h-0` on both children is what stops the panel growing to its
          content height and pushing through the strip below. */}
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
        <section
          className="relative min-h-[260px] min-w-0 flex-1 basis-1/2 lg:basis-auto"
          aria-label="Search tree"
        >
          {hasTree ? (
            <SearchTree
              nodes={shownNodes}
              winnerId={state.result?.winner_id ?? null}
              selectedId={selectedId}
              running={state.running}
              onSelect={(id) => select(id === selectedId ? null : id)}
            />
          ) : (
            <EmptyState running={state.running} />
          )}
        </section>

        {/* A third of the width. Code needs the room; the prose inside is
            capped separately so lines stay readable when the screen is wide. */}
        <aside className="flex min-h-0 w-full flex-1 basis-1/2 flex-col overflow-hidden border-t border-edge bg-surface lg:w-1/3 lg:min-w-[400px] lg:flex-none lg:basis-auto lg:border-t-0 lg:border-l">
          <div className="min-h-0 flex-1">
            <Inspector node={selected} result={state.result} onClose={() => select(null)} />
          </div>
          {showActivity && (
            <div className="h-[34%] max-h-[280px] min-h-[160px] shrink-0 border-t border-edge">
              <ActivityFeed activity={state.activity} running={state.running} />
            </div>
          )}
        </aside>
      </main>

      {replayable && (
        <ReplayBar
          ordered={replay.ordered}
          cursor={replay.cursor}
          total={replay.total}
          playing={replay.playing}
          speed={replay.speed}
          revealed={replay.revealed}
          onPlay={replay.play}
          onPause={replay.pause}
          onSeek={replay.seek}
          onStep={replay.step}
          onSpeed={replay.setSpeed}
        />
      )}

      <SpendStrip result={state.result} />
    </div>
  );
}
