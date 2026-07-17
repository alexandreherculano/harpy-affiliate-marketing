"""Stock video fetcher — Pexels API integration with local fallback."""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from core.config import Config, load_config
from core.logger import get_logger

logger = get_logger()


@dataclass
class StockClip:
    id: str
    url: str
    width: int
    height: int
    duration: int
    thumbnail: str = ""
    download_path: Path | None = None
    provider: str = "pexels"


@dataclass
class StockSearchResult:
    query: str
    clips: list[StockClip] = field(default_factory=list)
    total_results: int = 0
    provider: str = "pexels"


class StockFetcher:
    """Search and download stock videos from Pexels API."""

    PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
    PEXELS_POPULAR_URL = "https://api.pexels.com/videos/popular"

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config(require_api_key=False)
        self.api_key = getattr(self.config, "pexels_api_key", "") or ""

    def search_videos(
        self,
        query: str,
        per_page: int = 5,
        orientation: str = "portrait",
        size: str = "medium",
    ) -> StockSearchResult:
        """Search Pexels for stock videos matching the query."""
        if not self.api_key:
            logger.warning("No PEXELS_API_KEY — using local fallback")
            return self._fallback_search(query, per_page)

        params = {
            "query": query,
            "per_page": min(per_page, 15),
            "orientation": orientation,
            "size": size,
        }
        headers = {"Authorization": self.api_key}

        try:
            resp = requests.get(
                self.PEXELS_VIDEO_URL,
                params=params,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            clips = []
            for v in data.get("videos", []):
                files = v.get("video_files", [])
                best = self._pick_best_file(files)
                if best:
                    clips.append(StockClip(
                        id=str(v["id"]),
                        url=best["link"],
                        width=best.get("width", 1080),
                        height=best.get("height", 1920),
                        duration=v.get("duration", 10),
                        thumbnail=v.get("image", ""),
                        provider="pexels",
                    ))

            logger.info(
                "Pexels search '%s': %d clips found",
                query,
                len(clips),
            )
            return StockSearchResult(
                query=query,
                clips=clips,
                total_results=data.get("total_results", 0),
                provider="pexels",
            )
        except Exception as e:
            logger.error("Pexels API error: %s — using fallback", e)
            return self._fallback_search(query, per_page)

    def download_clip(self, clip: StockClip, output_dir: str | None = None) -> Path:
        """Download a stock video clip to disk."""
        if output_dir:
            dest = Path(output_dir)
        else:
            dest = Path(tempfile.gettempdir()) / "harpy_stock"
        dest.mkdir(parents=True, exist_ok=True)

        filename = f"{clip.provider}_{clip.id}.mp4"
        filepath = dest / filename

        if filepath.exists():
            logger.debug("Clip already downloaded: %s", filepath)
            clip.download_path = filepath
            return filepath

        try:
            resp = requests.get(clip.url, timeout=60, stream=True)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            clip.download_path = filepath
            logger.info("Downloaded clip: %s -> %s", clip.id, filepath)
            return filepath
        except Exception as e:
            logger.error("Failed to download clip %s: %s", clip.id, e)
            raise

    def download_all(
        self,
        result: StockSearchResult,
        output_dir: str | None = None,
        limit: int = 3,
    ) -> list[Path]:
        """Download up to `limit` clips from search results."""
        paths: list[Path] = []
        for clip in result.clips[:limit]:
            if clip.provider == "fallback":
                logger.debug("Skipping fallback clip: %s", clip.id)
                continue
            if not clip.url:
                logger.debug("Skipping clip with no URL: %s", clip.id)
                continue
            try:
                path = self.download_clip(clip, output_dir)
                paths.append(path)
                time.sleep(0.5)
            except Exception as e:
                logger.warning("Skipping clip %s: %s", clip.id, e)
        return paths

    def _pick_best_file(self, files: list[dict]) -> dict | None:
        """Pick the best quality portrait video file."""
        for f in files:
            if f.get("width") == 1080 and f.get("height") == 1920:
                return f
        portrait = [f for f in files if f.get("width", 0) < f.get("height", 0)]
        if portrait:
            return max(portrait, key=lambda f: f.get("width", 0))
        return files[0] if files else None

    def _fallback_search(
        self, query: str, count: int
    ) -> StockSearchResult:
        """Return placeholder clips when no API key is available."""
        clips = []
        for i in range(min(count, 5)):
            clips.append(StockClip(
                id=f"local_{i}",
                url="",
                width=1080,
                height=1920,
                duration=5,
                provider="fallback",
            ))
        return StockSearchResult(
            query=query,
            clips=clips,
            total_results=len(clips),
            provider="fallback",
        )
