# Arborist documentation

Arborist repairs a failing repository by searching a tree of immutable sandbox
states instead of walking one line of edits. These pages explain how, in the
order that makes sense if you are reading the code for the first time.

| Page | Read it for |
|---|---|
| [architecture.md](architecture.md) | The pieces, what each one owns, and how they fit together |
| [search-algorithm.md](search-algorithm.md) | The loop: selection, expansion, scoring, pruning, termination |
| [run-flow.md](run-flow.md) | One run end to end, from `arborist fix` to a diff |
| [models.md](models.md) | Nemotron tiering, the three prompts, budget accounting |
| [sandboxes.md](sandboxes.md) | The Nebius Sandboxes integration and the backend contract |
| [api.md](api.md) | HTTP endpoints and the event stream the UI consumes |
| [development.md](development.md) | Setup, tests, adding a backend, adding an eval case |
| [deploying.md](deploying.md) | Running the demo, recorded runs, Docker, going public |

## The one-paragraph version

A conventional coding agent edits, runs the tests, reads the failure, and edits
again. Three things are wrong with that shape: backtracking is destructive, the
expensive setup is repeated for every attempt, and rival explanations of a bug
are never compared. Nebius Sandboxes makes every executed command produce a new
immutable filesystem version that you can fork from. Arborist uses that to run
the setup **once**, fork it per candidate patch, score every fork against the
same baseline, make the winner the next fork point, and abandon regressions at no
cost — because nothing was ever mutated.

## Vocabulary

| Term | Meaning |
|---|---|
| **checkpoint** | An immutable filesystem state. A ConTree image version, or a directory snapshot under the local backend. |
| **node** | One position in the search tree: a checkpoint, the patch that produced it, and its score. |
| **fork** | Running a command *from* an existing checkpoint, producing a new one. The parent is unchanged. |
| **expansion** | Turning one node into children: diagnose, propose *k* patches, evaluate each on its own fork. |
| **the prefix** | Everything that must happen before tests can run — dependencies, build, cache warming. Paid once. |
| **regression** | A test that passed at the parent and does not pass at the child. Tracked by test identity, not by count. |
| **tier** | Which Nemotron model handles a step: `nano`, `super` or `ultra`. |
