# Eval results

backend: `local` · fanout: 3 · node cap: 12 · models: `nemotron` (nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, nvidia/nemotron-3-super-120b-a12b, nvidia/Nemotron-3-Ultra-550b-a55b)

| case | models | branching | solved | baseline | final | patches | sandbox runs | setup runs | invalid | wall (s) | nano tok | super tok | ultra tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| broken-invoice | nemotron | on | yes | 5/9 | 9/9 | 8 | 9 | 1 | 1 | 277.6 | 71,616 | 23,406 | 0 |
| broken-invoice | nemotron | off | no | 5/9 | 6/9 | 2 | 4 | 2 | 0 | 97.4 | 9,576 | 18,746 | 0 |
| regression-trap | nemotron | on | no | 3/5 | - | 2 | 2 | 1 | 2 | 159.0 | 30,704 | 10,645 | 0 |
| regression-trap | nemotron | off | yes | 3/5 | 5/5 | 1 | 3 | 1 | 0 | 52.9 | 5,250 | 4,248 | 0 |
| outside-knowledge | nemotron | on | yes | 0/1 | 4/4 | 1 | 3 | 1 | 0 | 65.9 | 5,354 | 9,443 | 0 |
| outside-knowledge | nemotron | off | yes | 0/1 | 4/4 | 1 | 3 | 1 | 0 | 1362.4 | 5,373 | 11,650 | 0 |

