import type { TestReport } from "./types";

/**
 * Why a suite produced no test results at all, or null when it did.
 *
 * A patch that breaks an import stops pytest collecting, and JUnit then
 * reports one errored "test" named after the module. Shown as "0/1 tests
 * passing" that reads like a nearly-empty suite; what actually happened is
 * that nothing ran, and the useful thing to show is the error that stopped it.
 */
export function loadFailure(report: TestReport | null, output = ""): string | null {
  if (!report) return null;
  const moduleLevel = report.failed_ids.length > 0 && report.failed_ids.every((id) => !id.includes("::"));
  const nothingRan = report.passed === 0 && report.failed === 0 && report.errors > 0;
  if (!report.collection_error && !(moduleLevel && nothingRan)) return null;

  // pytest prefixes the error line with "E"; take the last one, which is the cause.
  const errors = output
    .split("\n")
    .map((line) => line.match(/^E\s+(\S.*)$/)?.[1])
    .filter((line): line is string => Boolean(line));
  const cause = errors.at(-1) ?? "the test suite could not be collected";
  // Absolute sandbox paths add length and nothing a reader needs.
  return cause.replace(/\s*\((?:\/[^)\s]+)+\)$/, "");
}
