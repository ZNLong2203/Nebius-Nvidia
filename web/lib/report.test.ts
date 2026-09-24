import { describe, expect, it } from "vitest";

import { loadFailure } from "./report";
import type { TestReport } from "./types";

const report = (over: Partial<TestReport>): TestReport => ({
  total: 1, passed: 0, failed: 0, errors: 1, skipped: 0,
  failed_ids: ["tests.test_billing"], collection_error: false, green: false, ...over,
});

const OUTPUT = `tests/test_billing.py:4: in <module>
    from billing import InvoiceLine, invoice_total, line_total, prorate
E   ImportError: cannot import name 'prorate' from 'billing.proration' (/workspace/src/billing/proration.py)
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!`;

describe("loadFailure", () => {
  it("recognises a module that failed to import, and names the error without the sandbox path", () => {
    expect(loadFailure(report({}), OUTPUT)).toBe(
      "ImportError: cannot import name 'prorate' from 'billing.proration'",
    );
  });

  it("honours an explicit collection error", () => {
    expect(loadFailure(report({ collection_error: true, failed_ids: [] }), "")).toBe(
      "the test suite could not be collected",
    );
  });

  it("leaves an ordinary red suite alone", () => {
    const red = report({ total: 9, passed: 5, failed: 4, errors: 0, failed_ids: ["tests.t::test_a"] });
    expect(loadFailure(red, OUTPUT)).toBeNull();
  });

  it("leaves a test that errored during setup alone -- other tests ran", () => {
    const setup = report({ total: 3, passed: 2, errors: 1, failed_ids: ["tests.t::test_fixture"] });
    expect(loadFailure(setup, OUTPUT)).toBeNull();
  });
});
