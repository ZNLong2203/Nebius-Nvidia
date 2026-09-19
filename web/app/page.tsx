"use client";

import { useMemo, useState } from "react";
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

  const selected = useMemo(
    () => state.nodes.find((node) => node.id === selectedId) ?? null,
    [state.nodes, selectedId],
  );

  const hasTree = state.nodes.length > 0;
  const showActivity = state.activity.length > 0 || state.running;

  return (
    <div className="flex h-dvh flex-col">
      <CommandBar
        health={state.health}
        running={state.running}
        onRun={(request) => {
          setSelectedId(null);
          start(request);
        }}
        onStop={stop}
      />

      <ContextStrip
        health={state.health}
        result={state.result}
        recorded={state.recorded}
        running={state.running}
        error={state.error}
      />

      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <section
          className="relative min-h-[320px] min-w-0 flex-1 lg:min-h-0"
          aria-label="Search tree"
        >
          {hasTree ? (
            <SearchTree
              nodes={state.nodes}
              winnerId={state.result?.winner_id ?? null}
              selectedId={selectedId}
              running={state.running}
              onSelect={(id) => setSelectedId((current) => (current === id ? null : id))}
            />
          ) : (
            <EmptyState running={state.running} />
          )}
        </section>

        <aside className="flex w-full shrink-0 flex-col border-t border-edge bg-surface lg:w-[400px] lg:border-t-0 lg:border-l xl:w-[440px]">
          <div className="min-h-0 flex-1">
            <Inspector node={selected} result={state.result} onClose={() => setSelectedId(null)} />
          </div>
          {showActivity && (
            <div className="h-[34%] max-h-[280px] min-h-[160px] shrink-0 border-t border-edge">
              <ActivityFeed activity={state.activity} running={state.running} />
            </div>
          )}
        </aside>
      </main>

      <SpendStrip result={state.result} />
    </div>
  );
}
