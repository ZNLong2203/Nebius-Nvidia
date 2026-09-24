"use client";

import { useEffect, useState } from "react";
import { getRecordings } from "@/lib/api";
import type { Health, Recording, StartRunRequest } from "@/lib/types";

const FIELD =
  "mono w-full rounded-lg border border-edge bg-plane px-3 py-2 text-[12.5px] text-ink " +
  "placeholder:text-ink-3 focus:border-accent focus:outline-none transition-colors";

export function CommandBar({
  health,
  running,
  stopping,
  currentRunId,
  onRun,
  onStop,
}: {
  health: Health | null;
  running: boolean;
  stopping: boolean;
  currentRunId: string | null;
  onRun: (request: StartRunRequest) => void;
  onStop: () => void;
}) {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  useEffect(() => {
    if (health?.static) getRecordings().then(setRecordings);
  }, [health?.static]);
  const [repo, setRepo] = useState("examples/broken-invoice");
  const [test, setTest] = useState("python -m pytest -q");
  const [setup, setSetup] = useState("pip install -q -r requirements.txt");
  const [fanout, setFanout] = useState(3);
  const [branching, setBranching] = useState(true);
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem("arborist-theme");
    if (stored === "light" || stored === "dark") setTheme(stored);
  }, []);

  const toggleTheme = () => {
    const current =
      theme ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("arborist-theme", next);
    setTheme(next);
  };

  const canRun = health ? health.can_run : true;

  return (
    <header className="z-30 border-b lg:sticky lg:top-0 border-edge bg-surface/85 backdrop-blur-xl">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2.5">
          <Mark />
          <div className="leading-none">
            <div className="text-[15px] font-semibold tracking-[-0.01em]">Arborist</div>
            <div className="mt-1 text-[11px] text-ink-3">tree search over sandbox states</div>
          </div>
        </div>

        <div className="hidden h-8 w-px bg-edge lg:block" />

        {health?.static && recordings.length > 0 ? (
          <div className="flex min-w-0 flex-1 basis-[420px] items-center gap-2">
            <label className="shrink-0 text-[11.5px] text-ink-3" htmlFor="recording">
              Recorded run
            </label>
            <select
              id="recording"
              className="w-full cursor-pointer rounded-lg border border-edge bg-plane px-3 py-2 text-[12.5px] text-ink transition-colors focus:border-accent focus:outline-none"
              value={currentRunId ?? recordings[0].run_id}
              onChange={(event) => {
                // A full navigation: the run is a link, so it can be shared.
                const url = new URL(window.location.href);
                url.searchParams.set("run", event.target.value);
                url.searchParams.delete("node");
                window.location.assign(url);
              }}
            >
              {recordings.map((recording) => (
                <option key={recording.run_id} value={recording.run_id}>
                  {recording.solved ? "✓ " : "✗ "}
                  {recording.title}
                </option>
              ))}
            </select>
          </div>
        ) : (
        <div className="flex min-w-0 flex-1 basis-[420px] items-center gap-2">
          <label className="sr-only" htmlFor="repo">
            Repository path
          </label>
          <input
            id="repo"
            className={FIELD}
            value={repo}
            onChange={(event) => setRepo(event.target.value)}
            spellCheck={false}
            placeholder="path/to/repository"
          />
          <label className="sr-only" htmlFor="test">
            Test command
          </label>
          <input
            id="test"
            className={`${FIELD} hidden sm:block`}
            value={test}
            onChange={(event) => setTest(event.target.value)}
            spellCheck={false}
          />
        </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="rounded-lg border border-edge px-3 py-2 text-[12.5px] font-medium text-ink-2 transition-colors hover:bg-surface-2"
          >
            Options
            <span aria-hidden className="ml-1.5 inline-block text-ink-3">
              {open ? "▴" : "▾"}
            </span>
          </button>

          <button
            type="button"
            onClick={toggleTheme}
            title="Switch theme"
            aria-label="Switch theme"
            className="rounded-lg border border-edge px-3 py-2 text-[13px] text-ink-2 transition-colors hover:bg-surface-2"
          >
            ◐
          </button>

          {running ? (
            <button
              type="button"
              onClick={onStop}
              disabled={stopping}
              title={stopping ? "Finishing the step in flight" : "Stop the search"}
              className="rounded-lg border border-edge px-4 py-2 text-[13px] font-semibold text-ink transition-colors hover:bg-surface-2 disabled:opacity-60"
            >
              <span
                className="mr-2 inline-block size-2 animate-pulse rounded-full"
                style={{ background: stopping ? "var(--warning)" : "var(--accent)" }}
              />
              {stopping ? "Stopping…" : "Stop search"}
            </button>
          ) : (
            <button
              type="button"
              disabled={!canRun}
              title={
                canRun
                  ? undefined
                  : health?.static
                    ? "This page is a static recording. Clone the repository to run a live search."
                    : "This server has no NEBIUS_API_KEY configured"
              }
              onClick={() =>
                onRun({
                  repo_path: repo.trim(),
                  test_command: test.trim(),
                  setup_command: setup.trim(),
                  fanout,
                  branching,
                })
              }
              className="rounded-lg px-4 py-2 text-[13px] font-semibold transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
              style={{ background: "var(--accent)", color: "var(--accent-ink)" }}
            >
              Run search
            </button>
          )}
        </div>
      </div>

      {open && (
        <div className="grid gap-3 border-t border-edge px-4 py-3 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
          <Field label="Setup command" hint="Run once. Every branch forks the result.">
            <input
              className={FIELD}
              value={setup}
              onChange={(event) => setSetup(event.target.value)}
              spellCheck={false}
            />
          </Field>
          <Field label="Test command" hint="Must go green for the run to succeed.">
            <input
              className={FIELD}
              value={test}
              onChange={(event) => setTest(event.target.value)}
              spellCheck={false}
            />
          </Field>
          <Field label="Branches per step" hint="Rival theories tested in parallel.">
            <input
              type="number"
              min={1}
              max={8}
              className={FIELD}
              value={fanout}
              onChange={(event) => setFanout(Number(event.target.value) || 1)}
            />
          </Field>
          <Field label="Mode" hint="Off is the linear baseline: no checkpoint reuse.">
            <button
              type="button"
              onClick={() => setBranching((value) => !value)}
              className="flex w-full items-center justify-between rounded-lg border border-edge bg-plane px-3 py-2 text-[12.5px] transition-colors hover:bg-surface-2"
            >
              <span>{branching ? "Branching" : "Linear baseline"}</span>
              <span
                className="relative inline-flex h-4 w-7 items-center rounded-full transition-colors"
                style={{ background: branching ? "var(--accent)" : "var(--line-2)" }}
              >
                <span
                  className="absolute size-3 rounded-full bg-white transition-all"
                  style={{ left: branching ? 14 : 2 }}
                />
              </span>
            </button>
          </Field>
        </div>
      )}
    </header>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="eyebrow mb-1.5">{label}</div>
      {children}
      <div className="mt-1 text-[11px] text-ink-3">{hint}</div>
    </label>
  );
}

/** A mark that is the product: one trunk, branches, one that goes green. */
function Mark() {
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden className="shrink-0">
      <path
        d="M4 13h5M9 13c3 0 3-6 6-6M9 13c3 0 3 6 6 6"
        fill="none"
        stroke="var(--ink-3)"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <circle cx="4" cy="13" r="2.4" fill="var(--ink-2)" />
      <circle cx="16" cy="7" r="2.6" fill="var(--good)" />
      <circle cx="16" cy="19" r="2.2" fill="var(--line-2)" />
    </svg>
  );
}
