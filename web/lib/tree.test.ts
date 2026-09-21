import { describe, expect, it } from "vitest";

import { ancestryIds, GAP_X, layoutTree, NODE_W, PAD, winningPathIds } from "./tree";
import type { SearchNode } from "./types";

const node = (id: string, parent: string | null, depth: number, status = "improved") =>
  ({ id, parent_id: parent, depth, status }) as unknown as SearchNode;

// root ─┬─ a ─── a1 (green)
//       ├─ b      (regressed)
//       └─ c      (invalid)
const NODES = [
  node("root", null, 0, "baseline"),
  node("a", "root", 1),
  node("b", "root", 1, "regressed"),
  node("c", "root", 1, "invalid"),
  node("a1", "a", 2, "green"),
];

describe("layoutTree", () => {
  const layout = layoutTree(NODES, winningPathIds(NODES, "a1"));
  const at = (id: string) => layout.byId.get(id)!;

  it("puts depth on x, so the search reads left to right the way it happened", () => {
    for (const placed of layout.placed) {
      expect(placed.x).toBe(PAD + placed.node.depth * (NODE_W + GAP_X));
    }
  });

  it("keeps rival hypotheses in adjacent rows, in the order they were proposed", () => {
    expect(at("a").y).toBeLessThan(at("b").y);
    expect(at("b").y).toBeLessThan(at("c").y);
  });

  it("centres a parent on its children", () => {
    expect(at("root").y).toBe((at("a").y + at("c").y) / 2);
  });

  it("marks the winning chain, and dims branches that were abandoned", () => {
    const kind = (id: string) => layout.edges.find((e) => e.id === id)?.kind;
    expect(kind("root->a")).toBe("win");
    expect(kind("a->a1")).toBe("win");
    expect(kind("root->b")).toBe("dim");
    expect(kind("root->c")).toBe("dim");
  });

  it("sizes the canvas to fit every node", () => {
    for (const placed of layout.placed) {
      expect(placed.x + NODE_W).toBeLessThanOrEqual(layout.width);
    }
  });

  it("returns an empty layout for no nodes rather than -Infinity dimensions", () => {
    const empty = layoutTree([], new Set());
    expect(empty.placed).toEqual([]);
    expect(empty.width).toBe(0);
  });
});

describe("winningPathIds and ancestryIds", () => {
  it("walk from a node back to the root", () => {
    expect([...winningPathIds(NODES, "a1")].sort()).toEqual(["a", "a1", "root"]);
    expect([...ancestryIds(NODES, "b")].sort()).toEqual(["b", "root"]);
  });

  it("are empty when nothing is chosen", () => {
    expect(winningPathIds(NODES, null).size).toBe(0);
    expect(ancestryIds(NODES, null).size).toBe(0);
  });
});
