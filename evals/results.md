# Eval results

backend: `local` · fanout: 3 · node cap: 12 · models: `nemotron` (nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, nvidia/nemotron-3-super-120b-a12b, nvidia/Nemotron-3-Ultra-550b-a55b) · 2 run(s) per configuration

## Summary

| case | models | branching | solved | patches (median) | wall s (median) | tokens (median) | wall range |
|---|---|---|---|---|---|---|---|
| broken-invoice | nemotron | on | **2/2** | 7 | 275 | 73,204 | 166–384 |
| broken-invoice | nemotron | off | **0/2** | 8 | 351 | 105,787 | 289–412 |
| regression-trap | nemotron | on | **2/2** | 2 | 101 | 21,804 | 88–113 |
| regression-trap | nemotron | off | **2/2** | 2 | 97 | 18,360 | 42–152 |
| masked-faults | nemotron | on | **2/2** | 6 | 190 | 51,388 | 153–226 |
| masked-faults | nemotron | off | **0/2** | 12 | 531 | 139,876 | 509–553 |
| outside-knowledge | nemotron | on | **2/2** | 4 | 144 | 45,095 | 123–166 |
| outside-knowledge | nemotron | off | **2/2** | 2 | 101 | 26,132 | 83–118 |

## Every run

| case | models | branching | run | solved | baseline | final | patches | sandbox runs | setup runs | invalid | wall (s) | nano tok | super tok | ultra tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| broken-invoice | nemotron | on | 1 | yes | 5/9 | 9/9 | 8 | 9 | 1 | 1 | 384.4 | 58,431 | 33,060 | 0 |
| broken-invoice | nemotron | on | 2 | yes | 5/9 | 9/9 | 6 | 8 | 1 | 0 | 165.8 | 37,351 | 17,566 | 0 |
| broken-invoice | nemotron | off | 1 | no | 5/9 | 7/9 | 9 | 10 | 9 | 1 | 289.4 | 77,276 | 23,710 | 20,892 |
| broken-invoice | nemotron | off | 2 | no | 5/9 | 7/9 | 6 | 6 | 5 | 2 | 412.3 | 61,326 | 16,098 | 12,272 |
| regression-trap | nemotron | on | 1 | yes | 3/5 | 5/5 | 2 | 4 | 1 | 0 | 113.2 | 11,094 | 9,736 | 0 |
| regression-trap | nemotron | on | 2 | yes | 3/5 | 5/5 | 3 | 5 | 1 | 0 | 88.2 | 13,875 | 8,904 | 0 |
| regression-trap | nemotron | off | 1 | yes | 3/5 | 5/5 | 2 | 4 | 3 | 0 | 151.6 | 16,778 | 9,325 | 0 |
| regression-trap | nemotron | off | 2 | yes | 3/5 | 5/5 | 1 | 3 | 2 | 0 | 41.6 | 6,663 | 3,954 | 0 |
| masked-faults | nemotron | on | 1 | yes | 0/1 | 4/4 | 6 | 7 | 1 | 1 | 153.3 | 25,134 | 24,238 | 0 |
| masked-faults | nemotron | on | 2 | yes | 0/1 | 4/4 | 5 | 6 | 1 | 1 | 225.7 | 38,529 | 14,874 | 0 |
| masked-faults | nemotron | off | 1 | no | 0/1 | 1/4 | 12 | 13 | 12 | 1 | 553.4 | 81,341 | 16,508 | 44,429 |
| masked-faults | nemotron | off | 2 | no | 0/1 | 1/4 | 11 | 12 | 11 | 1 | 508.9 | 66,757 | 18,404 | 52,313 |
| outside-knowledge | nemotron | on | 1 | yes | 0/1 | 4/4 | 6 | 7 | 1 | 1 | 166.0 | 35,620 | 23,606 | 0 |
| outside-knowledge | nemotron | on | 2 | yes | 0/1 | 4/4 | 2 | 4 | 1 | 0 | 122.9 | 8,202 | 22,762 | 0 |
| outside-knowledge | nemotron | off | 1 | yes | 0/1 | 4/4 | 2 | 4 | 3 | 0 | 117.9 | 11,162 | 15,959 | 0 |
| outside-knowledge | nemotron | off | 2 | yes | 0/1 | 4/4 | 2 | 4 | 3 | 0 | 83.3 | 8,308 | 16,836 | 0 |

