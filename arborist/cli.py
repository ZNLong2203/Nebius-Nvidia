"""Command line entry point."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree as RichTree

from .config import load_settings
from .llm import NemotronClient
from .models import Node
from .publish import GitError, build_plan, publish
from .report import load_report, render_markdown_summary, render_pr_body
from .sandbox import build_backend
from .search import Arborist, RunConfig, RunResult, write_report
from .tools.tavily import TavilyClient

app = typer.Typer(add_completion=False, help="Repair a failing repo by searching a tree of sandbox states.")
console = Console()

STATUS_STYLE = {
    "green": "bold green",
    "improved": "green",
    "neutral": "yellow",
    "regressed": "red",
    "invalid": "dim red",
    "failed": "white",
    "running": "cyan",
}


@app.command()
def fix(
    repo: Path = typer.Argument(..., help="Path to the repository to repair."),
    test_command: str = typer.Option("python -m pytest -q", "--test", "-t", help="Command that must go green."),
    setup: str = typer.Option(
        "", "--setup", "-s", help="Command that prepares the environment. Run ONCE, then shared by every branch."
    ),
    image: str = typer.Option("python:3.12-slim", "--image", help="OCI image for the sandbox."),
    backend: str = typer.Option(None, "--backend", help="contree | local"),
    fanout: int = typer.Option(None, "--fanout", "-k", help="Candidate patches per expansion."),
    max_nodes: int = typer.Option(
        None, "--max-nodes", help="Hard cap on nodes, counting patches that never reach the sandbox."
    ),
    max_depth: int = typer.Option(None, "--max-depth"),
    no_branching: bool = typer.Option(False, "--no-branching", help="Linear baseline: one attempt at a time, no checkpoint reuse."),
    context: list[str] = typer.Option([], "--context", "-c", help="Extra files or globs to always show the model."),
    goal: str = typer.Option("", "--goal", help="What the repair is for, e.g. the issue text. Prefix with @ to read a file."),
    protect: list[str] = typer.Option(
        [], "--protect", "-p", help="Glob no patch may edit (repeatable). Protect the tests to keep the oracle honest."
    ),
    workdir: str = typer.Option(None, "--workdir", help="Repository location inside the sandbox image."),
    out: Path = typer.Option(Path("runs"), "--out", "-o", help="Where to write the run report."),
    quiet: bool = typer.Option(False, "--quiet", "-q"),
) -> None:
    settings = load_settings(
        backend=backend,
        fanout=fanout,
        max_nodes=max_nodes,
        max_depth=max_depth,
        branching=False if no_branching else None,
        workdir=workdir,
    )
    if goal.startswith("@"):
        goal = Path(goal[1:]).read_text(encoding="utf-8")

    if not settings.has_llm:
        console.print("[red]NEBIUS_API_KEY is not set.[/] Copy .env.example to .env and add your key.")
        raise typer.Exit(code=2)

    llm = NemotronClient(settings)
    sandbox = build_backend(settings)
    tavily = TavilyClient(api_key=settings.tavily_api_key) if settings.has_tavily else None

    def on_event(event: dict) -> None:
        if quiet:
            return
        kind = event.get("type")
        if kind == "diagnosing":
            console.print(f"[dim]diagnosing[/] {event['node_id']} with [bold]{event['tier']}[/]")
        elif kind == "diagnosed":
            if event.get("searched"):
                console.print(f"  [magenta]tavily[/] {event.get('search_query', '')}")
            console.print(f"  [dim]root cause:[/] {event.get('root_cause', '')[:140]}")
            for h in event.get("hypotheses", []):
                console.print(f"  [cyan]-[/] {h['title'][:110]}")
        elif kind == "node":
            node = event["node"]
            # Nodes are re-emitted when they become the next fork point, which
            # the UI needs and the terminal does not.
            if node["depth"] == 0 or node["status"] == "running" or node["expanded"]:
                return
            style = STATUS_STYLE.get(node["status"], "white")
            report = node.get("report") or {}
            passed = f"{report.get('passed', '?')}/{report.get('total', '?')}"
            console.print(
                f"  [{style}]{node['status']:<9}[/] {node['id']}  score {node['score']:.2f}  {passed} passing"
                + (f"  [red]regressions: {len(node['regressions'])}[/]" if node["regressions"] else "")
            )
        elif kind == "error":
            console.print(f"[red]error:[/] {event['message']}")

    agent = Arborist(settings, sandbox, llm, tavily, on_event=on_event)
    cfg = RunConfig(
        repo_path=str(repo),
        test_command=test_command,
        setup_command=setup,
        image=image,
        context_files=list(context),
        goal=goal,
        protected=list(protect),
    )

    console.print(
        Panel(
            f"[bold]{repo}[/]\n{test_command}",
            title="arborist",
            subtitle=f"{sandbox.name} backend · branching {'on' if settings.branching else 'OFF (baseline)'}",
        )
    )

    try:
        result = agent.run(cfg)
    finally:
        sandbox.close()

    # Persist before rendering: a run that cost tokens and minutes must not be
    # lost to a broken pipe or a terminal that cannot draw the tree.
    path = write_report(result, out)
    _print_result(result)
    console.print(f"\nreport: [bold]{path}[/]")
    raise typer.Exit(code=0 if result.solved else 1)


def _print_result(result: RunResult) -> None:
    console.rule("result")

    if result.error:
        console.print(f"[red]{result.error}[/]")

    before = result.baseline
    after = result.final
    if before:
        line = f"baseline  {before.passed}/{before.total} passing"
        if after:
            line += f"   ->   final  {after.passed}/{after.total} passing"
        console.print(line)

    console.print(_render_tree(result.nodes))

    stats = Table(show_header=False, box=None, padding=(0, 2))
    s = result.stats
    stats.add_row("backend", str(s.get("backend")))
    stats.add_row("branching", "on" if s.get("branching") else "off")
    stats.add_row("patches evaluated", str(s.get("patches_evaluated")))
    stats.add_row("sandbox executions", str(s.get("sandbox_executions")))
    stats.add_row("invalid patches (never run)", str(s.get("invalid_patches")))
    if s.get("setup_seconds"):
        stats.add_row("setup cost", f"{s['setup_seconds']}s paid once")
        stats.add_row("setup time saved by forking", f"{s.get('setup_seconds_saved', 0)}s")
    stats.add_row("wall time", f"{s.get('wall_seconds')}s")
    if s.get("tavily_queries"):
        stats.add_row("tavily queries", json.dumps(s["tavily_queries"]))
    console.print(stats)

    usage = Table(title="Nemotron usage", show_header=True, header_style="bold")
    usage.add_column("tier")
    usage.add_column("model")
    usage.add_column("calls", justify="right")
    usage.add_column("tokens", justify="right")
    usage.add_column("cost", justify="right")
    for tier, u in result.usage.get("by_tier", {}).items():
        usage.add_row(
            tier,
            result.usage["models"].get(tier, ""),
            str(u["calls"]),
            f"{u['total_tokens']:,}",
            f"${u.get('cost_usd', 0):.3f}",
        )
    if "cost_usd" in result.usage:
        limit = result.usage.get("max_cost_usd") or 0
        usage.add_row(
            "total", "", "", f"{result.usage.get('total_tokens', 0):,}",
            f"${result.usage['cost_usd']:.3f}" + (f" of ${limit:.2f}" if limit else ""),
        )
    console.print(usage)

    if result.solved:
        console.print("\n[bold green]suite is green[/]\n")
        console.print(result.diff or "(no diff)")
    else:
        console.print("\n[yellow]not fully repaired[/] — best branch kept below\n")
        if result.diff:
            console.print(result.diff)


def _render_tree(nodes: list[Node]) -> RichTree:
    by_parent: dict[str | None, list[Node]] = {}
    for node in nodes:
        by_parent.setdefault(node.parent_id, []).append(node)

    root_nodes = by_parent.get(None, [])
    label = "baseline"
    if root_nodes and root_nodes[0].report:
        r = root_nodes[0].report
        label = f"baseline · {r.passed}/{r.total} passing"
    tree = RichTree(label)

    def attach(parent_node: Node, branch) -> None:
        for child in by_parent.get(parent_node.id, []):
            style = STATUS_STYLE.get(child.status, "white")
            title = child.hypothesis.title if child.hypothesis else child.note
            report = child.report
            passing = f"{report.passed}/{report.total}" if report else "--"
            text = f"[{style}]{child.status}[/] {passing} · {title[:70]}"
            if child.regressions:
                text += f" [red](broke {len(child.regressions)})[/]"
            attach(child, branch.add(text))

    if root_nodes:
        attach(root_nodes[0], tree)
    return tree


@app.command()
def report(
    run_report: Path = typer.Argument(..., help="A run report JSON written by `arborist fix`."),
    out: Path = typer.Option(None, "--out", "-o", help="Write the markdown here instead of stdout."),
    summary: bool = typer.Option(False, "--summary", help="One line instead of the full body."),
) -> None:
    """Render a run as the pull request body a reviewer would read."""
    try:
        data = load_report(run_report)
    except (OSError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2) from exc

    text = render_markdown_summary(data) if summary else render_pr_body(data)
    if out:
        out.write_text(text, encoding="utf-8")
        console.print(f"written: [bold]{out}[/]")
    else:
        print(text)


@app.command()
def pr(
    run_report: Path = typer.Argument(..., help="A run report JSON written by `arborist fix`."),
    repo: Path = typer.Option(Path("."), "--repo", "-r", help="The git repository to branch from."),
    branch: str = typer.Option(None, "--branch", "-b", help="Branch name (default: derived from the fix)."),
    base: str = typer.Option(None, "--base", help="Base branch (default: the current one)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Actually create the branch and commit."),
    push: bool = typer.Option(False, "--push", help="Also push the branch to origin. Implies --yes."),
    open_pr: bool = typer.Option(False, "--open", help="Also open the pull request with gh. Implies --push."),
) -> None:
    """Open a pull request from a run, alternatives and all.

    Dry run by default: it prints the branch, the commands and the body, and
    changes nothing. Creating a branch needs --yes; pushing and opening the pull
    request are separate opt-ins on top of that.
    """
    try:
        data = load_report(run_report)
        plan = build_plan(data, repo, branch=branch, base=base)
    except (OSError, ValueError, GitError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2) from exc

    if open_pr:
        push = True
    if push:
        yes = True

    console.print(
        Panel(
            f"[bold]{plan.title}[/]\n\n"
            f"repo    {plan.repo_path}\n"
            f"base    {plan.base}\n"
            f"branch  {plan.branch}\n"
            f"files   {', '.join(plan.files) or '(none)'}",
            title="pull request",
        )
    )

    if not yes:
        console.print("\n[dim]dry run — nothing has changed. Pass --yes to create the branch.[/]\n")
        console.print(plan.describe())
        console.rule("body")
        print(plan.body)
        return

    try:
        result = publish(plan, push=push, open_pr=open_pr)
    except GitError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc

    for step in result.steps:
        console.print(f"[green]✓[/] {step}")
    if result.pr_url:
        console.print(f"\n[bold]{result.pr_url}[/]")
    elif result.committed and not result.pushed:
        console.print(
            f"\n[dim]branch {plan.branch} is committed locally. "
            f"Push it with:[/] git push -u origin {plan.branch}"
        )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Run the web UI."""
    import uvicorn

    uvicorn.run("arborist.server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
