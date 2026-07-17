"""Stock video fetcher — priority chain: product images > generated visuals > Pexels > fallback.

For affiliate content, product images and niche-themed visuals convert better
than generic stock footage. Pexels is only used as a last resort.
"""

from __future__ import annotations

import hashlib
import io
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

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
    provider: str = "generated"


@dataclass
class StockSearchResult:
    query: str
    clips: list[StockClip] = field(default_factory=list)
    total_results: int = 0
    provider: str = "generated"


class StockFetcher:
    """Media fetcher with priority chain:

    1. Product images from URL (scraping og:image, product photos)
    2. Generated niche visuals (colored cards with product name)
    3. Pexels API stock footage (only if API key configured)
    4. Solid color blocks (absolute fallback)
    """

    PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
    TARGET_W = 1080
    TARGET_H = 1920

    NICHE_PALETTES = {
        "gamer": [(25, 25, 45), (45, 25, 55), (20, 35, 50)],
        "tech": [(15, 25, 40), (25, 35, 55), (20, 25, 45)],
        "fitness": [(30, 20, 15), (20, 35, 25), (35, 25, 20)],
        "beauty": [(40, 25, 35), (35, 30, 45), (45, 30, 35)],
        "home": [(35, 30, 25), (25, 35, 30), (30, 35, 25)],
        "food": [(40, 30, 20), (35, 25, 15), (30, 35, 25)],
        "finance": [(20, 35, 25), (15, 30, 40), (25, 35, 20)],
        "default": [(20, 25, 45), (30, 20, 40), (25, 30, 45)],
    }

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
        """Search for video clips using the priority chain."""
        result = self._search_generated(query, per_page)
        if result.clips:
            return result
        if self.api_key:
            return self._search_pexels(query, per_page, orientation, size)
        return self._fallback_search(query, per_page)

    def fetch_product_media(
        self,
        product_url: str = "",
        product_name: str = "",
        niche: str = "",
        output_dir: str | None = None,
        count: int = 3,
    ) -> StockSearchResult:
        """Try to fetch real product media (images) from the product website.

        Attempts to find og:image or first large image from the product page.
        Falls back to generated visuals if nothing is found.
        """
        clips: list[StockClip] = []

        if product_url:
            logger.info("Fetching product media from: %s", product_url)
            try:
                images = self._scrape_product_images(product_url, count)
                if images:
                    dest = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "harpy_product"
                    dest.mkdir(parents=True, exist_ok=True)
                    for i, img_data in enumerate(images):
                        clip = self._image_to_clip(img_data, dest, f"product_{i}", product_name)
                        if clip:
                            clips.append(clip)
            except Exception as e:
                logger.warning("Product media fetch failed: %s", e)

        if not clips:
            logger.info("No product images found — generating niche visuals")
            clips = self._generate_niche_visuals(
                niche=niche,
                product_name=product_name,
                output_dir=output_dir,
                count=count,
            )

        return StockSearchResult(
            query=product_name or niche,
            clips=clips,
            total_results=len(clips),
            provider="product" if product_url else "generated",
        )

    def _scrape_product_images(self, url: str, count: int) -> list[bytes]:
        """Scrape product images from a webpage using og:image and img tags."""
        try:
            from urllib.parse import urljoin, urlparse

            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36"
            })
            resp.raise_for_status()
            html = resp.text

            image_urls: list[str] = []

            import re
            og_match = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
            if og_match:
                image_urls.append(urljoin(url, og_match.group(1)))

            img_matches = re.findall(r'<img[^>]+src="([^"]+\.(?:jpg|jpeg|png|webp))"', html, re.IGNORECASE)
            for img in img_matches:
                if len(image_urls) >= count:
                    break
                full = urljoin(url, img)
                if full not in image_urls:
                    image_urls.append(full)

            results: list[bytes] = []
            for img_url in image_urls[:count]:
                try:
                    img_resp = requests.get(img_url, timeout=10, headers={
                        "User-Agent": "Mozilla/5.0"
                    })
                    img_resp.raise_for_status()
                    results.append(img_resp.content)
                    logger.info("Scraped product image: %s (%d bytes)", img_url, len(img_resp.content))
                except Exception as e:
                    logger.debug("Failed to download image %s: %s", img_url, e)

            return results
        except Exception as e:
            logger.warning("Product scrape failed: %s", e)
            return []

    def _image_to_clip(
        self, img_data: bytes, output_dir: Path, prefix: str, product_name: str
    ) -> StockClip | None:
        """Convert a product image to a 9:16 video-ready clip (pillarboxed on colored bg)."""
        try:
            img = Image.open(io.BytesIO(img_data))
            img = img.convert("RGB")

            w, h = img.size
            target_ratio = self.TARGET_W / self.TARGET_H
            img_ratio = w / h

            bg = Image.new("RGB", (self.TARGET_W, self.TARGET_H), (18, 18, 35))

            if img_ratio > target_ratio:
                new_w = self.TARGET_W
                new_h = int(new_w / img_ratio)
            else:
                new_h = int(self.TARGET_H * 0.7)
                new_w = int(new_h * img_ratio)

            img_resized = img.resize((new_w, new_h), Image.LANCZOS)
            x = (self.TARGET_W - new_w) // 2
            y = (self.TARGET_H - new_h) // 2 - 60
            bg.paste(img_resized, (x, y))

            draw = ImageDraw.Draw(bg)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            except Exception:
                font = ImageFont.load_default()

            name = product_name[:50]
            bbox = draw.textbbox((0, 0), name, font=font)
            tw = bbox[2] - bbox[0]
            draw.text(
                ((self.TARGET_W - tw) // 2, self.TARGET_H - 120),
                name, font=font, fill=(200, 200, 220),
            )

            clip_path = output_dir / f"{prefix}_{hashlib.md5(img_data).hexdigest()[:8]}.png"
            bg.save(clip_path, "PNG")
            logger.info("Product image clip created: %s", clip_path)

            return StockClip(
                id=prefix,
                url="",
                width=self.TARGET_W,
                height=self.TARGET_H,
                duration=5,
                download_path=clip_path,
                provider="product",
            )
        except Exception as e:
            logger.warning("Failed to process product image: %s", e)
            return None

    def _generate_niche_visuals(
        self,
        niche: str,
        product_name: str,
        output_dir: str | None = None,
        count: int = 3,
    ) -> list[StockClip]:
        """Generate niche-themed visual cards as clip backgrounds."""
        dest = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "harpy_visuals"
        dest.mkdir(parents=True, exist_ok=True)

        niche_key = niche.lower().split()[0] if niche else "default"
        palette = self.NICHE_PALETTES.get(niche_key, self.NICHE_PALETTES["default"])
        clips: list[StockClip] = []

        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        except Exception:
            font_large = ImageFont.load_default()
            font_small = font_large

        for i in range(count):
            color = palette[i % len(palette)]
            img = Image.new("RGB", (self.TARGET_W, self.TARGET_H), color)
            draw = ImageDraw.Draw(img)

            for j in range(3):
                accent = tuple(min(c + 15, 255) for c in color)
                y_offset = 150 + j * 500
                draw.rectangle(
                    [(80, y_offset), (self.TARGET_W - 80, y_offset + 300)],
                    fill=accent, outline=accent,
                )

            name = product_name[:40]
            bbox = draw.textbbox((0, 0), name, font=font_large)
            tw = bbox[2] - bbox[0]
            draw.text(
                ((self.TARGET_W - tw) // 2, 600),
                name, font=font_large, fill=(255, 255, 255),
            )

            subtitle = f"Review completa • Link na bio"
            bbox2 = draw.textbbox((0, 0), subtitle, font=font_small)
            tw2 = bbox2[2] - bbox2[0]
            draw.text(
                ((self.TARGET_W - tw2) // 2, 680),
                subtitle, font=font_small, fill=(200, 200, 220),
            )

            clip_path = dest / f"niche_{niche_key}_{i}.png"
            img.save(clip_path, "PNG")

            clips.append(StockClip(
                id=f"niche_{niche_key}_{i}",
                url="",
                width=self.TARGET_W,
                height=self.TARGET_H,
                duration=4,
                download_path=clip_path,
                provider="generated",
            ))

        logger.info("Generated %d niche visuals for '%s'", len(clips), niche)
        return clips

    def _search_generated(self, query: str, count: int) -> StockSearchResult:
        """Create generated clips directly from a search query."""
        clips = self._generate_niche_visuals(
            niche=query,
            product_name=query,
            count=min(count, 3),
        )
        return StockSearchResult(
            query=query,
            clips=clips,
            total_results=len(clips),
            provider="generated",
        )

    def _search_pexels(
        self, query: str, per_page: int, orientation: str, size: str,
    ) -> StockSearchResult:
        """Search Pexels — only called as last resort when API key exists."""
        params = {
            "query": query,
            "per_page": min(per_page, 15),
            "orientation": orientation,
            "size": size,
        }
        headers = {"Authorization": self.api_key}

        try:
            resp = requests.get(self.PEXELS_VIDEO_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            clips: list[StockClip] = []
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
            logger.info("Pexels search '%s': %d clips", query, len(clips))
            return StockSearchResult(query=query, clips=clips, total_results=data.get("total_results", 0), provider="pexels")
        except Exception as e:
            logger.warning("Pexels failed: %s", e)
            return self._fallback_search(query, per_page)

    def download_clip(self, clip: StockClip, output_dir: str | None = None) -> Path:
        """Download a clip. For generated/product clips the file is already on disk."""
        if clip.download_path and clip.download_path.exists():
            return clip.download_path

        dest = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "harpy_stock"
        dest.mkdir(parents=True, exist_ok=True)
        filepath = dest / f"{clip.provider}_{clip.id}.mp4"

        if not clip.url:
            return self._save_placeholder(clip, filepath)

        try:
            resp = requests.get(clip.url, timeout=60, stream=True)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            clip.download_path = filepath
            logger.info("Downloaded: %s -> %s", clip.id, filepath)
            return filepath
        except Exception as e:
            logger.error("Download failed %s: %s", clip.id, e)
            raise

    def download_all(
        self,
        result: StockSearchResult,
        output_dir: str | None = None,
        limit: int = 3,
    ) -> list[Path]:
        """Download or collect paths for all clips."""
        paths: list[Path] = []
        for clip in result.clips[:limit]:
            if clip.provider == "fallback" and not clip.download_path:
                continue
            try:
                if clip.download_path and clip.download_path.exists():
                    paths.append(clip.download_path)
                elif clip.url:
                    path = self.download_clip(clip, output_dir)
                    paths.append(path)
                    time.sleep(0.3)
            except Exception as e:
                logger.warning("Skipping %s: %s", clip.id, e)
        return paths

    def _save_placeholder(self, clip: StockClip, filepath: Path) -> Path:
        img = Image.new("RGB", (clip.width, clip.height), (20, 20, 40))
        filepath = filepath.with_suffix(".png")
        img.save(filepath, "PNG")
        clip.download_path = filepath
        return filepath

    def _pick_best_file(self, files: list[dict]) -> dict | None:
        for f in files:
            if f.get("width") == 1080 and f.get("height") == 1920:
                return f
        portrait = [f for f in files if f.get("width", 0) < f.get("height", 0)]
        if portrait:
            return max(portrait, key=lambda f: f.get("width", 0))
        return files[0] if files else None

    def _fallback_search(self, query: str, count: int) -> StockSearchResult:
        clips = []
        for i in range(min(count, 5)):
            clips.append(StockClip(
                id=f"fallback_{i}",
                url="",
                width=1080,
                height=1920,
                duration=5,
                provider="fallback",
            ))
        return StockSearchResult(query=query, clips=clips, total_results=len(clips), provider="fallback")
