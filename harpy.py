#!/usr/bin/env python3
"""Harpy — End-to-end affiliate marketing automation for TikTok & Instagram."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

BANNER = """
┏━┓         ┏┓       
┃┣┫┏┓┏┓┏━┓ ┏┓┣┛┏┓
┃┃┃┣┫┣┫┣┳┛ ┃ ┃ ┫ 
┗┻┛┗┛┗┛┗┻┛ ┗┛┗┛┗┛
Affiliate Marketing Flywheel
"""


def _get_research_agent(dry_run: bool = False):
    """Lazy-load the ResearchAgent with proper error handling."""
    try:
        from core.research import ResearchAgent
        from core.config import load_config

        if dry_run:
            config = load_config(require_api_key=False)
        else:
            config = load_config(require_api_key=True)
        return ResearchAgent(config)
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/]")
        console.print("[dim]Set DEEPSEEK_API_KEY in .env or use --dry-run.[/]")
        sys.exit(1)


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Harpy — From research to published video, with a single approval."""
    if ctx.invoked_subcommand is None:
        console.print(Text(BANNER, style="bold cyan"))
        console.print("Run [bold]harpy --help[/] to see available commands.\n")


@cli.command()
@click.option("--niche", "-n", required=True, help="Product niche to target")
@click.option(
    "--platforms", "-p",
    default="tiktok,instagram",
    help="Target platforms (comma-separated)",
)
@click.option("--dry-run", is_flag=True, help="Simulate without API calls")
@click.option(
    "--research-only", is_flag=True,
    help="Run only the research phase (S1) and display results",
)
@click.option(
    "--script-only", is_flag=True,
    help="Run research + script generation (S1 + S2) and display results",
)
@click.option(
    "--render-only", is_flag=True,
    help="Run full pipeline (S1 + S2 + render) and output video",
)
def generate(
    niche: str, platforms: str, dry_run: bool,
    research_only: bool, script_only: bool, render_only: bool,
) -> None:
    """Generate content for a niche.

    Runs the full flywheel pipeline:
    S1 Research \u2192 S2 Content \u2192 S3 Blog \u2192 S4 Landing \u2192 S5 Distribution \u2192 S6 Analytics
    """
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]

    phase_label = ""
    if research_only:
        phase_label = "\n[bold]Phase:[/] [cyan]Research Only[/]"
    elif script_only:
        phase_label = "\n[bold]Phase:[/] [magenta]Research + Script[/]"
    elif render_only:
        phase_label = "\n[bold]Phase:[/] [yellow]Full Pipeline (Render)[/]"

    console.print(Panel.fit(
        f"[bold]Niche:[/] {niche}\n"
        f"[bold]Platforms:[/] {', '.join(platform_list)}\n"
        f"[bold]Mode:[/] {'[yellow]Dry Run[/]' if dry_run else '[green]Live[/]'}"
        + phase_label,
        title="Generating Content",
        border_style="cyan",
    ))

    # --- S1: Research Phase ---
    research_result = None
    if research_only or script_only or render_only or not dry_run:
        research_result = _run_research_phase(niche, dry_run)

    if research_only:
        return

    # --- S2: Script Phase ---
    product_name = niche
    research_ctx = ""
    if research_result and research_result.program:
        product_name = research_result.program.product_name or niche
        research_ctx = research_result.summary or ""

    if script_only or render_only or not dry_run:
        _run_script_phase(niche, product_name, platform_list, research_ctx, dry_run)

    if script_only:
        return

    # --- S3: Render Phase ---
    if render_only or not dry_run:
        script_text = _get_last_script_text()
        _run_render_phase(
            niche=niche,
            product_name=product_name,
            script_text=script_text,
            dry_run=dry_run,
        )

    if render_only:
        return

    # --- Full pipeline skeleton ---
    stages = [
        ("research", "S1 \u2014 Research & Discovery", "cyan"),
        ("content", "S2 \u2014 Content Creation", "green"),
        ("landing", "S3+S4 \u2014 Blog & Landing Pages", "yellow"),
        ("distribution", "S5 \u2014 Distribution (TT + IG)", "magenta"),
        ("analytics", "S6 \u2014 Analytics & Feedback", "blue"),
    ]

    table = Table(title="Pipeline Stages")
    table.add_column("Stage", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Status")

    for key, name, color in stages:
        status = "[green]complete[/]" if (key == "research" and not dry_run) else "[yellow]pending[/]" if dry_run else "[dim]pending...[/]"
        table.add_row(key, name, status)

    console.print(table)

    if dry_run:
        console.print("\n[yellow]Dry run complete. No API calls were made.[/]")
    else:
        console.print("\n[yellow]Full pipeline will be implemented in next rounds.[/]")


def _run_research_phase(niche: str, dry_run: bool):
    """Execute S1 research and display results. Returns the research output."""
    with console.status(f"[cyan]Researching '{niche}'...[/]"):
        try:
            agent = _get_research_agent(dry_run=dry_run)
            result = agent.run_full_research(niche, dry_run=dry_run)
        except Exception as e:
            console.print(f"[red]Research failed: {e}[/]")
            return None

    _display_trends(result.trends)
    console.print()
    _display_program(result.program)
    console.print()
    _display_traffic(result.traffic)

    console.print(Panel.fit(
        result.summary,
        title="Research Summary",
        border_style="cyan",
    ))
    return result


def _display_trends(trends) -> None:
    if not trends or not trends.top_format:
        return
    table = Table(title="Trend Research", border_style="cyan")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value")
    table.add_row("Best Format", trends.top_format)
    table.add_row("Avg Engagement", str(trends.avg_engagement))
    table.add_row("Best Hook", trends.best_hook)
    table.add_row("Content Gap", trends.content_gap or "—")
    table.add_row("Benchmark (views)", f"{trends.benchmark_views:,}")
    console.print(table)


def _display_program(program) -> None:
    if not program or not program.product_name:
        return
    table = Table(title="Affiliate Program", border_style="green")
    table.add_column("Field", style="bold green")
    table.add_column("Value")
    table.add_row("Product", f"[bold]{program.product_name}[/]")
    table.add_row("Commission", program.commission)
    table.add_row("Cookie Days", str(program.cookie_days))
    table.add_row("Stars", "\u2605 " * min(program.stars // 20, 5) if program.stars else "—")
    table.add_row("Traffic Score", f"{program.traffic_score}/100")
    table.add_row("Justification", program.justification)
    console.print(table)


def _display_traffic(traffic) -> None:
    if not traffic or not traffic.product_name:
        return
    table = Table(title="Traffic Analysis", border_style="blue")
    table.add_column("Metric", style="bold blue")
    table.add_column("Value")
    table.add_row("Monthly Visits", traffic.monthly_visits or "—")
    table.add_row("Global Rank", traffic.global_rank or "—")
    table.add_row("Bounce Rate", traffic.bounce_rate or "—")
    table.add_row("Top Sources", ", ".join(traffic.top_sources) if traffic.top_sources else "—")
    table.add_row("Score", f"{traffic.score}/100")
    table.add_row("Verdict", traffic.verdict or "—")
    console.print(table)


def _get_script_agent(dry_run: bool = False):
    """Lazy-load the ScriptAgent."""
    from core.script import ScriptAgent
    from core.config import load_config
    if dry_run:
        config = load_config(require_api_key=False)
    else:
        config = load_config(require_api_key=True)
    return ScriptAgent(config)


def _run_script_phase(
    niche: str, product_name: str,
    platforms: list[str], research_ctx: str,
    dry_run: bool,
) -> None:
    """Execute S2 script generation and display results."""
    with console.status(f"[magenta]Writing scripts for '{product_name}'...[/]"):
        try:
            agent = _get_script_agent(dry_run=dry_run)
            result = agent.run_full_script(
                product_name=product_name,
                niche=niche,
                platforms=platforms,
                research_context=research_ctx,
                dry_run=dry_run,
            )
        except Exception as e:
            console.print(f"[red]Script generation failed: {e}[/]")
            return

    console.print()
    _display_script(result.script_tiktok, "TikTok")
    if result.script_instagram.script:
        console.print()
        _display_script(result.script_instagram, "Instagram Reels")
    console.print()
    _display_captions(result.captions)
    console.print()
    _display_hashtags(result.hashtags)

    console.print(Panel.fit(
        result.summary,
        title="Script Summary",
        border_style="magenta",
    ))

    _set_last_script_text(result.script_tiktok.script or result.script_instagram.script or "")


def _display_script(script, platform: str) -> None:
    if not script or not script.script:
        return
    lines = script.script.strip().split("\n")
    shortened = "\n".join(lines[:50])
    if len(lines) > 50:
        shortened += f"\n... ({len(lines) - 50} more lines)"

    console.print(Panel.fit(
        f"[bold]Hook:[/] {script.hook}\n"
        f"[bold]Duration:[/] {script.duration}\n"
        f"[bold]CTA:[/] {script.cta}\n\n"
        f"{shortened}",
        title=f"Script — {platform}",
        border_style="magenta",
    ))


def _display_captions(captions) -> None:
    if not captions or not captions.primary:
        return
    table = Table(title="Captions", border_style="green")
    table.add_column("Type", style="bold green")
    table.add_column("Text")
    table.add_row("[bold]Primary[/]", captions.primary[:300])
    for i, alt in enumerate(captions.alternatives[:3]):
        table.add_row(f"Alt #{i + 1}", alt[:300])
    console.print(table)


def _display_hashtags(hashtags) -> None:
    if not hashtags or not hashtags.tags:
        return
    tag_str = " ".join(hashtags.tags[:20])
    console.print(Panel.fit(
        tag_str,
        title="Hashtags",
        border_style="blue",
    ))
    if hashtags.grouped:
        for group, tags in hashtags.grouped.items():
            console.print(f"  [dim]{group}:[/] {' '.join(tags)}")


_last_script_text: str = ""


def _get_last_script_text() -> str:
    return _last_script_text


def _set_last_script_text(text: str) -> None:
    global _last_script_text
    _last_script_text = text


def _get_render_agent(dry_run: bool = False):
    """Lazy-load the RenderAgent."""
    from core.render import RenderAgent
    from core.config import load_config
    if dry_run:
        config = load_config(require_api_key=False)
    else:
        config = load_config(require_api_key=True)
    return RenderAgent(config)


def _run_render_phase(
    niche: str,
    product_name: str,
    script_text: str,
    dry_run: bool,
) -> None:
    """Execute rendering pipeline and display result."""
    with console.status(f"[yellow]Rendering video for '{product_name}'...[/]"):
        try:
            agent = _get_render_agent(dry_run=dry_run)
            result = agent.render_video(
                script_text=script_text,
                niche=niche,
                product_name=product_name,
                output_dir=f"outputs/{niche.replace(' ', '_')}",
            )
        except Exception as e:
            console.print(f"[red]Render failed: {e}[/]")
            return

    _display_render_result(result)


def _display_render_result(result) -> None:
    if not result:
        console.print("[red]No render result.[/]")
        return

    table = Table(title="Render Output", border_style="yellow")
    table.add_column("Component", style="bold yellow")
    table.add_column("Status")

    status = "[green]OK[/]" if result.success else "[red]FAILED[/]"
    table.add_row("Overall", status)

    if result.video:
        v = result.video
        table.add_row("Video", str(v.video_path))
        table.add_row("Duration", f"{v.duration:.1f}s")
        table.add_row("Resolution", f"{v.resolution[0]}x{v.resolution[1]}")
        table.add_row("File Size", f"{v.file_size_mb:.1f} MB")
        table.add_row("Clips Used", str(v.components.get("clips_count", "?")))
        table.add_row("Captions", str(v.components.get("captions_count", "?")))

    if result.voiceover_path:
        table.add_row("Voiceover", f"[dim]{result.voiceover_path}[/]")
    if result.clips_paths:
        table.add_row("Stock Clips", str(len(result.clips_paths)))
    if result.errors:
        for err in result.errors:
            table.add_row("Error", f"[red]{err[:80]}[/]")

    console.print(table)

    if result.success and result.video:
        console.print(Panel.fit(
            f"[bold]Video ready:[/] {result.video.video_path}\n"
            f"[bold]Duration:[/] {result.video.duration:.1f}s\n"
            f"Preview with: [dim]ffplay {result.video.video_path}[/]",
            title="Render Complete",
            border_style="yellow",
        ))


@cli.command()
@click.argument("niche_slug", required=False)
def preview(niche_slug: str | None) -> None:
    """Preview generated content before publishing."""
    if niche_slug:
        console.print(Panel.fit(
            f"Previewing content for [bold cyan]{niche_slug}[/]",
            title="Content Preview",
        ))
    else:
        console.print("[yellow]No niche specified. Usage: harpy preview <niche-slug>[/]")
        return

    sections = [
        ("TikTok / Reels Script", "15-30s short-form video script"),
        ("Instagram Feed Post", "Caption + hashtag strategy"),
        ("Landing Page", "AIDA-framework HTML landing page"),
        ("Bio Link Page", "Linktree-style bio link hub"),
        ("30-Day Calendar", "Publishing schedule for TT + IG"),
    ]

    for title, desc in sections:
        console.print(f"\n[bold]{title}[/]")
        console.print(f"  [dim]{desc}[/]")
        console.print(f"  [dim]→ Content will be rendered here after generation.[/]")

    console.print(Panel.fit(
        "[bold]Actions:[/]\n"
        "  [y] approve    [/] → publish content\n"
        "  [n] reject     [/] → regenerate with feedback\n"
        "  [e] edit       [/] → refine manually",
        title="Human-in-the-Loop",
        border_style="green",
    ))


@cli.command()
@click.option("--platform", "-p", default="tiktok", help="Target platform")
@click.option("--niche", "-n", required=True, help="Niche slug to publish")
@click.option("--dry-run", is_flag=True, help="Simulate without posting")
def publish(platform: str, niche: str, dry_run: bool) -> None:
    """Publish approved content to TikTok or Instagram."""
    valid_platforms = ["tiktok", "instagram", "reels"]
    if platform not in valid_platforms:
        console.print(f"[red]Invalid platform: {platform}. Use: {', '.join(valid_platforms)}[/]")
        return

    console.print(Panel.fit(
        f"[bold]Platform:[/] {platform}\n"
        f"[bold]Niche:[/] {niche}\n"
        f"[bold]Mode:[/] {'[yellow]Dry Run[/]' if dry_run else '[green]Live[/]'}",
        title="Publishing Content",
        border_style="magenta",
    ))

    if platform == "tiktok":
        console.print("[dim]→ Posting video to TikTok via API...[/]")
    elif platform == "instagram":
        console.print("[dim]→ Posting Reel + Feed post to Instagram via API...[/]")
    elif platform == "reels":
        console.print("[dim]→ Posting Reels to Instagram + TikTok...[/]")

    if dry_run:
        console.print("[yellow]Dry run — nothing was posted.[/]")
    else:
        console.print("[yellow]Publish endpoint not yet connected. Use dry-run mode for now.[/]")


@cli.command()
def status() -> None:
    """Show pipeline status and active flywheels."""
    console.print(Text("Harpy Pipeline Status", style="bold underline"))

    try:
        from core.config import load_config
        from core.queue import QueueManager
        config = load_config()
        qm = QueueManager(config.output_dir)
        flywheels = qm.load_all()
    except Exception:
        flywheels = []

    if not flywheels:
        table = Table(title="Flywheels")
        table.add_column("Niche", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Stage", style="yellow")
        table.add_column("Iteration", justify="right")
        table.add_column("Platforms")
        table.add_row(
            "No flywheels yet",
            "[dim]—[/]",
            "—",
            "—",
            "—",
        )
        console.print(table)
        console.print("\n[dim]Run [bold]harpy generate --niche <name>[/] to start.[/]")
        return

    table = Table(title="Flywheels")
    table.add_column("Niche", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Stage", style="yellow")
    table.add_column("Iteration", justify="right")
    table.add_column("Platforms")

    for fw in flywheels:
        status_color = "green" if fw.status == "active" else "dim"
        stage = fw.current_stage or "complete"
        table.add_row(
            fw.niche,
            f"[{status_color}]{fw.status}[/]",
            stage,
            str(fw.iteration),
            ", ".join(fw.target_platforms),
        )

    console.print(table)
    console.print("\n[dim]Run [bold]harpy generate --niche <name>[/] to start a new flywheel.[/]")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
