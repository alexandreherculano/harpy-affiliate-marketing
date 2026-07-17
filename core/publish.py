"""PublishAgent — publish content to TikTok and Instagram with fallback to manual posting.

Handles platform API posting with rate-limit retry and generates
.txt fallback files with complete posting instructions for manual copy-paste.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import Config, load_config
from core.logger import get_logger

logger = get_logger()


@dataclass
class PublishResult:
    platform: str
    success: bool
    post_id: str = ""
    video_path: str = ""
    caption: str = ""
    fallback_path: str = ""
    message: str = ""
    posted_at: str = ""


@dataclass
class FallbackFile:
    path: Path
    content: str


class PublishAgent:
    """Publishes content to social platforms with automatic fallback generation."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config(require_api_key=False)

    def publish_to_tiktok(
        self,
        video_path: str | Path,
        caption: str = "",
        hashtags: list[str] | None = None,
        dry_run: bool = False,
    ) -> PublishResult:
        """Publish a video to TikTok.

        If API is not configured, generates a fallback .txt with instructions.
        """
        video = Path(video_path)
        if not video.exists():
            return PublishResult(
                platform="tiktok",
                success=False,
                video_path=str(video_path),
                caption=caption,
                message=f"Video file not found: {video_path}",
            )

        full_caption = self._build_full_caption(caption, hashtags)

        if dry_run:
            fallback = self._generate_fallback(
                platform="tiktok",
                video_path=video,
                caption=full_caption,
                hashtags=hashtags or [],
            )
            return PublishResult(
                platform="tiktok",
                success=True,
                video_path=str(video),
                caption=full_caption,
                fallback_path=str(fallback.path),
                message=f"Dry run — fallback saved to {fallback.path}",
            )

        tiktok_token = getattr(self.config, "tiktok_access_token", None) or ""
        if not tiktok_token:
            fallback = self._generate_fallback(
                platform="tiktok",
                video_path=video,
                caption=full_caption,
                hashtags=hashtags or [],
            )
            logger.info("TikTok API not configured — fallback saved: %s", fallback.path)
            return PublishResult(
                platform="tiktok",
                success=False,
                video_path=str(video),
                caption=full_caption,
                fallback_path=str(fallback.path),
                message=f"TikTok API not configured. Manual posting instructions: {fallback.path}",
            )

        try:
            with open(video, "rb") as video_file:
                resp = self._api_request(
                    method="POST",
                    url="https://open-api.tiktok.com/video/upload/",
                    headers={"Authorization": f"Bearer {tiktok_token}"},
                    files={"video": video_file},
                    params={"caption": full_caption},
                    timeout=60,
                )
            data = resp.json()
            post_id = data.get("data", {}).get("video_id", "")

            logger.info("Posted to TikTok: %s", post_id)
            return PublishResult(
                platform="tiktok",
                success=True,
                post_id=post_id,
                video_path=str(video),
                caption=full_caption,
                posted_at=datetime.now(timezone.utc).isoformat(),
                message=f"Posted! Video ID: {post_id}",
            )
        except Exception as e:
            logger.error("TikTok publish failed: %s", e)
            fallback = self._generate_fallback(
                platform="tiktok",
                video_path=video,
                caption=full_caption,
                hashtags=hashtags or [],
            )
            return PublishResult(
                platform="tiktok",
                success=False,
                video_path=str(video),
                caption=full_caption,
                fallback_path=str(fallback.path),
                message=f"API error: {e}. Fallback: {fallback.path}",
            )

    def publish_to_instagram(
        self,
        video_path: str | Path,
        caption: str = "",
        hashtags: list[str] | None = None,
        dry_run: bool = False,
        post_type: str = "reel",
    ) -> PublishResult:
        """Publish a video to Instagram (Reel or Feed).

        If API is not configured, generates a fallback .txt with instructions.
        post_type: 'reel' (default) or 'feed'
        """
        video = Path(video_path)
        if not video.exists():
            return PublishResult(
                platform="instagram",
                success=False,
                video_path=str(video_path),
                caption=caption,
                message=f"Video file not found: {video_path}",
            )

        full_caption = self._build_full_caption(caption, hashtags, platform="instagram")

        if dry_run:
            fallback = self._generate_fallback(
                platform="instagram",
                video_path=video,
                caption=full_caption,
                hashtags=hashtags or [],
                post_type=post_type,
            )
            return PublishResult(
                platform="instagram",
                success=True,
                video_path=str(video),
                caption=full_caption,
                fallback_path=str(fallback.path),
                message=f"Dry run — fallback saved to {fallback.path}",
            )

        ig_token = getattr(self.config, "instagram_access_token", None) or ""
        ig_user_id = getattr(self.config, "instagram_user_id", None) or ""

        if not ig_token or not ig_user_id:
            fallback = self._generate_fallback(
                platform="instagram",
                video_path=video,
                caption=full_caption,
                hashtags=hashtags or [],
                post_type=post_type,
            )
            logger.info("Instagram API not configured — fallback saved: %s", fallback.path)
            return PublishResult(
                platform="instagram",
                success=False,
                video_path=str(video),
                caption=full_caption,
                fallback_path=str(fallback.path),
                message=f"Instagram API not configured. Manual posting instructions: {fallback.path}",
            )

        try:
            container_url = f"https://graph.facebook.com/v20.0/{ig_user_id}/media"
            container_resp = self._api_request(
                method="POST",
                url=container_url,
                params={
                    "access_token": ig_token,
                    "media_type": "REELS",
                    "video_url": str(video.absolute()),
                    "caption": full_caption,
                },
                timeout=30,
            )
            container_data = container_resp.json()
            container_id = container_data.get("id", "")

            if container_id:
                publish_url = f"https://graph.facebook.com/v20.0/{ig_user_id}/media_publish"
                pub_resp = self._api_request(
                    method="POST",
                    url=publish_url,
                    params={
                        "access_token": ig_token,
                        "creation_id": container_id,
                    },
                    timeout=30,
                )
                pub_data = pub_resp.json()
                post_id = pub_data.get("id", container_id)

                logger.info("Posted to Instagram: %s", post_id)
                return PublishResult(
                    platform="instagram",
                    success=True,
                    post_id=post_id,
                    video_path=str(video),
                    caption=full_caption,
                    posted_at=datetime.now(timezone.utc).isoformat(),
                    message=f"Posted! Media ID: {post_id}",
                )

            raise RuntimeError("No container ID in response")
        except Exception as e:
            logger.error("Instagram publish failed: %s", e)
            fallback = self._generate_fallback(
                platform="instagram",
                video_path=video,
                caption=full_caption,
                hashtags=hashtags or [],
                post_type=post_type,
            )
            return PublishResult(
                platform="instagram",
                success=False,
                video_path=str(video),
                caption=full_caption,
                fallback_path=str(fallback.path),
                message=f"API error: {e}. Fallback: {fallback.path}",
            )

    def publish_all(
        self,
        video_path: str | Path,
        caption: str = "",
        hashtags: list[str] | None = None,
        platforms: list[str] | None = None,
        dry_run: bool = False,
    ) -> list[PublishResult]:
        """Publish to all specified platforms."""
        if platforms is None:
            platforms = ["tiktok", "instagram"]

        results: list[PublishResult] = []
        for platform in platforms:
            if platform == "tiktok":
                result = self.publish_to_tiktok(video_path, caption, hashtags, dry_run)
            elif platform == "instagram":
                result = self.publish_to_instagram(video_path, caption, hashtags, dry_run)
            else:
                continue
            results.append(result)
        return results

    def _generate_fallback(
        self,
        platform: str,
        video_path: Path,
        caption: str,
        hashtags: list[str],
        post_type: str = "reel",
    ) -> FallbackFile:
        """Generate a .txt file with manual posting instructions."""
        output_dir = video_path.parent / "fallback"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"post_{platform}_{timestamp}.txt"
        filepath = output_dir / filename

        tags_str = " ".join(hashtags) if hashtags else ""

        content = f"""==============================================
  HARPY — MANUAL POSTING INSTRUCTIONS
==============================================
Platform: {platform.upper()}
Post Type: {post_type}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

----------------------------------------------
  VIDEO FILE
----------------------------------------------
{video_path.absolute()}

----------------------------------------------
  CAPTION (copy-paste)
----------------------------------------------
{caption}

----------------------------------------------
  HASHTAGS (copy-paste after caption)
----------------------------------------------
{tags_str}

----------------------------------------------
  STEPS FOR {platform.upper()}
----------------------------------------------"""

        if platform == "tiktok":
            content += """
1. Open TikTok app on your phone
2. Tap "+" to create a new post
3. Select the video file listed above
4. Paste the caption text
5. Paste the hashtags after the caption
6. Set cover image (optional)
7. Toggle "Allow comments", "Duet", "Stitch" as desired
8. Tap "Post"
"""
        elif platform == "instagram":
            if post_type == "reel":
                content += """
1. Open Instagram app on your phone
2. Tap "+" and select "Reel"
3. Select the video file listed above
4. Tap "Next" and edit cover/trim if needed
5. Paste the caption text
6. Paste the hashtags after the caption
7. Tag accounts/products if applicable
8. Toggle "Share to Feed" if desired
9. Tap "Share"
"""
            else:
                content += """
1. Open Instagram app on your phone
2. Tap "+" and select "Post"
3. Select the video file listed above
4. Tap "Next" and apply any filters
5. Paste the caption text
6. Paste the hashtags after the caption
7. Tag accounts and add location if desired
8. Tap "Share"
"""

        content += """
----------------------------------------------
  NOTE
----------------------------------------------
This file was auto-generated by Harpy because
the platform API is not yet configured.
Set credentials in .env to enable auto-posting.
"""

        filepath.write_text(content, encoding="utf-8")
        logger.info("Fallback file generated: %s", filepath)
        return FallbackFile(path=filepath, content=content)

    def publish_all_from_queue(
        self,
        platform: str,
        dry_run: bool = False,
    ) -> list[PublishResult]:
        """Publish all approved posts from the queue for a given platform."""
        from core.post_queue import PostQueue

        queue = PostQueue()
        approved = queue.approved()

        if not approved:
            logger.info("No approved posts to publish for %s", platform)
            return []

        results: list[PublishResult] = []
        for i, post in enumerate(approved):
            logger.info(
                "Publishing post %d/%d: %s → %s",
                i + 1,
                len(approved),
                post.id,
                platform,
            )

            if platform == "tiktok":
                result = self.publish_to_tiktok(
                    video_path=post.video_path,
                    caption=post.caption,
                    hashtags=post.hashtags,
                    dry_run=dry_run,
                )
            else:
                result = self.publish_to_instagram(
                    video_path=post.video_path,
                    caption=post.caption,
                    hashtags=post.hashtags,
                    dry_run=dry_run,
                )

            results.append(result)

            if result.success:
                queue.mark_posted(post.id)
            elif i < len(approved) - 1:
                logger.info("Rate-limit pause (2s)...")
                time.sleep(2)

        return results

    @staticmethod
    def _api_request(
        method: str,
        url: str,
        headers: dict | None = None,
        json_data: dict | None = None,
        params: dict | None = None,
        files: dict | None = None,
        timeout: int = 60,
        max_retries: int = 3,
    ) -> requests.Response:
        """Make an API request with rate-limit retry logic.

        Handles 429 (Too Many Requests) with exponential backoff.
        """
        import requests

        for attempt in range(max_retries):
            try:
                if method.upper() == "POST":
                    resp = requests.post(
                        url, json=json_data, params=params,
                        headers=headers, files=files, timeout=timeout,
                    )
                else:
                    resp = requests.get(
                        url, params=params, headers=headers, timeout=timeout,
                    )

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                    logger.warning(
                        "Rate limited (429) — attempt %d/%d, waiting %ds",
                        attempt + 1, max_retries, retry_after,
                    )
                    time.sleep(retry_after)
                    continue

                if resp.status_code >= 500:
                    logger.warning(
                        "Server error %d — attempt %d/%d",
                        resp.status_code, attempt + 1, max_retries,
                    )
                    time.sleep(2 ** attempt)
                    continue

                resp.raise_for_status()
                return resp

            except requests.Timeout:
                logger.warning(
                    "Timeout — attempt %d/%d", attempt + 1, max_retries,
                )
                time.sleep(2 ** attempt)
            except requests.ConnectionError as e:
                logger.warning(
                    "Connection error — attempt %d/%d: %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(2 ** attempt)

        raise RuntimeError(f"API request failed after {max_retries} retries: {url}")

    @staticmethod
    def _build_full_caption(
        caption: str, hashtags: list[str] | None, platform: str = "tiktok"
    ) -> str:
        parts = [caption] if caption else []
        if hashtags:
            parts.append(" ".join(hashtags))
        return "\n\n".join(parts)
