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
            platforms=platform_list,
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
    _set_last_script_result(result)


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
_last_script_result: object = None


def _get_last_script_text() -> str:
    return _last_script_text


def _get_last_script_result():
    return _last_script_result


def _set_last_script_text(text: str) -> None:
    global _last_script_text
    _last_script_text = text


def _set_last_script_result(result) -> None:
    global _last_script_result
    _last_script_result = result


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
    platforms: list[str],
    dry_run: bool,
) -> None:
    """Execute rendering pipeline and display result. Enqueues post on success."""
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

    if result.success and result.video:
        _enqueue_after_render(
            niche=niche,
            product_name=product_name,
            video_path=result.video.video_path,
            platforms=platforms,
            render_meta={
                "duration": result.video.duration,
                "file_size_mb": result.video.file_size_mb,
                "engine": result.video.components.get("engine", "unknown"),
                "captions_count": result.video.components.get("captions_count", 0),
            },
        )


def _enqueue_after_render(
    niche: str,
    product_name: str,
    video_path: Path | str,
    platforms: list[str],
    render_meta: dict | None = None,
) -> None:
    """Save the rendered post to the approval queue."""
    from core.post_queue import PostEntry, PostQueue

    script_result = _get_last_script_result()
    caption = ""
    hashtags: list[str] = []

    if script_result:
        try:
            caption = script_result.captions.primary or ""
        except AttributeError:
            pass
        try:
            hashtags = script_result.hashtags.tags or []
        except AttributeError:
            pass

    entry = PostEntry(
        niche=niche,
        product=product_name,
        video_path=str(video_path),
        caption=caption,
        hashtags=hashtags,
        platforms=platforms,
        render_metadata=render_meta or {},
    )

    queue = PostQueue()
    queue.add(entry)

    console.print(Panel.fit(
        f"[bold green]Post enqueued![/]\n"
        f"ID: {entry.id}\n"
        f"Niche: {entry.niche}\n"
        f"Video: {entry.video_path}\n"
        f"Status: [yellow]{entry.status}[/]\n\n"
        f"Review with: [bold]harpy preview[/]",
        title="Approval Queue",
        border_style="green",
    ))


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
@click.argument("post_id", required=False)
@click.option("--approve", "-a", "do_approve", is_flag=True, help="Approve the post (non-interactive)")
@click.option("--reject", "-r", "do_reject", is_flag=True, help="Reject the post (non-interactive)")
@click.option("--feedback", "-f", default="", help="Rejection feedback")
def preview(post_id: str | None, do_approve: bool, do_reject: bool, feedback: str) -> None:
    """Preview the most recent pending post and approve or reject it.

    Without arguments, shows the latest pending video + caption
    and asks interactively: Aprovar? (s/n)

    Use --approve/--reject for non-interactive (scripted) mode.
    """
    from core.post_queue import PostQueue

    queue = PostQueue()
    posts = queue.load()

    if not posts:
        console.print("[dim]Queue is empty. Run: harpy generate --niche <name> --render-only[/]")
        return

    if post_id:
        post = queue.get(post_id)
        if not post:
            console.print(f"[red]Post not found: {post_id}[/]")
            return
        if do_approve:
            queue.approve(post_id)
            console.print(f"[green]Post {post_id} approved![/]")
            return
        if do_reject:
            queue.remove(post_id)
            console.print(f"[yellow]Post {post_id} rejected and removed.[/]")
            return
        _display_post_detail(post)
        return

    pending = queue.pending()
    if not pending:
        console.print("[green]No pending posts![/]")
        counts = queue.count_by_status()
        if counts:
            console.print(f"  Approved: {counts.get('approved', 0)} | Rejected: {counts.get('rejected', 0)} | Posted: {counts.get('posted', 0)}")
        return

    post = pending[0]

    _display_post_preview(post)

    if do_approve:
        queue.approve(post.id)
        console.print(f"\n[green]Post {post.id} approved![/]")
        return
    if do_reject:
        queue.remove(post.id)
        console.print(f"\n[yellow]Post {post.id} rejected and removed.[/]")
        return

    choice = click.prompt("\nAprovar? (s/n)", type=str, default="n").strip().lower()
    if choice in ("s", "y", "sim", "yes"):
        queue.approve(post.id)
        console.print(f"[green]Post {post.id} approved![/]")
        console.print(f"[dim]Publish with: harpy publish --post {post.id} --platform tiktok[/]")
    else:
        queue.remove(post.id)
        console.print(f"[yellow]Post {post.id} rejected and removed from queue.[/]")


def _display_post_preview(post) -> None:
    """Show a compact post preview with video info, caption, and hashtags."""
    console.print(Panel.fit(
        f"[bold]ID:[/] {post.id} | [bold]Status:[/] [yellow]{post.status}[/]\n"
        f"[bold]Niche:[/] {post.niche}\n"
        f"[bold]Product:[/] {post.product}\n"
        f"[bold]Video:[/] [dim]{post.video_path}[/]\n"
        f"[bold]Platforms:[/] {', '.join(post.platforms)}\n"
        f"[bold]Created:[/] {post.created_at[:16].replace('T', ' ')}",
        title=f"Post Preview — {post.niche}",
        border_style="cyan",
    ))

    if post.caption:
        console.print(Panel.fit(
            post.caption[:600],
            title="Caption",
            border_style="green",
        ))

    if post.hashtags:
        console.print(Panel.fit(
            " ".join(post.hashtags[:15]),
            title="Hashtags",
            border_style="blue",
        ))

    if post.render_metadata:
        meta = post.render_metadata
        console.print(
            f"  [dim]Video: {meta.get('duration', '?')}s | "
            f"{meta.get('file_size_mb', '?')} MB | "
            f"Captions: {meta.get('captions_count', '?')} segments[/]"
        )


def _display_post_detail(post) -> None:
    """Show full detail view (for non-interactive inspection)."""
    from core.post_queue import PostQueue
    import os

    queue = PostQueue()

    console.print(Panel.fit(
        f"[bold]ID:[/] {post.id}\n"
        f"[bold]Status:[/] {post.status}\n"
        f"[bold]Niche:[/] {post.niche}\n"
        f"[bold]Product:[/] {post.product}\n"
        f"[bold]Video:[/] {post.video_path}\n"
        f"[bold]Platforms:[/] {', '.join(post.platforms)}\n"
        f"[bold]Created:[/] {post.created_at}",
        title="Post Detail",
        border_style="blue",
    ))

    if post.caption:
        console.print(Panel.fit(
            post.caption[:500],
            title="Caption",
            border_style="green",
        ))

    if post.hashtags:
        console.print(Panel.fit(
            " ".join(post.hashtags[:20]),
            title="Hashtags",
            border_style="blue",
        ))

    if post.render_metadata:
        meta = post.render_metadata
        console.print(f"  [dim]Duration: {meta.get('duration', '?')}s | "
                      f"Size: {meta.get('file_size_mb', '?')} MB | "
                      f"Engine: {meta.get('engine', '?')} | "
                      f"Captions: {meta.get('captions_count', '?')}[/]")

    console.print()
    console.print(Panel.fit(
        "[bold]Actions:[/]\n"
        f"  [green]harpy preview {post.id} --approve[/]   → approve for publishing\n"
        f"  [red]harpy preview {post.id} --reject[/]   → reject and remove\n"
        f"  [yellow]harpy publish --post {post.id}[/]   → publish approved post",
        title="Commands",
        border_style="yellow",
    ))


@cli.command()
@click.option("--platform", "-p", default="tiktok", help="Target platform")
@click.option("--post", "-P", "post_id", default="", help="Post ID from the queue (single)")
@click.option("--dry-run", is_flag=True, help="Simulate without posting. Generates fallback .txt")
def publish(platform: str, post_id: str, dry_run: bool) -> None:
    """Publish ALL approved posts to TikTok or Instagram.

    Without --post, publishes every approved post in the queue.
    Always generates fallback .txt files for manual posting.
    """
    from core.post_queue import PostQueue
    from core.publish import PublishAgent

    valid_platforms = ["tiktok", "instagram", "reels"]
    if platform == "reels":
        platform = "instagram"
    if platform not in valid_platforms:
        console.print(f"[red]Invalid platform: {platform}. Use: tiktok, instagram[/]")
        return

    queue = PostQueue()
    agent = PublishAgent()

    if post_id:
        post = queue.get(post_id)
        if not post:
            console.print(f"[red]Post not found: {post_id}[/]")
            return
        if post.status != "approved":
            console.print(
                f"[yellow]Post {post_id} is '{post.status}'. "
                f"Approve it first: harpy preview[/]"
            )
            return
        approved_posts = [post]
    else:
        approved_posts = queue.approved()
        if not approved_posts:
            console.print("[yellow]No approved posts. Approve with: harpy preview[/]")
            return

    console.print(Panel.fit(
        f"[bold]Platform:[/] {platform}\n"
        f"[bold]Posts to publish:[/] {len(approved_posts)}\n"
        f"[bold]Mode:[/] {'[yellow]Dry Run[/]' if dry_run else '[green]Live[/]'}",
        title="Publishing Content",
        border_style="magenta",
    ))

    results = agent.publish_all_from_queue(platform=platform, dry_run=dry_run)

    table = Table(title="Publish Results")
    table.add_column("Post ID", style="dim")
    table.add_column("Product", style="bold")
    table.add_column("Status")
    table.add_column("Fallback")

    for r in results:
        status_icon = "[green]OK[/]" if r.success else "[yellow]fallback[/]"
        table.add_row(
            r.post_id or "—",
            r.video_path.split("/")[-1] if r.video_path else "—",
            status_icon,
            r.fallback_path.split("/")[-1] if r.fallback_path else "—",
        )

    console.print(table)

    if results:
        fallbacks = [r for r in results if r.fallback_path]
        if fallbacks:
            console.print(
                f"\n[dim]{len(fallbacks)} fallback .txt file(s) generated. "
                "Open for step-by-step manual posting instructions.[/]"
            )
            for r in fallbacks:
                console.print(f"  [dim]→ {r.fallback_path}[/]")


@cli.command()
@click.option("--analytics", "-a", is_flag=True, help="Include performance analytics")
def status(analytics: bool) -> None:
    """Show queue status, flywheels, and optionally analytics."""
    from core.post_queue import PostQueue

    console.print(Text("Harpy Pipeline Status", style="bold underline"))

    # --- Post Queue ---
    queue = PostQueue()
    counts = queue.count_by_status()
    total = sum(counts.values())

    console.print()
    console.print(Panel.fit(
        f"Total posts: {total} | "
        f"[yellow]Pending: {counts.get('pending', 0)}[/] | "
        f"[green]Approved: {counts.get('approved', 0)}[/] | "
        f"[red]Rejected: {counts.get('rejected', 0)}[/] | "
        f"[dim]Posted: {counts.get('posted', 0)}[/]",
        title="Post Queue",
        border_style="blue",
    ))

    posts = queue.load()
    if posts:
        table = Table(title="Posts")
        table.add_column("ID", style="dim")
        table.add_column("Niche", style="cyan")
        table.add_column("Product", style="bold")
        table.add_column("Status")
        table.add_column("Platforms")
        table.add_column("Created")

        for p in sorted(posts, key=lambda x: x.created_at, reverse=True):
            status_color = {
                "pending": "yellow",
                "approved": "green",
                "rejected": "red",
                "posted": "dim",
            }.get(p.status, "white")

            table.add_row(
                p.id,
                p.niche,
                p.product[:25] if p.product else "—",
                f"[{status_color}]{p.status}[/]",
                ", ".join(p.platforms),
                p.created_at[:16].replace("T", " "),
            )

        console.print(table)
    else:
        console.print("  [dim]No posts yet. Run: harpy generate --niche <name> --render-only[/]")

    # --- Analytics ---
    if analytics and posts:
        _display_analytics()

    # --- Flywheels ---
    try:
        from core.config import load_config
        from core.queue import QueueManager
        config = load_config(require_api_key=False)
        qm = QueueManager(config.output_dir)
        flywheels = qm.load_all()
    except Exception:
        flywheels = []

    if flywheels:
        console.print()
        ftable = Table(title="Flywheels")
        ftable.add_column("Niche", style="cyan")
        ftable.add_column("Status", style="green")
        ftable.add_column("Stage", style="yellow")
        ftable.add_column("Iteration", justify="right")
        ftable.add_column("Platforms")

        for fw in flywheels:
            status_color = "green" if fw.status == "active" else "dim"
            stage = fw.current_stage or "complete"
            ftable.add_row(
                fw.niche,
                f"[{status_color}]{fw.status}[/]",
                stage,
                str(fw.iteration),
                ", ".join(fw.target_platforms),
            )

        console.print(ftable)

    if not posts and not flywheels:
        console.print("\n[dim]Run [bold]harpy generate --niche <name> --render-only[/] to start.[/]")


def _display_analytics() -> None:
    """Fetch and display analytics from the AnalyticsAgent."""
    try:
        from core.analytics import AnalyticsAgent
        agent = AnalyticsAgent()
        report = agent.generate_report()

        console.print()
        if report.metrics:
            m = report.metrics
            console.print(Panel.fit(
                f"[bold]{m.platform.upper()}[/]: {m.views:,} views, "
                f"{m.likes} likes, {m.comments} comments, "
                f"{m.shares} shares\n"
                f"Engagement rate: {m.engagement_rate:.1f}% | "
                f"Clicks: {m.click_through}\n"
                f"[dim]Data: {m.fetched_at}[/]",
                title="Analytics (simulated)",
                border_style="green",
            ))

        if report.suggestions:
            s_table = Table(title="Improvement Suggestions")
            s_table.add_column("Priority", style="bold")
            s_table.add_column("Category", style="cyan")
            s_table.add_column("Suggestion")

            for s in report.suggestions[:5]:
                sev_color = {"high": "red", "medium": "yellow", "low": "dim"}.get(s.severity, "white")
                s_table.add_row(
                    f"[{sev_color}]{s.severity.upper()}[/]",
                    s.category,
                    s.suggestion[:100],
                )

            console.print(s_table)
    except Exception as e:
        console.print(f"[dim]Analytics unavailable: {e}[/]")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
