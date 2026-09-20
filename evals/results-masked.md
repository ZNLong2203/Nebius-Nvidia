# Eval results

backend: `local` · fanout: 3 · node cap: 12 · models: `nemotron` (nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, nvidia/nemotron-3-super-120b-a12b, nvidia/Nemotron-3-Ultra-550b-a55b) · 2 run(s) per configuration

## Summary

| case | models | branching | solved | patches (median) | wall s (median) | tokens (median) | wall range |
|---|---|---|---|---|---|---|---|
| masked-faults | nemotron | on | **2/2** | 6 | 191 | 55,898 | 144–237 |
| masked-faults | nemotron | off | **0/2** | 12 | 582 | 159,834 | 504–660 |

## Every run

| case | models | branching | run | solved | baseline | final | patches | sandbox runs | setup runs | invalid | wall (s) | nano tok | super tok | ultra tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| masked-faults | nemotron | on | 1 | yes | 0/1 | 4/4 | 5 | 7 | 1 | 0 | 144.5 | 29,553 | 13,554 | 0 |
| masked-faults | nemotron | on | 2 | yes | 0/1 | 4/4 | 8 | 10 | 1 | 0 | 236.7 | 46,416 | 22,272 | 0 |
| masked-faults | nemotron | off | 1 | no | 0/1 | 1/4 | 12 | 14 | 13 | 0 | 503.5 | 72,869 | 20,314 | 42,597 |
| masked-faults | nemotron | off | 2 | no | 0/1 | 1/4 | 12 | 13 | 12 | 1 | 659.8 | 80,905 | 22,088 | 80,894 |

