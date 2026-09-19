"use client";

import { STATUS_META } from "@/lib/tree";
import type { RunResult, SearchNode } from "@/lib/types";
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

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-3 border-b border-edge px-5 py-4">
        <div className="min-w-0">
          <Badge tone={meta.tone} icon={meta.icon}>
            {meta.label}
          </Badge>
          <h2 className="mt-2 text-[15px] leading-snug font-semibold tracking-[-0.01em]">
            {node.depth === 0
              ? "Starting state"
              : node.hypothesis?.title || node.note || "Candidate patch"}
          </h2>
          <p className="mono mt-1 text-[11px] text-ink-3">
            depth {node.depth}
            {node.checkpoint_id && ` · checkpoint ${node.checkpoint_id.slice(0, 12)}`}
            {node.wall_seconds > 0 && ` · ${node.wall_seconds}s`}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close inspector"
          className="shrink-0 rounded-lg border border-edge px-2 py-1 text-[13px] text-ink-3 transition-colors hover:bg-surface-2"
        >
          ✕
        </button>
      </div>

      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {report && (
          <Section title="Tests">
            <div className="flex items-baseline justify-between gap-3">
              <span className="tnum text-[22px] font-semibold">
                {report.passed}
                <span className="text-ink-3">/{report.total}</span>
              </span>
              <span className="text-[12px] text-ink-2">
                {report.failed > 0 && `${report.failed} failed`}
                {report.errors > 0 && ` · ${report.errors} errored`}
              </span>
            </div>
            <div className="mt-2">
              <Meter value={report.passed} total={report.total} tone={meta.tone} height={6} />
            </div>
          </Section>
        )}

        {node.fixed.length > 0 && (
          <Section title="Fixed">
            <TestList items={node.fixed} tone="good" />
          </Section>
        )}

        {node.regressions.length > 0 && (
          <Section title="Broke">
            <p className="mb-2 text-[12.5px] text-ink-2">
              These passed at the parent state. That is what made this branch a dead end.
            </p>
            <TestList items={node.regressions} tone="critical" />
          </Section>
        )}

        {report && report.failed_ids.length > 0 && (
          <Section title="Still failing">
            <TestList items={report.failed_ids} tone="muted" />
          </Section>
        )}

        {node.diagnosis && (
          <Section title="Diagnosis">
            <p className="text-[12.5px] leading-relaxed text-ink-2">{node.diagnosis}</p>
          </Section>
        )}

        {node.hypothesis?.rationale && (
          <Section title="Why this theory">
            <p className="text-[12.5px] leading-relaxed text-ink-2">{node.hypothesis.rationale}</p>
          </Section>
        )}

        {node.explanation && (
          <Section title="What the patch does">
            <p className="text-[12.5px] leading-relaxed text-ink-2">{node.explanation}</p>
          </Section>
        )}

        {node.note && (
          <Section title="Note">
            <p className="mono rounded-lg bg-surface-2 px-3 py-2 text-[11.5px] leading-relaxed text-ink-2">
              {node.note}
            </p>
          </Section>
        )}

        {node.edits.length > 0 && (
          <Section title={node.edits.length === 1 ? "The edit" : `${node.edits.length} edits`}>
            {node.edits.map((edit, index) => (
              <div key={index} className="mb-3 last:mb-0">
                <div className="mono mb-1.5 text-[11px] text-ink-3">{edit.path}</div>
                <Diff edit={edit} />
              </div>
            ))}
          </Section>
        )}

        {node.stdout_tail && (
          <Section title="Test output">
            <pre className="mono scroll-thin max-h-72 overflow-auto rounded-lg border border-edge bg-plane p-3 text-[11px] leading-relaxed whitespace-pre-wrap text-ink-2">
              {node.stdout_tail.slice(-2500)}
            </pre>
          </Section>
        )}
      </div>
    </div>
  );
}

function Diff({ edit }: { edit: { search: string | null; replace: string | null; new_content: string | null } }) {
  if (edit.new_content !== null) {
    return (
      <pre className="mono scroll-thin max-h-60 overflow-auto rounded-lg border border-edge bg-plane p-3 text-[11px] leading-relaxed whitespace-pre-wrap text-ink-2">
        {edit.new_content.slice(0, 2000)}
      </pre>
    );
  }
  const removed = (edit.search ?? "").split("\n");
  const added = (edit.replace ?? "").split("\n");
  return (
    <pre className="mono scroll-thin max-h-60 overflow-auto rounded-lg border border-edge bg-plane p-3 text-[11px] leading-relaxed whitespace-pre-wrap">
      {removed.map((line, index) => (
        <div key={`r${index}`} style={{ color: "var(--critical)" }}>
          − {line}
        </div>
      ))}
      {added.map((line, index) => (
        <div key={`a${index}`} style={{ color: "var(--good)" }}>
          + {line}
        </div>
      ))}
    </pre>
  );
}

function TestList({ items, tone }: { items: string[]; tone: string }) {
  const colour =
    tone === "good" ? "var(--good)" : tone === "critical" ? "var(--critical)" : "var(--ink-3)";
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item} className="mono flex gap-2 text-[11px] leading-relaxed text-ink-2">
          <span aria-hidden style={{ color: colour }}>
            •
          </span>
          <span className="min-w-0 break-all">{item}</span>
        </li>
      ))}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-6 last:mb-0">
      <h3 className="eyebrow mb-2">{title}</h3>
      {children}
    </section>
  );
}

/** Shown when nothing is selected: teach the mental model rather than sit blank. */
function Explainer({ result }: { result: RunResult | null }) {
  return (
    <div className="scroll-thin h-full overflow-y-auto px-5 py-5">
      <h2 className="text-[15px] font-semibold tracking-[-0.01em]">How to read this</h2>
      <p className="mt-2 text-[12.5px] leading-relaxed text-ink-2">
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
          <li key={text} className="flex gap-2.5 text-[12.5px] text-ink-2">
            <span
              aria-hidden
              className="mt-[7px] h-[3px] w-4 shrink-0 rounded-full"
              style={{ background: colour }}
            />
            <span>{text}</span>
          </li>
        ))}
      </ul>

      {result?.diff && (
        <section className="mt-6">
          <h3 className="eyebrow mb-2">The resulting patch</h3>
          <pre className="mono scroll-thin max-h-[420px] overflow-auto rounded-lg border border-edge bg-plane p-3 text-[11px] leading-relaxed whitespace-pre">
            {result.diff.split("\n").map((line, index) => (
              <div
                key={index}
                style={{
                  color: line.startsWith("+")
                    ? "var(--good)"
                    : line.startsWith("-")
                      ? "var(--critical)"
                      : line.startsWith("@@")
                        ? "var(--accent)"
                        : "var(--ink-2)",
                }}
              >
                {line || " "}
              </div>
            ))}
          </pre>
        </section>
      )}

      <p className="mt-6 text-[12px] text-ink-3">Select any card to see its patch and its tests.</p>
    </div>
  );
}
