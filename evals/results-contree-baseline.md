# Eval results

code: `7b11e3d` · backend: `contree` · fanout: 3 · node cap: 12 · models: `matched-baseline` (Qwen/Qwen3-30B-A3B-Instruct-2507, openai/gpt-oss-120b, Qwen/Qwen3-235B-A22B-Instruct-2507) · 3 run(s) per configuration

## Summary

| case | models | branching | solved | patches (median) | wall s (median) | tokens (median) | wall range |
|---|---|---|---|---|---|---|---|
| broken-invoice | matched-baseline | on | **3/3** | 7 | 88 | 30,653 | 84–106 |
| regression-trap | matched-baseline | on | **3/3** | 6 | 92 | 26,198 | 54–182 |
| masked-faults | matched-baseline | on | **3/3** | 6 | 66 | 21,632 | 54–67 |
| outside-knowledge | matched-baseline | on | **3/3** | 6 | 64 | 24,511 | 44–101 |

## Every run

| case | models | branching | run | solved | baseline | final | patches | sandbox runs | setup runs | invalid | wall (s) | nano tok | super tok | ultra tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| broken-invoice | matched-baseline | on | 1 | yes | 5/9 | 9/9 | 5 | 7 | 1 | 0 | 88.4 | 15,139 | 10,013 | 0 |
| broken-invoice | matched-baseline | on | 2 | yes | 5/9 | 9/9 | 7 | 9 | 1 | 0 | 83.8 | 20,612 | 10,041 | 0 |
| broken-invoice | matched-baseline | on | 3 | yes | 5/9 | 9/9 | 8 | 10 | 1 | 0 | 106.4 | 23,489 | 13,817 | 0 |
| regression-trap | matched-baseline | on | 1 | yes | 3/5 | 5/5 | 6 | 5 | 1 | 3 | 91.9 | 20,840 | 5,358 | 0 |
| regression-trap | matched-baseline | on | 2 | yes | 3/5 | 5/5 | 9 | 7 | 1 | 4 | 182.0 | 30,446 | 8,322 | 0 |
| regression-trap | matched-baseline | on | 3 | yes | 3/5 | 5/5 | 3 | 4 | 1 | 1 | 54.0 | 8,714 | 2,727 | 0 |
| masked-faults | matched-baseline | on | 1 | yes | 0/1 | 4/4 | 6 | 7 | 1 | 1 | 65.8 | 16,075 | 6,325 | 0 |
| masked-faults | matched-baseline | on | 2 | yes | 0/1 | 4/4 | 4 | 6 | 1 | 0 | 54.2 | 10,065 | 6,484 | 0 |
| masked-faults | matched-baseline | on | 3 | yes | 0/1 | 4/4 | 6 | 8 | 1 | 0 | 67.1 | 14,435 | 7,197 | 0 |
| outside-knowledge | matched-baseline | on | 1 | yes | 0/1 | 4/4 | 6 | 8 | 1 | 0 | 64.1 | 13,707 | 10,804 | 0 |
| outside-knowledge | matched-baseline | on | 2 | yes | 0/1 | 4/4 | 3 | 5 | 1 | 0 | 44.4 | 8,609 | 8,472 | 0 |
| outside-knowledge | matched-baseline | on | 3 | yes | 0/1 | 4/4 | 9 | 11 | 1 | 0 | 101.3 | 27,923 | 19,378 | 0 |

