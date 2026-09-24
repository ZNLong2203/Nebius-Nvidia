// Ships recorded runs beside a static build, for hosting with no server.
//
// The runs come from evals/evidence/, the same files the README cites, so the
// hosted page can only ever show a search that is checked into the repository.
// Every entry becomes linkable as ?run=<run_id>; the one named as `demo` is what
// the page opens on.
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const evidence = join(here, "..", "..", "evals", "evidence");
const out = join(here, "..", "public", "demo");
const manifest = JSON.parse(readFileSync(join(evidence, "manifest.json"), "utf8"));

rmSync(out, { recursive: true, force: true });
mkdirSync(join(out, "runs"), { recursive: true });

let pinned = false;
const index = [];
for (const entry of manifest.runs) {
  const run = JSON.parse(readFileSync(join(evidence, entry.file), "utf8"));
  const recorded_at = entry.recorded_at ?? null;
  writeFileSync(
    join(out, "runs", `${run.run_id}.json`),
    JSON.stringify({ run_id: run.run_id, done: true, error: run.error ?? "", result: run, recorded_at }),
  );
  index.push({ run_id: run.run_id, title: entry.title ?? entry.file, recorded_at, solved: Boolean(run.solved) });
  if (entry.file === manifest.demo) {
    writeFileSync(
      join(out, "demo.json"),
      JSON.stringify({ available: true, source: entry.file, recorded_at, run }),
    );
    pinned = true;
  }
  console.log(`bundled ${entry.file} as ?run=${run.run_id}`);
}

// What the page offers as "recorded runs": every entry, the demo first.
writeFileSync(join(out, "index.json"), JSON.stringify(index));

if (!pinned) {
  console.error(`manifest.demo (${manifest.demo}) is not among manifest.runs`);
  process.exit(1);
}
