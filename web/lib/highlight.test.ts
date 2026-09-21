import { describe, expect, it } from "vitest";

import { opensDocstring, tokenizeBlock, tokenizeLine } from "./highlight";

const kinds = (line: string) =>
  tokenizeLine(line, null).tokens.filter((t) => t.text.trim()).map((t) => [t.kind, t.text.trim()]);

describe("tokenizeLine", () => {
  it("tells keywords, calls, builtins, numbers and comments apart", () => {
    expect(kinds("def total(x):  # sum it")).toEqual([
      ["keyword", "def"],
      ["func", "total"],
      ["plain", "(x):"],
      ["comment", "# sum it"],
    ]);
    expect(kinds("return round(x, 2)")).toContainEqual(["builtin", "round"]);
    expect(kinds("return round(x, 2)")).toContainEqual(["number", "2"]);
  });

  it("keeps a '#' inside a string out of the comment", () => {
    expect(kinds('label = "no # comment here"')).toContainEqual(["string", '"no # comment here"']);
  });

  it("reads prefixed strings as strings", () => {
    expect(kinds('msg = f"{a} and {b}"')).toContainEqual(["string", 'f"{a} and {b}"']);
  });
});

describe("tokenizeBlock", () => {
  it("carries a docstring across lines and stops at its closer", () => {
    const lines = tokenizeBlock('"""Money helpers.\n\nRounds half away from zero.\n"""\nx = 1');
    for (const line of lines.slice(0, 4)) {
      expect(line.every((t) => t.kind === "string")).toBe(true);
    }
    expect(lines[4].map((t) => t.kind)).toContain("number");
  });
});

describe("opensDocstring", () => {
  it("recognises either triple quote", () => {
    expect(opensDocstring('    """Start')).toBe(true);
    expect(opensDocstring("'''Start")).toBe(true);
    expect(opensDocstring("x = 1")).toBe(false);
  });
});
