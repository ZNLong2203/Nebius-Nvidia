# Eval results

backend: `local` · fanout: 3 · node cap: 12 · models: `matched-baseline` (Qwen/Qwen3-30B-A3B-Instruct-2507, openai/gpt-oss-120b, Qwen/Qwen3-235B-A22B-Instruct-2507)

| case | models | branching | solved | baseline | final | patches | sandbox runs | setup runs | invalid | wall (s) | nano tok | super tok | ultra tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| broken-invoice | matched-baseline | on | yes | 5/9 | 9/9 | 8 | 10 | 1 | 0 | 66.7 | 23,078 | 20,171 | 0 |
| regression-trap | matched-baseline | on | yes | 3/5 | 5/5 | 3 | 4 | 1 | 1 | 33.2 | 8,282 | 2,688 | 0 |
| outside-knowledge | matched-baseline | on | yes | 0/1 | 4/4 | 3 | 5 | 1 | 0 | 29.0 | 7,967 | 5,859 | 0 |

