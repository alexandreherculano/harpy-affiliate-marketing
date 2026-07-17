"""Harpy CLI — human-in-the-loop affiliate marketing flywheel manager."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.config import load_config
from core.logger import get_logger
from core.orchestrator import Orchestrator
from core.queue import QueueManager

console = Console()
logger = get_logger()


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Harpy — End-to-end affiliate marketing automation flywheel."""
    ctx.ensure_object(dict)


@cli.command()
@click.argument("niche")
@click.option("--platforms", "-p", default="tiktok,instagram",
              help="Target platforms (comma-separated)")
def new(niche: str, platforms: str) -> None:
    """Create a new flywheel for a niche."""
    config = load_config()
    queue = QueueManager(config.output_dir)

    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
    fw = queue.create_flywheel(niche=niche, platforms=platform_list)

    console.print(Panel.fit(
        f"[bold green]Flywheel created[/]\n"
        f"ID: {fw.flywheel_id}\n"
        f"Niche: {fw.niche}\n"
        f"Platforms: {', '.join(fw.target_platforms)}\n"
        f"Stage: {fw.current_stage}",
        title="Harpy Flywheel",
    ))


@cli.command()
@click.argument("niche_slug", required=False)
@click.option("--auto", is_flag=True, help="Run without human approval prompts")
def run(niche_slug: Optional[str], auto: bool) -> None:
    """Run or resume a flywheel. Prompts for approval at each stage."""
    config = load_config()
    orchestrator = Orchestrator(config)

    if niche_slug:
        fw = orchestrator.queue.get_flywheel(niche_slug)
        if not fw:
            console.print(f"[red]Flywheel not found: {niche_slug}[/]")
            sys.exit(1)
    else:
        flywheels = orchestrator.queue.load_all()
        active = [fw for fw in flywheels if fw.status == "active"]
        if not active:
            console.print("[yellow]No active flywheels. Use 'harpy new <niche>' to create one.[/]")
            sys.exit(0)
        if len(active) == 1:
            fw = active[0]
        else:
            fw = _select_flywheel(active)

    if not fw:
        sys.exit(0)

    console.print(Panel.fit(
        f"[bold]Resuming flywheel[/]\n"
        f"Niche: {fw.niche} | Iteration: {fw.iteration}\n"
        f"Stage: {fw.current_stage} | Platforms: {', '.join(fw.target_platforms)}",
        title=f"Flywheel: {fw.flywheel_id}",
    ))

    try:
        orchestrator.run_full_flywheel(fw, interactive=not auto)
        console.print(f"\n[bold green]Flywheel {fw.flywheel_id} complete![/]")
        console.print(f"Niche: {fw.niche} — Iteration {fw.iteration}")
    except KeyboardInterrupt:
        console.print("\n[yellow]Flywheel paused. Resume with: harpy run {fw.niche_slug}[/]")
        sys.exit(0)
    except Exception as e:
        logger.exception("Flywheel run failed")
        console.print(f"[red]Error: {e}[/]")
        sys.exit(1)


@cli.command()
def status() -> None:
    """Show status of all flywheels."""
    config = load_config()
    queue = QueueManager(config.output_dir)
    flywheels = queue.load_all()

    if not flywheels:
        console.print("[yellow]No flywheels found. Use 'harpy new <niche>' to create one.[/]")
        return

    table = Table(title="Harpy Flywheels")
    table.add_column("Niche", style="cyan")
    table.add_column("Slug", style="dim")
    table.add_column("Status", style="green")
    table.add_column("Stage", style="yellow")
    table.add_column("Iteration", justify="right")
    table.add_column("Platforms")

    for fw in flywheels:
        status_color = "green" if fw.status == "active" else "dim"
        stage = fw.current_stage or "complete"
        table.add_row(
            fw.niche,
            fw.niche_slug,
            f"[{status_color}]{fw.status}[/]",
            stage,
            str(fw.iteration),
            ", ".join(fw.target_platforms),
        )

    console.print(table)


@cli.command()
@click.argument("niche_slug")
def show(niche_slug: str) -> None:
    """Show details of a specific flywheel."""
    config = load_config()
    queue = QueueManager(config.output_dir)
    fw = queue.get_flywheel(niche_slug)

    if not fw:
        console.print(f"[red]Flywheel not found: {niche_slug}[/]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold]{fw.niche}[/] ({fw.flywheel_id})\n"
        f"Status: {fw.status} | Iteration: {fw.iteration}\n"
        f"Platforms: {', '.join(fw.target_platforms)}",
        title="Flywheel Details",
    ))

    table = Table(title="Stages")
    table.add_column("Stage", style="cyan")
    table.add_column("Status", style="yellow")
    table.add_column("Skills", style="dim")
    table.add_column("Approved", justify="center")

    for stage_key in ["research", "content", "landing", "distribution", "analytics"]:
        st = fw.stages.get(stage_key)
        if st:
            approved = "✓" if st.approved_by_user else ("✗" if st.approved_by_user is False else "-")
            table.add_row(
                stage_key,
                st.status,
                ", ".join(st.skills_executed[:3]) + ("..." if len(st.skills_executed) > 3 else ""),
                approved,
            )

    console.print(table)


@cli.command()
@click.argument("niche_slug")
@click.argument("stage")
def approve(niche_slug: str, stage: str) -> None:
    """Approve a stage without entering the interactive loop."""
    config = load_config()
    orchestrator = Orchestrator(config)
    fw = orchestrator.queue.get_flywheel(niche_slug)

    if not fw:
        console.print(f"[red]Flywheel not found: {niche_slug}[/]")
        sys.exit(1)

    orchestrator.approve_stage(fw, stage)
    console.print(f"[green]Stage '{stage}' approved for {fw.niche}.[/]")


@cli.command()
@click.argument("niche_slug")
@click.argument("stage")
@click.option("--feedback", "-f", prompt="Rejection feedback", help="Reason for rejection")
def reject(niche_slug: str, stage: str, feedback: str) -> None:
    """Reject a stage with feedback for re-execution."""
    config = load_config()
    orchestrator = Orchestrator(config)
    fw = orchestrator.queue.get_flywheel(niche_slug)

    if not fw:
        console.print(f"[red]Flywheel not found: {niche_slug}[/]")
        sys.exit(1)

    orchestrator.reject_stage(fw, stage, feedback)
    console.print(f"[yellow]Stage '{stage}' rejected. Re-run with: harpy run {niche_slug}[/]")


@cli.command()
@click.argument("niche_slug")
@click.confirmation_option(prompt="Are you sure you want to delete this flywheel?")
def delete(niche_slug: str) -> None:
    """Delete a flywheel permanently."""
    config = load_config()
    queue = QueueManager(config.output_dir)
    if queue.delete_flywheel(niche_slug):
        console.print(f"[green]Deleted flywheel: {niche_slug}[/]")
    else:
        console.print(f"[red]Flywheel not found: {niche_slug}[/]")


def _select_flywheel(flywheels: list) -> object:
    table = Table(title="Select Flywheel")
    table.add_column("#", style="dim")
    table.add_column("Niche", style="cyan")
    table.add_column("Stage", style="yellow")
    table.add_column("Iteration", justify="right")

    for i, fw in enumerate(flywheels, 1):
        table.add_row(str(i), fw.niche, fw.current_stage or "done", str(fw.iteration))

    console.print(table)
    choice = click.prompt("Select flywheel number (or 0 to cancel)", type=int, default=0)
    if choice == 0:
        return None
    if 1 <= choice <= len(flywheels):
        return flywheels[choice - 1]
    return None


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
