# Eval results

backend: `local` · fanout: 3 · node cap: 10

| case | branching | solved | baseline | final | patches | sandbox runs | setup runs | invalid | wall (s) | nano tok | super tok | ultra tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| broken-invoice | on | no | 5/9 | 8/9 | 8 | 7 | 1 | 3 | 249.0 | 43,772 | 39,276 | 0 |
| broken-invoice | off | no | 5/9 | 6/9 | 2 | 4 | 2 | 0 | 93.7 | 11,679 | 15,416 | 0 |
| regression-trap | on | yes | 3/5 | 5/5 | 3 | 5 | 1 | 0 | 58.9 | 9,453 | 7,808 | 0 |
| regression-trap | off | yes | 3/5 | 5/5 | 1 | 3 | 1 | 0 | 50.9 | 4,957 | 4,576 | 0 |
| outside-knowledge | on | yes | 0/1 | 4/4 | 3 | 5 | 1 | 0 | 70.5 | 9,392 | 9,712 | 0 |
| outside-knowledge | off | yes | 0/1 | 4/4 | 2 | 4 | 2 | 0 | 70.4 | 7,284 | 6,824 | 0 |

