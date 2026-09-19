# outside-knowledge

An order model written against Pydantic 1.x, in a project whose pin has moved to
2.x. Four tests, none of which even collect.

The point of this case is that **the answer is not in the repository**. Nothing
here records what `@root_validator` and `@validator` became; a repo-local agent
can read every file and still not know. This is the class of failure the Tavily
lookup exists for, and the case is how you check that the agent recognises an
external cause rather than hallucinating a local one.

## Why the obvious fix is not enough

The error names `skip_on_failure=True`, and adding it makes the exception go
away. It is still wrong: the deprecated API stays, and this project fails on
`DeprecationWarning` (see `pytest.ini`), which is a real convention in codebases
that intend to keep up with their dependencies.

| Patch | Result |
|---|---|
| as shipped | collection error |
| `@root_validator(skip_on_failure=True)` | **still fails** — deprecated API, warning is fatal |
| `@model_validator(mode="after")` **and** `@field_validator` | 4 passed |

So the case rewards a complete migration and punishes the patch that only
silences the symptom.

## What it measures

No partial credit is available: until both decorators are migrated the suite
does not collect, so every branch scores zero. That makes this the opposite of
`broken-invoice`, which rewards depth on a gradient. Here the only thing that
helps is **breadth** — several rival migrations evaluated from one prepared
checkpoint, with the tests as the arbiter.

```bash
python -m pytest -q
# 1 error in collection
```
