"""AnalyticsAgent — track post performance and suggest improvements.

Connects to TikTok/Instagram APIs (when configured) or uses the post queue
to provide performance analytics and actionable feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.config import Config, load_config
from core.logger import get_logger

logger = get_logger()


@dataclass
class PostMetrics:
    post_id: str
    platform: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    engagement_rate: float = 0.0
    click_through: int = 0
    fetched_at: str = ""


@dataclass
class ImprovementSuggestion:
    category: str
    severity: str  # low, medium, high
    suggestion: str
    metric: str = ""


@dataclass
class AnalyticsReport:
    post_id: str
    niche: str = ""
    product: str = ""
    metrics: PostMetrics | None = None
    suggestions: list[ImprovementSuggestion] = field(default_factory=list)
    summary: str = ""
    generated_at: str = ""


class AnalyticsAgent:
    """Track performance and generate improvement suggestions."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config(require_api_key=False)

    def track_performance(
        self,
        post_id: str,
        platform: str = "tiktok",
    ) -> PostMetrics:
        """Fetch post performance data from the platform.

        Falls back to mock/simulated data when API is not configured.
        """
        now = datetime.now(timezone.utc).isoformat()

        if platform == "tiktok":
            token = getattr(self.config, "tiktok_access_token", None) or ""
            if token:
                return self._fetch_tiktok_metrics(post_id, token, now)
        elif platform == "instagram":
            token = getattr(self.config, "instagram_access_token", None) or ""
            if token:
                return self._fetch_instagram_metrics(post_id, token, now)

        return self._mock_metrics(post_id, platform)

    def track_all_posts(self) -> dict[str, PostMetrics]:
        """Fetch metrics for all posted content from the queue."""
        from core.post_queue import PostQueue

        queue = PostQueue()
        posted = [p for p in queue.load() if p.status == "posted"]
        results: dict[str, PostMetrics] = {}

        for post in posted:
            for platform in post.platforms:
                metrics = self.track_performance(post.id, platform)
                results[post.id] = metrics

        return results

    def suggest_improvements(
        self,
        metrics: PostMetrics | list[PostMetrics] | None = None,
    ) -> list[ImprovementSuggestion]:
        """Analyze metrics and generate actionable improvement suggestions."""
        if metrics is None:
            return self._baseline_suggestions()

        if isinstance(metrics, PostMetrics):
            metrics = [metrics]

        suggestions: list[ImprovementSuggestion] = []

        for m in metrics:
            if m.views > 0:
                er = m.engagement_rate or self._calc_engagement(m)
                m.engagement_rate = er

                if er < 3.0:
                    suggestions.append(ImprovementSuggestion(
                        category="hook",
                        severity="high",
                        suggestion="Engagement rate below 3%. Test stronger hooks in the first 3 seconds. Use pattern interrupts (fast cuts, text overlay, question).",
                        metric=f"ER={er:.1f}%",
                    ))

                if m.views > 1000 and m.likes / max(m.views, 1) < 0.03:
                    suggestions.append(ImprovementSuggestion(
                        category="content",
                        severity="medium",
                        suggestion="Low like-to-view ratio. Try adding a clear CTA asking viewers to like/save. Test different value propositions.",
                        metric=f"likes/views={(m.likes / max(m.views, 1)):.3f}",
                    ))

                if m.comments == 0 and m.views > 500:
                    suggestions.append(ImprovementSuggestion(
                        category="engagement",
                        severity="medium",
                        suggestion="Zero comments despite views. Add a question in your caption to spark discussion. Reply to every comment in the first hour.",
                        metric="comments=0",
                    ))

                if m.views < 500:
                    suggestions.append(ImprovementSuggestion(
                        category="distribution",
                        severity="high",
                        suggestion="Low reach (<500 views). Optimize hashtag mix (broad+niche+specific). Post at peak hours (7-10pm local). Check if video quality/lighting is poor.",
                        metric=f"views={m.views}",
                    ))

        if not suggestions:
            suggestions = self._baseline_suggestions()

        return suggestions

    def generate_report(
        self,
        post_id: str = "",
    ) -> AnalyticsReport:
        """Generate a full analytics report for a post or all posts."""
        from core.post_queue import PostQueue

        queue = PostQueue()
        posts = queue.load()

        if post_id:
            post = queue.get(post_id)
            if not post:
                return self._empty_report(post_id)
            metrics = self.track_performance(post_id, post.platforms[0] if post.platforms else "tiktok")
            suggestions = self.suggest_improvements(metrics)
            return AnalyticsReport(
                post_id=post_id,
                niche=post.niche,
                product=post.product,
                metrics=metrics,
                suggestions=suggestions,
                summary=self._build_summary(metrics, suggestions),
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        all_suggestions: list[ImprovementSuggestion] = []
        all_metrics: list[PostMetrics] = []
        for p in posts:
            if p.status in ("posted", "approved"):
                for platform in p.platforms:
                    m = self.track_performance(p.id, platform)
                    all_metrics.append(m)
                if p.status == "posted":
                    suggestions = self.suggest_improvements(all_metrics)
                    all_suggestions.extend(suggestions)

        report = AnalyticsReport(
            post_id="all",
            suggestions=all_suggestions[:10],
            summary=self._build_summary(
                all_metrics[0] if all_metrics else None,
                all_suggestions[:5],
            ),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        if all_metrics:
            report.metrics = all_metrics[0]

        return report

    def _fetch_tiktok_metrics(
        self, post_id: str, token: str, now: str
    ) -> PostMetrics:
        """Fetch real metrics from TikTok API."""
        try:
            import requests
            resp = requests.get(
                f"https://open-api.tiktok.com/video/query/",
                params={
                    "access_token": token,
                    "video_id": post_id,
                    "fields": "video_id,view_count,like_count,comment_count,share_count",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            views = data.get("view_count", 0)
            likes = data.get("like_count", 0)
            return PostMetrics(
                post_id=post_id,
                platform="tiktok",
                views=views,
                likes=likes,
                comments=data.get("comment_count", 0),
                shares=data.get("share_count", 0),
                engagement_rate=self._calc_rate(likes, views),
                fetched_at=now,
            )
        except Exception as e:
            logger.warning("TikTok metrics fetch failed: %s", e)
            return self._mock_metrics(post_id, "tiktok")

    def _fetch_instagram_metrics(
        self, post_id: str, token: str, now: str
    ) -> PostMetrics:
        """Fetch real metrics from Instagram Graph API."""
        try:
            import requests
            resp = requests.get(
                f"https://graph.facebook.com/v20.0/{post_id}/insights",
                params={
                    "access_token": token,
                    "metric": "impressions,reach,likes,comments,saved",
                },
                timeout=15,
            )
            resp.raise_for_status()
            metric_map = {
                m["name"]: m.get("values", [{}])[0].get("value", 0)
                for m in resp.json().get("data", [])
            }
            views = metric_map.get("impressions", metric_map.get("reach", 0))
            likes = metric_map.get("likes", 0)
            return PostMetrics(
                post_id=post_id,
                platform="instagram",
                views=views,
                likes=likes,
                comments=metric_map.get("comments", 0),
                saves=metric_map.get("saved", 0),
                engagement_rate=self._calc_rate(likes, views),
                fetched_at=now,
            )
        except Exception as e:
            logger.warning("Instagram metrics fetch failed: %s", e)
            return self._mock_metrics(post_id, "instagram")

    def _mock_metrics(self, post_id: str, platform: str) -> PostMetrics:
        return PostMetrics(
            post_id=post_id,
            platform=platform,
            views=1250,
            likes=85,
            comments=12,
            shares=30,
            saves=45,
            engagement_rate=6.8,
            click_through=22,
            fetched_at=datetime.now(timezone.utc).isoformat() + " [simulated]",
        )

    def _baseline_suggestions(self) -> list[ImprovementSuggestion]:
        return [
            ImprovementSuggestion(
                category="hook",
                severity="high",
                suggestion="Hook must stop the scroll in the first 1-3 seconds. Test: question, bold claim, pattern interrupt, or curiosity gap.",
                metric="baseline",
            ),
            ImprovementSuggestion(
                category="hashtags",
                severity="medium",
                suggestion="Use 3-5 broad tags + 5-8 niche tags + 3-5 specific tags. Avoid generic tags with >10M posts unless you have strong engagement.",
                metric="baseline",
            ),
            ImprovementSuggestion(
                category="pacing",
                severity="low",
                suggestion="Keep cuts under 2 seconds. Use text overlays for key points. Match edits to audio beats.",
                metric="baseline",
            ),
        ]

    @staticmethod
    def _calc_engagement(m: PostMetrics) -> float:
        return AnalyticsAgent._calc_rate(
            m.likes + m.comments + m.shares + m.saves,
            m.views,
        )

    @staticmethod
    def _calc_rate(interactions: int, views: int) -> float:
        if views <= 0:
            return 0.0
        return round(interactions / views * 100, 2)

    @staticmethod
    def _build_summary(
        metrics: PostMetrics | None,
        suggestions: list[ImprovementSuggestion],
    ) -> str:
        parts: list[str] = []
        if metrics:
            parts.append(
                f"{metrics.platform.upper()}: {metrics.views} views, "
                f"{metrics.likes} likes, {metrics.comments} comments "
                f"(ER: {metrics.engagement_rate:.1f}%)"
            )
        high = [s for s in suggestions if s.severity == "high"]
        if high:
            parts.append(f"Top priority: {high[0].suggestion[:100]}")
        return "\n".join(parts)

    def _empty_report(self, post_id: str) -> AnalyticsReport:
        return AnalyticsReport(
            post_id=post_id,
            summary="No data available — post not found in queue.",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
