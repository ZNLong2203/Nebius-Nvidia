# Eval results

code: `7b11e3d` · backend: `contree` · fanout: 3 · node cap: 12 · models: `nemotron` (nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, nvidia/nemotron-3-super-120b-a12b, nvidia/Nemotron-3-Ultra-550b-a55b) · 3 run(s) per configuration

## Summary

| case | models | branching | solved | patches (median) | wall s (median) | tokens (median) | wall range |
|---|---|---|---|---|---|---|---|
| broken-invoice | nemotron | on | **3/3** | 6 | 230 | 64,328 | 168–297 |
| broken-invoice | nemotron | off | **0/3** | 12 | 713 | 160,311 | 396–751 |
| regression-trap | nemotron | on | **3/3** | 2 | 79 | 15,734 | 71–399 |
| regression-trap | nemotron | off | **3/3** | 1 | 51 | 9,444 | 50–56 |
| masked-faults | nemotron | on | **2/3** | 8 | 313 | 85,305 | 156–334 |
| masked-faults | nemotron | off | **0/3** | 12 | 470 | 133,647 | 345–476 |
| outside-knowledge | nemotron | on | **3/3** | 3 | 198 | 38,303 | 164–243 |
| outside-knowledge | nemotron | off | **3/3** | 3 | 250 | 58,752 | 131–256 |

## Every run

| case | models | branching | run | solved | baseline | final | patches | sandbox runs | setup runs | invalid | wall (s) | nano tok | super tok | ultra tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| broken-invoice | nemotron | on | 1 | yes | 5/9 | 9/9 | 6 | 7 | 1 | 1 | 167.5 | 33,308 | 20,685 | 0 |
| broken-invoice | nemotron | on | 2 | yes | 5/9 | 9/9 | 7 | 9 | 1 | 0 | 297.0 | 49,546 | 33,812 | 0 |
| broken-invoice | nemotron | on | 3 | yes | 5/9 | 9/9 | 6 | 7 | 1 | 1 | 229.8 | 46,312 | 18,016 | 0 |
| broken-invoice | nemotron | off | 1 | no | 5/9 | 7/9 | 12 | 12 | 11 | 2 | 396.5 | 92,676 | 34,713 | 31,667 |
| broken-invoice | nemotron | off | 2 | no | 5/9 | 7/9 | 12 | 13 | 12 | 1 | 713.3 | 100,522 | 27,025 | 32,764 |
| broken-invoice | nemotron | off | 3 | no | 5/9 | 7/9 | 12 | 13 | 12 | 1 | 751.3 | 107,681 | 32,657 | 46,534 |
| regression-trap | nemotron | on | 1 | yes | 3/5 | 5/5 | 7 | 7 | 1 | 2 | 399.1 | 64,740 | 23,127 | 5,995 |
| regression-trap | nemotron | on | 2 | yes | 3/5 | 5/5 | 2 | 4 | 1 | 0 | 79.3 | 9,247 | 6,487 | 0 |
| regression-trap | nemotron | on | 3 | yes | 3/5 | 5/5 | 1 | 3 | 1 | 0 | 71.2 | 9,854 | 4,786 | 0 |
| regression-trap | nemotron | off | 1 | yes | 3/5 | 5/5 | 1 | 3 | 2 | 0 | 56.2 | 5,605 | 4,950 | 0 |
| regression-trap | nemotron | off | 2 | yes | 3/5 | 5/5 | 1 | 3 | 2 | 0 | 50.2 | 4,450 | 3,857 | 0 |
| regression-trap | nemotron | off | 3 | yes | 3/5 | 5/5 | 1 | 3 | 2 | 0 | 51.3 | 4,910 | 4,534 | 0 |
| masked-faults | nemotron | on | 1 | yes | 0/1 | 4/4 | 8 | 9 | 1 | 1 | 312.9 | 48,437 | 36,868 | 0 |
| masked-faults | nemotron | on | 2 | no | 0/1 | 3/4 | 12 | 12 | 1 | 2 | 334.5 | 61,696 | 25,819 | 6,575 |
| masked-faults | nemotron | on | 3 | yes | 0/1 | 4/4 | 6 | 8 | 1 | 0 | 155.7 | 23,126 | 17,203 | 0 |
| masked-faults | nemotron | off | 1 | no | 0/1 | 1/4 | 12 | 12 | 11 | 2 | 475.9 | 76,522 | 18,844 | 42,275 |
| masked-faults | nemotron | off | 2 | no | 0/1 | 1/4 | 12 | 12 | 11 | 2 | 344.6 | 69,101 | 29,908 | 33,043 |
| masked-faults | nemotron | off | 3 | no | 0/1 | 1/4 | 12 | 13 | 12 | 1 | 470.0 | 74,592 | 13,528 | 45,527 |
| outside-knowledge | nemotron | on | 1 | yes | 0/1 | 4/4 | 3 | 5 | 1 | 0 | 197.5 | 16,172 | 21,250 | 0 |
| outside-knowledge | nemotron | on | 2 | yes | 0/1 | 4/4 | 2 | 4 | 1 | 0 | 243.0 | 21,433 | 16,870 | 0 |
| outside-knowledge | nemotron | on | 3 | yes | 0/1 | 4/4 | 6 | 8 | 1 | 0 | 164.0 | 28,039 | 21,839 | 0 |
| outside-knowledge | nemotron | off | 1 | yes | 0/1 | 4/4 | 4 | 5 | 4 | 1 | 255.7 | 32,261 | 22,575 | 5,889 |
| outside-knowledge | nemotron | off | 2 | yes | 0/1 | 4/4 | 3 | 5 | 4 | 0 | 249.9 | 26,097 | 32,655 | 0 |
| outside-knowledge | nemotron | off | 3 | yes | 0/1 | 4/4 | 2 | 4 | 3 | 0 | 131.0 | 11,637 | 18,304 | 0 |

