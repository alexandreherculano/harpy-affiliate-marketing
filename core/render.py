"""RenderAgent — orchestrates stock fetching, voiceover, captions, and video composition.

Pulls together StockFetcher, VoiceoverEngine, CaptionEngine, and VideoFactory
into a single pipeline that takes a script and outputs a finished MP4.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import Config, load_config
from core.logger import get_logger
from modules.caption_engine import CaptionEngine
from modules.stock_fetcher import StockFetcher
from modules.video_factory import VideoFactory, VideoOutput
from modules.voiceover import VoiceoverEngine

logger = get_logger()


@dataclass
class RenderResult:
    video: VideoOutput | None = None
    voiceover_path: Path | None = None
    caption_path: Path | None = None
    clips_paths: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    success: bool = False


class RenderAgent:
    """High-level agent that renders a complete video from a script."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config(require_api_key=False)
        self.stock = StockFetcher(self.config)
        self.voiceover = VoiceoverEngine(self.config)
        self.captions = CaptionEngine()
        self.factory = VideoFactory()

    def render_video(
        self,
        script_text: str,
        script_hook: str = "",
        niche: str = "",
        product_name: str = "",
        output_dir: str | None = None,
        search_queries: list[str] | None = None,
        voice_language: str = "pt",
        product_url: str = "",
    ) -> RenderResult:
        """Render a complete video from a script.

        Pipeline:
        1. Search stock clips for the niche/product
        2. Generate voiceover from the script
        3. Generate timed captions
        4. Compose everything into a final MP4
        """
        output = Path(output_dir) if output_dir else Path("outputs")
        output.mkdir(parents=True, exist_ok=True)

        queries = search_queries or self._derive_queries(niche, product_name)
        result = RenderResult()
        errors: list[str] = []

        logger.info("RenderAgent starting — niche=%s product=%s", niche, product_name)

        # 1. Fetch media (priority: product images > generated visuals > Pexels > fallback)
        clip_paths: list[Path] = []
        clips_output = str(output / "clips")

        if product_url:
            search = self.stock.fetch_product_media(
                product_url=product_url,
                product_name=product_name,
                niche=niche,
                output_dir=clips_output,
                count=3,
            )
        elif niche or product_name:
            search = self.stock.fetch_product_media(
                product_name=product_name,
                niche=niche,
                output_dir=clips_output,
                count=3,
            )
        else:
            search = StockSearchResult(query="default", clips=[], provider="fallback")

        if search.clips:
            paths = self.stock.download_all(search, output_dir=clips_output, limit=3)
            clip_paths.extend(paths)

        if not clip_paths:
            queries = search_queries or self._derive_queries(niche, product_name)
            for query in queries:
                try:
                    fallback_search = self.stock.search_videos(query, per_page=2)
                    if fallback_search.clips:
                        paths = self.stock.download_all(fallback_search, output_dir=clips_output, limit=1)
                        clip_paths.extend(paths)
                except Exception as e:
                    msg = f"Media fetch failed for '{query}': {e}"
                    logger.warning(msg)
                    errors.append(msg)

        result.clips_paths = clip_paths

        # 2. Generate voiceover
        voice_text = self._prepare_voice_text(script_text, script_hook)
        try:
            vo = self.voiceover.generate_voiceover(
                text=voice_text,
                language=voice_language,
                output_dir=str(output / "voice"),
            )
            result.voiceover_path = vo.audio_path
        except Exception as e:
            msg = f"Voiceover failed: {e}"
            logger.error(msg)
            errors.append(msg)
            result.errors = errors
            return result

        # 3. Generate captions
        try:
            track = self.captions.generate_captions(
                text=voice_text,
                total_duration=vo.duration,
                words_per_segment=4,
            )
            caption_path = output / "captions" / "captions.srt"
            caption_path.parent.mkdir(parents=True, exist_ok=True)
            self.captions.save_srt(track, caption_path)
            result.caption_path = caption_path

            caption_data = [
                {"text": s.text, "start": s.start, "end": s.end}
                for s in track.segments
            ]
        except Exception as e:
            msg = f"Captions failed: {e}"
            logger.error(msg)
            errors.append(msg)
            caption_data = []

        # 4. Compose final video
        video_path = output / f"harpy_{niche.replace(' ', '_') or 'video'}.mp4"
        try:
            video = self.factory.compose_video(
                script_text=script_text,
                clips=clip_paths,
                audio_path=vo.audio_path,
                captions=caption_data,
                output_path=video_path,
            )
            result.video = video
            result.success = True
        except Exception as e:
            msg = f"Video composition failed: {e}"
            logger.error(msg)
            errors.append(msg)

        result.errors = errors
        if errors:
            result.success = False

        logger.info(
            "RenderAgent complete — success=%s video=%s",
            result.success,
            result.video.video_path if result.video else "N/A",
        )
        return result

    def _derive_queries(self, niche: str, product: str) -> list[str]:
        queries = [niche, product]
        queries.append(f"{niche} product review")
        queries.append(f"{product} demo")
        queries.append("technology background")
        return [q for q in queries if q.strip()]

    def _prepare_voice_text(self, script_text: str, hook: str) -> str:
        """Clean script text for TTS — remove visual directions but preserve accents."""
        import re

        text = re.sub(r'【.*?】', '', script_text)
        text = re.sub(r'\[.*?\]', '', text)
        text = re.sub(r'\bVOZ:\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bVoz:\s*', '', text)
        text = re.sub(r'\bVOICE:\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bVoice:\s*', '', text)

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        clean = " ".join(lines)
        clean = re.sub(r'\s+', ' ', clean).strip()

        if hook and hook not in clean:
            clean = f"{hook}. {clean}"

        return clean
