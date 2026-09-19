"use client";

import { STATUS_META } from "@/lib/tree";
import type { RunResult, SearchNode } from "@/lib/types";
import { CodeBlock, DiffBlock, TestOutput } from "./Code";
import { Collapsible } from "./Collapsible";
import { Badge, Meter } from "./Primitives";

export function Inspector({
  node,
  result,
  onClose,
}: {
  node: SearchNode | null;
  result: RunResult | null;
  onClose: () => void;
}) {
  if (!node) return <Explainer result={result} />;

  const meta = STATUS_META[node.status] ?? STATUS_META.running;
  const report = node.report;
  const title =
    node.depth === 0 ? "Starting state" : node.hypothesis?.title || node.note || "Candidate patch";

  return (
    <div className="flex h-full flex-col">
      {/* Sticky, and always bordered, so scrolled content never slides under it
          without an edge to mark where the header ends. */}
      <header className="sticky top-0 z-10 shrink-0 border-b border-edge bg-surface px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Badge tone={meta.tone} icon={meta.icon}>
              {meta.label}
            </Badge>
            <h2 className="mt-2 max-w-[52ch] text-[16.5px] leading-snug font-semibold tracking-[-0.015em]">
              {title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close inspector"
            className="shrink-0 rounded-lg border border-edge px-2 py-1 text-[12px] text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            ✕
          </button>
        </div>

        <div className="mono mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-ink-3">
          {[
            `depth ${node.depth}`,
            node.checkpoint_id ? `checkpoint ${node.checkpoint_id.slice(0, 10)}` : null,
            node.wall_seconds > 0 ? `${node.wall_seconds.toFixed(1)}s` : null,
            node.model_tier ? `patch by ${node.model_tier}` : null,
          ]
            .filter(Boolean)
            .map((item, index) => (
              <span key={item as string} className="flex items-center gap-2">
                {index > 0 && <span aria-hidden className="text-line-2">·</span>}
                {item}
              </span>
            ))}
        </div>
      </header>

      {/* Keyed on the node: selecting a different branch resets the scroll
          position and every collapsed section, rather than showing the new
          node through the previous one's reading position. */}
      <div key={node.id} className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {/* At a glance: the three things worth knowing before any prose. */}
        {report && (
          <div className="mb-5 rounded-xl border border-edge bg-surface-2 px-4 py-3">
            <div className="flex items-baseline justify-between gap-3">
              <span className="tnum text-[24px] leading-none font-semibold">
                {report.passed}
                <span className="text-[16px] text-ink-3">/{report.total}</span>
              </span>
              <span className="eyebrow">tests passing</span>
            </div>
            <div className="mt-2.5">
              <Meter value={report.passed} total={report.total} tone={meta.tone} height={6} />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {node.fixed.length > 0 && (
                <Badge tone="good" icon="✓">
                  fixed {node.fixed.length}
                </Badge>
              )}
              {node.regressions.length > 0 && (
                <Badge tone="critical" icon="↓">
                  broke {node.regressions.length}
                </Badge>
              )}
              {report.failed > 0 && (
                <Badge tone="muted" icon="•">
                  {report.failed} still failing
                </Badge>
              )}
              {report.green && (
                <Badge tone="good" icon="✓">
                  suite is green
                </Badge>
              )}
            </div>
          </div>
        )}

        {node.note && (
          <div
            className="mb-5 rounded-lg border px-3 py-2.5 text-[12px] leading-relaxed"
            style={{
              borderColor: "color-mix(in srgb, var(--warning) 40%, transparent)",
              background: "color-mix(in srgb, var(--warning) 8%, transparent)",
            }}
          >
            <span className="eyebrow mb-1 block">Why it stopped here</span>
            <span className="mono text-ink-2">{node.note}</span>
          </div>
        )}

        {node.regressions.length > 0 && (
          <Collapsible title="Tests it broke" count={node.regressions.length}>
            <p className="mb-2 max-w-[68ch] text-[12.5px] leading-relaxed text-ink-2">
              These passed at the parent state. That is what made this branch a dead end — and
              because nothing was mutated, abandoning it cost nothing.
            </p>
            <TestList items={node.regressions} tone="critical" />
          </Collapsible>
        )}

        {node.fixed.length > 0 && (
          <Collapsible title="Tests it fixed" count={node.fixed.length}>
            <TestList items={node.fixed} tone="good" />
          </Collapsible>
        )}

        {node.diagnosis && (
          <Collapsible title="The diagnosis">
            <p className="max-w-[68ch] text-[13px] leading-relaxed text-ink-2">{node.diagnosis}</p>
          </Collapsible>
        )}

        {node.hypothesis?.rationale && (
          <Collapsible title="Why this theory">
            <p className="max-w-[68ch] text-[13px] leading-relaxed text-ink-2">{node.hypothesis.rationale}</p>
          </Collapsible>
        )}

        {node.explanation && (
          <Collapsible title="What the patch does">
            <p className="max-w-[68ch] text-[13px] leading-relaxed text-ink-2">{node.explanation}</p>
          </Collapsible>
        )}

        {node.edits.length > 0 && (
          <Collapsible
            title={node.edits.length === 1 ? "The edit" : "The edits"}
            count={node.edits.length > 1 ? node.edits.length : undefined}
          >
            <div className="space-y-3">
              {node.edits.map((edit, index) =>
                edit.new_content !== null ? (
                  <CodeBlock key={index} source={edit.new_content} path={edit.path} />
                ) : (
                  <DiffBlock
                    key={index}
                    path={edit.path}
                    removed={edit.search ?? ""}
                    added={edit.replace ?? ""}
                  />
                ),
              )}
            </div>
          </Collapsible>
        )}

        {report && report.failed_ids.length > 0 && (
          <Collapsible
            title="Still failing"
            count={report.failed_ids.length}
            defaultOpen={report.failed_ids.length <= 4}
          >
            <TestList items={report.failed_ids} tone="muted" />
          </Collapsible>
        )}

        {node.stdout_tail && (
          <Collapsible title="Test output" defaultOpen={false}>
            <TestOutput text={node.stdout_tail.slice(-3000)} />
          </Collapsible>
        )}
      </div>
    </div>
  );
}

function TestList({ items, tone }: { items: string[]; tone: string }) {
  const colour =
    tone === "good" ? "var(--good)" : tone === "critical" ? "var(--critical)" : "var(--ink-3)";

  // Every id in a list usually shares a suite. Printing it once buys each name
  // the width it needs to sit on one line.
  const suites = new Set(items.map((item) => (item.includes("::") ? item.split("::")[0] : "")));
  const commonSuite = suites.size === 1 ? [...suites][0] : "";
  const names = items.map((item) =>
    commonSuite && item.startsWith(`${commonSuite}::`) ? item.slice(commonSuite.length + 2) : item,
  );

  return (
    <div>
      {commonSuite && <div className="mono mb-1 text-[10.5px] text-ink-3">{commonSuite}</div>}
      <ul className="space-y-1">
        {names.map((name, index) => (
          <li key={items[index]} className="flex gap-2 text-[11.5px] leading-relaxed">
            <span
              aria-hidden
              className="mt-[7px] h-1 w-1 shrink-0 rounded-full"
              style={{ background: colour }}
            />
            <span className="mono min-w-0 text-ink-2 [overflow-wrap:anywhere]" title={items[index]}>
              {name}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Shown when nothing is selected: teach the mental model rather than sit blank. */
function Explainer({ result }: { result: RunResult | null }) {
  return (
    <div className="scroll-thin h-full overflow-y-auto px-5 py-5">
      <h2 className="text-[15.5px] font-semibold tracking-[-0.01em]">How to read this</h2>
      <p className="mt-2 max-w-[68ch] text-[13px] leading-relaxed text-ink-2">
        Every card is an <strong className="text-ink">immutable repository state</strong>. Moving
        right means a patch was applied <em>on top of</em> the one before it. Cards stacked
        vertically are rival theories of the same failure, each tested from the identical
        checkpoint — which is the only reason their scores can be compared.
      </p>

      <ul className="mt-4 space-y-2.5">
        {[
          ["var(--good)", "The branch that got the whole suite green."],
          ["var(--accent)", "Improved: fixed tests without breaking any. Worth building on."],
          ["var(--warning)", "Changed nothing. Kept, but not promising."],
          ["var(--critical)", "Broke a test that used to pass. Abandoned at no cost."],
          ["var(--ink-3)", "The patch would not apply. It never reached the sandbox."],
        ].map(([colour, text]) => (
          <li key={text} className="flex max-w-[68ch] gap-2.5 text-[13px] text-ink-2">
            <span
              aria-hidden
              className="mt-[7px] h-[3px] w-4 shrink-0 rounded-full"
              style={{ background: colour }}
            />
            <span>{text}</span>
          </li>
        ))}
      </ul>

      <p className="mt-4 max-w-[68ch] rounded-lg bg-surface-2 px-3 py-2.5 text-[12.5px] leading-relaxed text-ink-2">
        Hover a card to light up everything it was built on. Select one for its patch, the tests it
        fixed, and the tests it broke.
      </p>

      {result?.diff && (
        <div className="mt-6">
          <h3 className="eyebrow mb-2">The resulting patch</h3>
          <UnifiedDiff diff={result.diff} />
        </div>
      )}
    </div>
  );
}

/** The final diff, split per file so each one is separately readable. */
function UnifiedDiff({ diff }: { diff: string }) {
  const files: { path: string; removed: string[]; added: string[] }[] = [];
  let current: (typeof files)[number] | null = null;

  for (const line of diff.split("\n")) {
    if (line.startsWith("--- a/")) {
      current = { path: line.slice(6), removed: [], added: [] };
      files.push(current);
      continue;
    }
    if (!current || line.startsWith("+++ ") || line.startsWith("@@")) continue;
    if (line.startsWith("-")) current.removed.push(line.slice(1));
    else if (line.startsWith("+")) current.added.push(line.slice(1));
  }

  if (files.length === 0) return null;

  return (
    <div className="space-y-3">
      {files.map((file) => (
        <DiffBlock
          key={file.path}
          path={file.path}
          removed={file.removed.join("\n")}
          added={file.added.join("\n")}
        />
      ))}
    </div>
  );
}
