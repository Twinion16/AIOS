import sys

import click
from rich.console import Console
from rich.table import Table

from .config import load_config
from .orchestrator import Orchestrator
from .projects import ProjectRegistry
from .state_machine import TaskState
from .task_types import classify_task, describe_task, select_workflow

console = Console()


@click.group()
def cli():
    """AIOS — multi-agent orchestration with Obsidian shared memory."""
    pass


@cli.command()
@click.argument("task")
@click.option("--project", "-p", default=None,
              help="Project name (default: 'default')")
@click.option("--config", "-c", help="Config file path")
def start(task, project, config):
    """Run TASK through the AIOS agent pipeline.

    The task must be a single quoted argument:

        aios start --project myproj "Add a small feature"
    """
    cfg = load_config(config)
    name = project or "default"
    orch = Orchestrator(cfg, config_path=cfg.get("_config_path"))

    try:
        known = orch.projects.exists(name)
    except Exception:
        known = False
    if not known:
        orch.projects.create(name)
        saved = orch.projects.save_definitions()
        console.print(
            f"[yellow][AIOS] Unknown project '{name}' — created new "
            f"project state.[/yellow]")
        if not saved:
            console.print(
                "[yellow][AIOS] Tip: no config directory yet; run "
                "'aios project create <name>' to persist repository/vault "
                "settings in config/projects.yaml.[/yellow]")
    elif project is None:
        console.print(
            "[dim][AIOS] No --project given, using 'default'.[/dim]")

    task_types = classify_task(task)
    console.print(f"[bold green][AIOS][/bold green] Starting task: {task}")
    console.print(f"[AIOS] Project: {name}")
    console.print(f"[AIOS] Intent: {describe_task(task_types, select_workflow(task_types))}")

    result = orch.run_task(name, task)
    color = "bold green" if result == TaskState.COMPLETE.value else "bold red"
    console.print(f"[{color}][AIOS][/{color}] Final: {result}")


# --------------------------------------------------------------------- project
@cli.group()
def project():
    """Create and inspect AIOS projects."""
    pass


@project.command("list")
@click.option("--config", "-c", help="Config file path")
def project_list(config):
    cfg = load_config(config)
    reg = ProjectRegistry(cfg)
    table = Table(title="AIOS Projects")
    table.add_column("Name")
    table.add_column("State dir")
    table.add_column("Repository")
    table.add_column("Obsidian")
    for name in reg.list():
        p = reg.resolve(name)
        table.add_row(name, str(p.state_dir),
                      str(p.repository or "-"), str(p.obsidian or "-"))
    console.print(table)


@project.command("create")
@click.argument("name")
@click.option("--repository", default="", help="Path to the project codebase")
@click.option("--obsidian", default="",
              help="Vault folder for this project (defaults to "
                   "<vault>/Projects/<name>)")
@click.option("--config", "-c", help="Config file path")
def project_create(name, repository, obsidian, config):
    cfg = load_config(config)
    reg = ProjectRegistry(cfg)
    if reg.exists(name):
        console.print(f"[yellow][AIOS] Project '{name}' already exists.[/yellow]")
        p = reg.resolve(name)
        saved = True
    else:
        p = reg.create(name, repository=repository, obsidian=obsidian)
        saved = reg.save_definitions()
        console.print(f"[green][AIOS] Created project '{name}'[/green]")
    console.print(f"  state dir : {p.state_dir}")
    console.print(f"  repository: {p.repository or '-'}")
    console.print(f"  obsidian  : {p.obsidian or '-'}")
    console.print(f"  registry  : {reg.registry_path if saved else '(not saved)'}")


# --------------------------------------------------------------------- history
@cli.group()
def history():
    """Inspect prior agent conversations (read-only)."""
    pass


def _provider(cfg):
    from .history import HistoryProviderError, OpenCodeHistoryProvider
    try:
        return OpenCodeHistoryProvider(cfg, db_path=(
            (cfg.get("history") or {}).get("opencode") or {}
        ).get("db_path", ""))
    except HistoryProviderError as e:
        console.print(f"[red][AIOS] {e}[/red]")
        raise SystemExit(1)


@history.command("list")
@click.option("--limit", default=20, show_default=True)
@click.option("--config", "-c", help="Config file path")
def history_list(limit, config):
    cfg = load_config(config)
    prov = _provider(cfg)
    table = Table(title=f"OpenCode sessions ({prov.db_path})")
    table.add_column("Session ID")
    table.add_column("Date")
    table.add_column("Title")
    for s in prov.list_sessions(limit=limit):
        table.add_row(s.id, s.date_iso, s.title[:60])
    console.print(table)


@history.command("search")
@click.argument("query")
@click.option("--limit", default=20, show_default=True)
@click.option("--config", "-c", help="Config file path")
def history_search(query, limit, config):
    cfg = load_config(config)
    prov = _provider(cfg)
    hits = prov.search_messages(query, limit=limit)
    if not hits:
        console.print("[yellow][AIOS] No matching messages.[/yellow]")
        return
    console.print(f"[AIOS] {len(hits)} match(es) for: {query}")
    for h in hits:
        snippet = " ".join(h.text[:300].split())
        console.print(f"\n[cyan]{h.session_id}[/cyan] {h.role} "
                      f"score={h.score} terms={','.join(h.matched_terms)}")
        console.print(f"  {snippet}")


# ---------------------------------------------------------------------- status
@cli.command()
@click.option("--config", "-c", help="Config file path")
def status(config):
    """Show the last known state of every project."""
    cfg = load_config(config)
    reg = ProjectRegistry(cfg)
    table = Table(title="AIOS Status")
    table.add_column("Project")
    table.add_column("Status")
    table.add_column("Workflow")
    table.add_column("Updated")
    for name in reg.list():
        state_file = reg.resolve(name).state_dir / "CURRENT_STATE.md"
        status_s = workflow_s = updated = "-"
        if state_file.exists():
            for line in state_file.read_text(encoding="utf-8",
                                             errors="replace").splitlines():
                if line.startswith("- status:"):
                    status_s = line.split(":", 1)[1].strip()
                elif line.startswith("- workflow:"):
                    workflow_s = line.split(":", 1)[1].strip()
                elif line.startswith("- last_updated:"):
                    updated = line.split(":", 1)[1].strip()
        table.add_row(name, status_s, workflow_s, updated)
    console.print(table)


# ------------------------------------------------------------- security-audit
@cli.command("security-audit")
@click.option("--root", default=None,
              help="Repository root to audit (default: current directory)")
def security_audit(root):
    """Audit the repository for secrets, private data, and personal paths.

    Read-only. Scans the working tree, the Git index, and Git history.
    Verdict: PASS (safe to consider publishing) / WARNINGS / FAIL.
    Exit code 1 on FAIL.
    """
    from .security_audit import run_audit
    from rich.markup import escape
    report = run_audit(root)
    console.print(f"[bold]AIOS security audit[/bold] — {escape(str(report.root))}")
    for msg in report.ok:
        console.print(f"  [green][OK][/green]   {escape(msg)}")
    for msg in report.skipped:
        console.print(f"  [dim][SKIP][/dim] {escape(msg)}")
    for msg in report.warnings:
        console.print(f"  [yellow][WARN][/yellow] {escape(msg)}")
    for msg in report.failures:
        console.print(f"  [red][FAIL][/red] {escape(msg)}")
    color = {"PASS": "green", "WARNINGS": "yellow", "FAIL": "red"}[report.verdict]
    console.print(
        f"\n[bold {color}]RESULT: {report.verdict}[/bold {color}] "
        f"({len(report.failures)} failure(s), "
        f"{len(report.warnings)} warning(s))")
    if report.verdict == "FAIL":
        raise SystemExit(1)


def main():
    # legacy Windows consoles (cp1252) must not crash on unicode notes
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    cli()


if __name__ == "__main__":
    main()
