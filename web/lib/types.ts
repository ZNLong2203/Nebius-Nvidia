/** Mirrors the shapes produced by `arborist.search.RunResult.to_dict()`. */

export type NodeStatus =
  | "running"
  | "improved"
  | "neutral"
  | "regressed"
  | "invalid"
  | "green"
  | "failed";

export interface TestReport {
  total: number;
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  failed_ids: string[];
  collection_error: boolean;
  green: boolean;
}

export interface Hypothesis {
  id: string;
  title: string;
  rationale: string;
  target_files: string[];
  strategy: string;
}

export interface Edit {
  path: string;
  search: string | null;
  replace: string | null;
  new_content: string | null;
}

export interface SearchNode {
  id: string;
  parent_id: string | null;
  depth: number;
  checkpoint_id: string | null;
  hypothesis: Hypothesis | null;
  diagnosis: string;
  edits: Edit[];
  explanation: string;
  report: TestReport | null;
  score: number;
  status: NodeStatus;
  regressions: string[];
  fixed: string[];
  stdout_tail: string;
  model_tier: string;
  wall_seconds: number;
  expanded: boolean;
  note: string;
}

export interface TierUsage {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface Usage {
  by_tier: Record<string, TierUsage>;
  models: Record<string, string>;
  total_tokens: number;
  budget: number;
}

export interface RunStats {
  backend: string;
  branching: boolean;
  wall_seconds: number;
  sandbox_executions: number;
  sandbox_seconds: number;
  setup_seconds: number;
  setup_runs: number;
  setup_seconds_saved: number;
  nodes: number;
  patches_evaluated: number;
  invalid_patches: number;
  forks: number | null;
  tavily_queries: string[];
}

export interface RunResult {
  run_id: string;
  solved: boolean;
  winner_id: string | null;
  diff: string;
  baseline: TestReport | null;
  final: TestReport | null;
  nodes: SearchNode[];
  stats: RunStats;
  usage: Usage;
  error: string;
}

export interface Health {
  ok: boolean;
  llm_configured: boolean;
  tavily_configured: boolean;
  can_run: boolean;
  backend: string;
  models: Record<string, string>;
  saved_runs: number;
  /** A static build with no server: recorded runs only. */
  static?: boolean;
}

export interface DemoResponse {
  available: boolean;
  source: string;
  recorded_at: number | null;
  run: RunResult | null;
}

/** One line of the server-sent event stream. */
export type RunEvent =
  | { type: "run_started"; at: number; run_id: string; repo: string; test_command: string }
  | { type: "checkpoint"; at: number; stage: "base" | "setup"; checkpoint: string; seconds?: number }
  | { type: "node"; at: number; node: SearchNode }
  | { type: "diagnosing"; at: number; node_id: string; tier: string }
  | {
      type: "diagnosed";
      at: number;
      node_id: string;
      tier: string;
      root_cause: string;
      searched: boolean;
      search_query: string;
      attempts: number;
      reply_keys: string[];
      hypotheses: Hypothesis[];
    }
  | { type: "progress"; at: number; best_score: number; stalls: number }
  | { type: "adjudicated"; at: number; verdict: Record<string, unknown> }
  | { type: "budget_exceeded"; at: number; message: string }
  | { type: "cancelled"; at: number; message: string }
  | { type: "error"; at: number; message: string }
  | { type: "run_finished"; at: number; result: RunResult }
  | { type: "done"; at: number };

export interface StartRunRequest {
  repo_path: string;
  test_command?: string;
  setup_command?: string;
  image?: string;
  backend?: string | null;
  fanout?: number | null;
  max_nodes?: number | null;
  max_depth?: number | null;
  branching?: boolean | null;
  context_files?: string[];
}
