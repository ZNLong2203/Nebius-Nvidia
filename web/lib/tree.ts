import type { SearchNode } from "./types";

export const NODE_W = 236;
export const NODE_H = 76;
export const GAP_X = 88;
export const GAP_Y = 20;
export const PAD = 36;

export interface Placed {
  node: SearchNode;
  x: number;
  y: number;
}

export interface Layout {
  placed: Placed[];
  edges: { id: string; from: Placed; to: Placed; kind: "win" | "live" | "dim" }[];
  width: number;
  height: number;
  byId: Map<string, Placed>;
}

/**
 * A tidy tree laid out left to right: depth on x, so the search reads the way
 * it happened. Leaves take sequential rows and a parent centres on its
 * children, which keeps sibling hypotheses visually adjacent — they are rival
 * theories of one failure and belong side by side.
 */
export function layoutTree(nodes: SearchNode[], winningPath: Set<string>): Layout {
  const empty: Layout = { placed: [], edges: [], width: 0, height: 0, byId: new Map() };
  if (nodes.length === 0) return empty;

  const children = new Map<string | null, SearchNode[]>();
  for (const node of nodes) {
    const list = children.get(node.parent_id) ?? [];
    list.push(node);
    children.set(node.parent_id, list);
  }

  const rows = new Map<string, number>();
  let cursor = 0;

  const place = (node: SearchNode): number => {
    const kids = children.get(node.id) ?? [];
    if (kids.length === 0) {
      const y = cursor;
      cursor += NODE_H + GAP_Y;
      rows.set(node.id, y);
      return y;
    }
    const ys = kids.map(place);
    const y = (Math.min(...ys) + Math.max(...ys)) / 2;
    rows.set(node.id, y);
    return y;
  };

  for (const root of children.get(null) ?? []) place(root);

  const placed: Placed[] = nodes
    .filter((node) => rows.has(node.id))
    .map((node) => ({
      node,
      x: PAD + node.depth * (NODE_W + GAP_X),
      y: PAD + (rows.get(node.id) as number),
    }));

  if (placed.length === 0) return empty;

  const byId = new Map(placed.map((p) => [p.node.id, p]));
  const edges: Layout["edges"] = [];

  for (const child of placed) {
    if (!child.node.parent_id) continue;
    const parent = byId.get(child.node.parent_id);
    if (!parent) continue;
    const onWinningPath = winningPath.has(child.node.id) && winningPath.has(parent.node.id);
    const abandoned = child.node.status === "invalid" || child.node.status === "regressed";
    edges.push({
      id: `${parent.node.id}->${child.node.id}`,
      from: parent,
      to: child,
      kind: onWinningPath ? "win" : abandoned ? "dim" : "live",
    });
  }

  return {
    placed,
    edges,
    byId,
    width: Math.max(...placed.map((p) => p.x + NODE_W)) + PAD,
    height: Math.max(...placed.map((p) => p.y + NODE_H)) + PAD,
  };
}

/** The chain of accepted patches, from the root to the winner. */
export function winningPathIds(nodes: SearchNode[], winnerId: string | null): Set<string> {
  const path = new Set<string>();
  if (!winnerId) return path;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let current = byId.get(winnerId);
  while (current) {
    path.add(current.id);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return path;
}

/** Every ancestor of a node, used to light up "what this state was built on". */
export function ancestryIds(nodes: SearchNode[], nodeId: string | null): Set<string> {
  const chain = new Set<string>();
  if (!nodeId) return chain;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let current = byId.get(nodeId);
  while (current) {
    chain.add(current.id);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return chain;
}

export const STATUS_META: Record<
  SearchNode["status"],
  { label: string; icon: string; tone: string }
> = {
  green: { label: "green", icon: "✓", tone: "good" },
  improved: { label: "improved", icon: "↑", tone: "accent" },
  neutral: { label: "no change", icon: "→", tone: "warning" },
  regressed: { label: "regressed", icon: "↓", tone: "critical" },
  invalid: { label: "unapplied", icon: "✕", tone: "muted" },
  failed: { label: "baseline", icon: "○", tone: "muted" },
  running: { label: "running", icon: "◌", tone: "accent" },
};

export const TIER_META: Record<string, { label: string; role: string }> = {
  nano: { label: "Nano", role: "writes each candidate patch" },
  super: { label: "Super", role: "diagnoses and branches" },
  ultra: { label: "Ultra", role: "breaks ties and unsticks" },
};
