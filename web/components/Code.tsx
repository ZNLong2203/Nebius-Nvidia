"use client";

import { useState } from "react";
import { tokenizeBlock, type Token } from "@/lib/highlight";

function Line({ tokens }: { tokens: Token[] }) {
  return (
    <>
      {tokens.map((token, index) =>
        token.kind === "plain" ? (
          <span key={index}>{token.text}</span>
        ) : (
          <span key={index} style={{ color: `var(--tok-${token.kind})` }}>
            {token.text}
          </span>
        ),
      )}
    </>
  );
}

function CopyButton({ value, label = "code" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {
          /* clipboard is unavailable over plain http on some hosts */
        }
      }}
      aria-label={`Copy ${label}`}
      className="rounded-md border border-edge px-2 py-0.5 text-[10.5px] font-medium text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink-2"
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

/**
 * A patch, rendered so it can be read.
 *
 * The lines are tinted by their side of the change and the code inside them is
 * still syntax-coloured, because a wall of solid red and green tells you where
 * the change is but nothing about what it says.
 */
export function DiffBlock({
  removed,
  added,
  path,
}: {
  removed: string;
  added: string;
  path?: string;
}) {
  const removedLines = removed === "" ? [] : removed.replace(/\n$/, "").split("\n");
  const addedLines = added === "" ? [] : added.replace(/\n$/, "").split("\n");
  const removedTokens = tokenizeBlock(removedLines.join("\n"));
  const addedTokens = tokenizeBlock(addedLines.join("\n"));

  const rows: { sign: "-" | "+"; tokens: Token[] }[] = [
    ...removedLines.map((_, index) => ({ sign: "-" as const, tokens: removedTokens[index] ?? [] })),
    ...addedLines.map((_, index) => ({ sign: "+" as const, tokens: addedTokens[index] ?? [] })),
  ];

  return (
    <figure className="overflow-hidden rounded-lg border border-edge bg-plane">
      {path && (
        <figcaption className="flex items-center justify-between gap-2 border-b border-edge bg-surface-2 px-3 py-1.5">
          <span className="mono truncate text-[11px] text-ink-2">{path}</span>
          <div className="flex shrink-0 items-center gap-2">
            <span className="mono text-[10.5px] text-ink-3">
              <span style={{ color: "var(--critical)" }}>−{removedLines.length}</span>{" "}
              <span style={{ color: "var(--good)" }}>+{addedLines.length}</span>
            </span>
            <CopyButton value={added || removed} label="patch" />
          </div>
        </figcaption>
      )}
      <div className="scroll-thin max-h-[340px] overflow-auto">
        <pre className="mono m-0 p-0 text-[11.5px] leading-[1.55]">
          {rows.map((row, index) => (
            <div
              key={index}
              className="flex gap-2 px-3"
              style={{
                background:
                  row.sign === "+"
                    ? "color-mix(in srgb, var(--good) 11%, transparent)"
                    : "color-mix(in srgb, var(--critical) 11%, transparent)",
              }}
            >
              <span
                aria-hidden
                className="shrink-0 select-none opacity-70"
                style={{ color: row.sign === "+" ? "var(--good)" : "var(--critical)" }}
              >
                {row.sign}
              </span>
              <code className="min-w-0 flex-1 break-words whitespace-pre-wrap">
                <Line tokens={row.tokens} />
              </code>
            </div>
          ))}
        </pre>
      </div>
    </figure>
  );
}

/** A file, or a whole-file rewrite. */
export function CodeBlock({
  source,
  path,
  max = 340,
}: {
  source: string;
  path?: string;
  max?: number;
}) {
  const lines = tokenizeBlock(source.replace(/\n$/, ""));
  return (
    <figure className="overflow-hidden rounded-lg border border-edge bg-plane">
      {path && (
        <figcaption className="flex items-center justify-between gap-2 border-b border-edge bg-surface-2 px-3 py-1.5">
          <span className="mono truncate text-[11px] text-ink-2">{path}</span>
          <CopyButton value={source} label="file" />
        </figcaption>
      )}
      <div className="scroll-thin overflow-auto" style={{ maxHeight: max }}>
        <pre className="mono m-0 px-3 py-2 text-[11.5px] leading-[1.55]">
          {lines.map((tokens, index) => (
            <div key={index} className="break-words whitespace-pre-wrap">
              <Line tokens={tokens} />
            </div>
          ))}
        </pre>
      </div>
    </figure>
  );
}

const FAIL = /^(FAILED|ERROR|E\s|>\s+assert|AssertionError)/;
const PASS = /\bpassed\b/;

/**
 * pytest output, with the lines a reader is actually scanning for picked out.
 */
export function TestOutput({ text }: { text: string }) {
  const lines = text.replace(/\n$/, "").split("\n");
  return (
    <figure className="overflow-hidden rounded-lg border border-edge bg-plane">
      <figcaption className="flex items-center justify-between gap-2 border-b border-edge bg-surface-2 px-3 py-1.5">
        <span className="eyebrow">stdout</span>
        <CopyButton value={text} label="output" />
      </figcaption>
      <div className="scroll-thin max-h-[300px] overflow-auto">
        <pre className="mono m-0 px-3 py-2 text-[11px] leading-[1.6]">
          {lines.map((line, index) => {
            const failing = FAIL.test(line.trim());
            const summary = /\d+ (failed|passed|error)/.test(line);
            return (
              <div
                key={index}
                className="break-words whitespace-pre-wrap"
                style={{
                  color: failing
                    ? "var(--critical)"
                    : summary
                      ? PASS.test(line) && !/failed|error/.test(line)
                        ? "var(--good)"
                        : "var(--ink)"
                      : "var(--ink-3)",
                  fontWeight: summary ? 600 : undefined,
                }}
              >
                {line || " "}
              </div>
            );
          })}
        </pre>
      </div>
    </figure>
  );
}
