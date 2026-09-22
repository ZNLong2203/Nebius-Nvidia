# SWE-bench Lite on Nebius Sandboxes

code: `7b11e3d`

Test-driven setting: the agent sees the issue **and** the failing tests, which are
protected from edits. Not comparable to the SWE-bench leaderboard. Method and
exclusions: [README.md](README.md).

## Summary

| arm | resolved (verified) | reported solved | patches (median) | wall s (median) | tokens (median) |
|---|---|---|---|---|---|
| branching | **14/23** | 14/23 | 3 | 257 | 303,301 |
| linear | **15/23** | 15/23 | 6 | 449 | 514,736 |

Paired by instance: branching alone resolved **2**, linear alone resolved **3**, of 23 instances run in both arms.

## Every run

| instance | arm | run | solved | verified | patches | invalid | sandbox runs | wall s | tokens | tavily | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mwaskom__seaborn-2848 | branching | 1 | no | - | 6 | 5 | 2 | 334 | 514,798 | 1 |  |
| mwaskom__seaborn-2848 | linear | 1 | no | - | 12 | 7 | 6 | 1410 | 1,009,382 | 3 |  |
| mwaskom__seaborn-3010 | branching | 1 | yes | yes | 3 | 0 | 4 | 89 | 158,169 | 0 |  |
| mwaskom__seaborn-3010 | linear | 1 | yes | yes | 1 | 0 | 2 | 49 | 56,089 | 0 |  |
| mwaskom__seaborn-3190 | branching | 1 | yes | yes | 1 | 0 | 2 | 133 | 93,996 | 0 |  |
| mwaskom__seaborn-3190 | linear | 1 | yes | yes | 6 | 4 | 3 | 449 | 527,505 | 0 |  |
| mwaskom__seaborn-3407 | branching | 1 | no | - | 12 | 7 | 6 | 678 | 819,911 | 1 |  |
| mwaskom__seaborn-3407 | linear | 1 | no | - | 12 | 7 | 6 | 1596 | 1,408,405 | 3 |  |
| pallets__flask-4045 | branching | 1 | yes | yes | 4 | 0 | 5 | 233 | 162,528 | 0 |  |
| pallets__flask-4045 | linear | 1 | yes | yes | 1 | 0 | 2 | 57 | 47,666 | 0 |  |
| pallets__flask-4992 | branching | 1 | yes | yes | 6 | 5 | 2 | 283 | 344,138 | 0 |  |
| pallets__flask-4992 | linear | 1 | yes | yes | 8 | 7 | 2 | 602 | 556,476 | 0 |  |
| pallets__flask-5063 | branching | 1 | yes | yes | 1 | 0 | 2 | 184 | 94,422 | 0 |  |
| pallets__flask-5063 | linear | 1 | yes | yes | 7 | 4 | 4 | 982 | 514,736 | 0 |  |
| pytest-dev__pytest-11143 | branching | 1 | yes | yes | 1 | 0 | 2 | 106 | 78,457 | 0 |  |
| pytest-dev__pytest-11143 | linear | 1 | yes | yes | 1 | 0 | 2 | 68 | 50,560 | 0 |  |
| pytest-dev__pytest-11148 | branching | 1 | yes | yes | 6 | 4 | 3 | 264 | 445,806 | 0 |  |
| pytest-dev__pytest-11148 | linear | 1 | yes | yes | 1 | 0 | 2 | 75 | 65,190 | 0 |  |
| pytest-dev__pytest-5221 | branching | 1 | no | - | 9 | 9 | 1 | 498 | 741,090 | 0 |  |
| pytest-dev__pytest-5221 | linear | 1 | no | - | 12 | 9 | 4 | 1417 | 1,218,601 | 0 |  |
| pytest-dev__pytest-5227 | branching | 1 | yes | yes | 1 | 0 | 2 | 150 | 127,332 | 0 |  |
| pytest-dev__pytest-5227 | linear | 1 | no | - | 9 | 9 | 1 | 1432 | 967,255 | 0 |  |
| pytest-dev__pytest-5413 | branching | 1 | yes | yes | 1 | 0 | 2 | 54 | 63,674 | 0 |  |
| pytest-dev__pytest-5413 | linear | 1 | yes | yes | 1 | 0 | 2 | 52 | 62,362 | 0 |  |
| pytest-dev__pytest-5495 | branching | 1 | yes | yes | 7 | 3 | 5 | 361 | 482,605 | 0 |  |
| pytest-dev__pytest-5495 | linear | 1 | yes | yes | 2 | 0 | 3 | 166 | 174,724 | 0 |  |
| pytest-dev__pytest-5692 | branching | 1 | yes | yes | 8 | 6 | 3 | 643 | 466,212 | 0 |  |
| pytest-dev__pytest-5692 | linear | 1 | no | - | 12 | 11 | 2 | 786 | 870,096 | 0 |  |
| pytest-dev__pytest-6116 | branching | 1 | no | - | 12 | 5 | 8 | 455 | 746,489 | 0 |  |
| pytest-dev__pytest-6116 | linear | 1 | no | - | 9 | 9 | 1 | 1115 | 931,513 | 0 |  |
| pytest-dev__pytest-7168 | branching | 1 | no | - | 3 | 2 | 2 | 254 | 245,049 | 0 |  |
| pytest-dev__pytest-7168 | linear | 1 | no | - | 8 | 7 | 2 | 532 | 810,077 | 0 |  |
| pytest-dev__pytest-7220 | branching | 1 | no | - | 3 | 2 | 2 | 258 | 386,722 | 0 |  |
| pytest-dev__pytest-7220 | linear | 1 | yes | yes | 1 | 0 | 2 | 60 | 53,643 | 0 |  |
| pytest-dev__pytest-7373 | branching | 1 | yes | yes | 3 | 1 | 3 | 181 | 245,978 | 1 |  |
| pytest-dev__pytest-7373 | linear | 1 | yes | yes | 1 | 0 | 2 | 63 | 61,278 | 0 |  |
| pytest-dev__pytest-7432 | branching | 1 | no | - | 4 | 3 | 2 | 355 | 330,872 | 0 |  |
| pytest-dev__pytest-7432 | linear | 1 | yes | yes | 9 | 7 | 3 | 950 | 901,074 | 0 |  |
| pytest-dev__pytest-7490 | branching | 1 | no | - | 2 | 2 | 1 | 178 | 224,201 | 0 |  |
| pytest-dev__pytest-7490 | linear | 1 | yes | yes | 4 | 0 | 5 | 392 | 307,600 | 0 |  |
| pytest-dev__pytest-8365 | branching | 1 | yes | yes | 1 | 0 | 2 | 146 | 76,901 | 0 |  |
| pytest-dev__pytest-8365 | linear | 1 | yes | yes | 2 | 0 | 3 | 268 | 164,326 | 0 |  |
| pytest-dev__pytest-8906 | branching | 1 | no | - | 3 | 3 | 1 | 276 | 303,301 | 0 |  |
| pytest-dev__pytest-8906 | linear | 1 | no | - | 9 | 9 | 1 | 1279 | 1,013,491 | 0 |  |
| pytest-dev__pytest-9359 | branching | 1 | yes | yes | 3 | 1 | 3 | 257 | 347,452 | 0 |  |
| pytest-dev__pytest-9359 | linear | 1 | yes | yes | 1 | 0 | 2 | 251 | 268,106 | 0 |  |
