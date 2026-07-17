"""Video factory — compose stock clips, voiceover, and captions into final MP4.

Supports MoviePy (full features) and imageio (lightweight, auto-downloads ffmpeg).
"""

from __future__ import annotations

import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.logger import get_logger

logger = get_logger()

MOVIEPY_AVAILABLE = False
IMAGEIO_AVAILABLE = False

try:
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeVideoClip,
        TextClip,
        VideoClip,
        VideoFileClip,
        concatenate_videoclips,
    )
    MOVIEPY_AVAILABLE = True
    logger.info("MoviePy loaded")
except ImportError:
    pass

try:
    import imageio
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    IMAGEIO_AVAILABLE = True
    logger.info("imageio+ffmpeg loaded")
except ImportError:
    pass


@dataclass
class VideoOutput:
    video_path: Path
    duration: float
    resolution: tuple[int, int]
    file_size_mb: float = 0.0
    components: dict[str, Any] = field(default_factory=dict)


class VideoFactory:
    """Compose final video using MoviePy (preferred) or imageio (fallback)."""

    TARGET_RESOLUTION = (1080, 1920)
    FPS = 30

    def __init__(self) -> None:
        self._engine = self._detect_engine()

    def _detect_engine(self) -> str:
        if MOVIEPY_AVAILABLE:
            return "moviepy"
        if IMAGEIO_AVAILABLE:
            return "imageio"
        return "none"

    def compose_video(
        self,
        script_text: str,
        clips: list[Path],
        audio_path: Path,
        captions: list[dict] | None = None,
        output_path: str | Path | None = None,
        add_watermark: bool = True,
        language: str = "pt",
    ) -> VideoOutput:
        output = Path(output_path) if output_path else Path(tempfile.gettempdir()) / "harpy_video" / "output.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)

        if self._engine == "moviepy":
            return self._compose_moviepy(script_text, clips, audio_path, captions, output, add_watermark)
        if self._engine == "imageio":
            return self._compose_imageio(script_text, clips, audio_path, captions, output, add_watermark, language)

        return self._compose_placeholder(output)

    def _compose_imageio(
        self,
        script_text: str,
        clips: list[Path],
        audio_path: Path,
        captions: list[dict] | None,
        output: Path,
        add_watermark: bool,
        language: str = "pt",
    ) -> VideoOutput:
        """Create video using imageio + numpy + Pillow — no external ffmpeg needed."""
        import imageio
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont

        render_fps = 15
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
        except Exception:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 44)
            except Exception:
                font = ImageFont.load_default()

        total_duration = 40.0
        frame_count = int(total_duration * render_fps)
        w, h = self.TARGET_RESOLUTION

        if captions:
            cap_map = self._build_caption_map(captions, total_duration)
        else:
            lines = [l.strip() for l in script_text.split("\n") if l.strip()]
            cap_map = self._build_caption_map(
                [{"text": " ".join(lines), "start": 0.5, "end": total_duration - 0.5}],
                total_duration,
            )

        writer = imageio.get_writer(
            str(output),
            fps=render_fps,
            codec="libx264",
            quality=8,
            pixelformat="yuv420p",
            macro_block_size=8,
        )

        try:
            last_caption: list[str] = []
            for frame_idx in range(frame_count):
                t = frame_idx / render_fps
                frame = np.zeros((h, w, 3), dtype=np.uint8)
                frame[:, :] = (18, 18, 38)

                img = Image.fromarray(frame)
                draw = ImageDraw.Draw(img)

                captions_to_draw: list[str] = []
                for time_key in sorted(cap_map.keys(), reverse=True):
                    if time_key <= t:
                        captions_to_draw = cap_map[time_key]
                        break

                if not captions_to_draw:
                    captions_to_draw = last_caption
                else:
                    last_caption = captions_to_draw

                if captions_to_draw:
                    y_center = h * 0.60
                    line_height = 56
                    texts = captions_to_draw[:5]
                    total_text_height = len(texts) * line_height
                    start_y = int(y_center - total_text_height / 2)

                    for i, txt in enumerate(texts):
                        wrapped = textwrap.wrap(txt, width=28)
                        for j, line in enumerate(wrapped):
                            text_y = start_y + i * line_height + j * 44
                            bbox = draw.textbbox((0, 0), line, font=font)
                            tw = bbox[2] - bbox[0]
                            tx = (w - tw) // 2

                            for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
                                draw.text((tx + ox, text_y + oy), line, font=font, fill=(0, 0, 0))
                            draw.text((tx, text_y), line, font=font, fill=(255, 255, 255))

                if add_watermark:
                    try:
                        small_font = ImageFont.truetype(
                            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18
                        )
                    except Exception:
                        small_font = font
                    wm_text = "Feito com Harpy" if language.startswith("pt") else "Made with Harpy"
                    draw.text((w - 180, h - 50), wm_text, font=small_font, fill=(200, 200, 200, 128))

                writer.append_data(np.array(img))

        finally:
            writer.close()

        if audio_path and audio_path.exists() and output.exists():
            output = self._mux_audio(output, audio_path)

        file_size = output.stat().st_size / (1024 * 1024) if output.exists() else 0

        logger.info("Video rendered (imageio): %s (%.1fs, %.1fMB)", output, total_duration, file_size)
        return VideoOutput(
            video_path=output,
            duration=total_duration,
            resolution=self.TARGET_RESOLUTION,
            file_size_mb=round(file_size, 2),
            components={
                "clips_count": len(clips),
                "captions_count": len(captions) if captions else 0,
                "engine": "imageio",
            },
        )

    def _build_caption_map(
        self, captions: list[dict], total_duration: float
    ) -> dict[float, list[str]]:
        """Build a frame-indexed map of captions by time."""
        cmap: dict[float, list[str]] = {}
        for cap in captions:
            start = cap.get("start", 0)
            text = cap.get("text", "")
            if text:
                cmap.setdefault(start, []).append(text)
        return cmap

    def _mux_audio(self, video_path: Path, audio_path: Path) -> Path:
        """Merge audio into video using ffmpeg."""
        import subprocess
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            ffmpeg = get_ffmpeg_exe()
        except ImportError:
            logger.warning("imageio_ffmpeg not available, skipping audio mux")
            return video_path

        temp = video_path.with_suffix(".tmp.mp4")
        cmd = [
            ffmpeg, "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(temp),
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True, timeout=30)
            temp.replace(video_path)
            logger.info("Audio muxed into video: %s", video_path)
        except Exception as e:
            logger.warning("Failed to mux audio: %s", e)
        return video_path

    def _compose_moviepy(
        self,
        script_text: str,
        clips: list[Path],
        audio_path: Path,
        captions: list[dict] | None,
        output: Path,
        add_watermark: bool,
    ) -> VideoOutput:
        video_clips = self._load_moviepy_clips(clips)
        if not video_clips:
            video_clips = [self._create_placeholder_clip(audio_path)]

        audio = AudioFileClip(str(audio_path))
        total_duration = audio.duration

        video = self._assemble_moviepy_video(video_clips, total_duration)
        video = video.with_audio(audio)

        if captions:
            video = self._add_moviepy_captions(video, captions)

        if add_watermark:
            video = self._add_moviepy_watermark(video)

        video.write_videofile(str(output), fps=self.FPS, codec="libx264", audio_codec="aac",
                             preset="medium", threads=2)

        file_size = output.stat().st_size / (1024 * 1024) if output.exists() else 0

        for clip in video_clips:
            try:
                clip.close()
            except Exception:
                pass
        audio.close()
        video.close()

        logger.info("Video rendered (moviepy): %s (%.1fs, %.1fMB)", output, total_duration, file_size)
        return VideoOutput(
            video_path=output,
            duration=total_duration,
            resolution=self.TARGET_RESOLUTION,
            file_size_mb=round(file_size, 2),
            components={
                "clips_count": len(video_clips),
                "captions_count": len(captions) if captions else 0,
                "engine": "moviepy",
            },
        )

    def _compose_placeholder(self, output: Path) -> VideoOutput:
        output.touch()
        logger.warning("No video engine available — created empty placeholder: %s", output)
        return VideoOutput(
            video_path=output,
            duration=15.0,
            resolution=self.TARGET_RESOLUTION,
            file_size_mb=0.0,
            components={"engine": "none", "note": "Install moviepy or imageio"},
        )

    # MoviePy-specific helpers

    def _load_moviepy_clips(self, paths: list[Path]) -> list[VideoClip]:
        clips: list[VideoClip] = []
        for p in paths:
            if not p.exists():
                continue
            try:
                clip = VideoFileClip(str(p))
                clip = clip.resized(width=self.TARGET_RESOLUTION[0], height=self.TARGET_RESOLUTION[1])
                clips.append(clip)
            except Exception as e:
                logger.warning("Failed to load clip %s: %s", p, e)
        return clips

    def _assemble_moviepy_video(self, clips: list[VideoClip], total_duration: float) -> VideoClip:
        if len(clips) == 1:
            clip = clips[0]
            if clip.duration < total_duration:
                clip = clip.loop(duration=total_duration)
            else:
                clip = clip.subclipped(0, total_duration)
            return clip
        per_clip = total_duration / len(clips)
        segments = []
        for clip in clips:
            if clip.duration > per_clip:
                segmented = clip.subclipped(0, per_clip)
            else:
                segmented = clip.loop(duration=per_clip)
            segments.append(segmented)
        return concatenate_videoclips(segments)

    def _add_moviepy_captions(self, video: VideoClip, captions: list[dict]) -> VideoClip:
        text_clips = []
        for cap in captions:
            txt = cap.get("text", "")
            start = cap.get("start", 0)
            end = cap.get("end", 0)
            duration = end - start
            if duration <= 0 or not txt:
                continue
            tc = TextClip(text=txt, font_size=48, color="white",
                          stroke_color="black", stroke_width=2, font="Arial",
                          size=(self.TARGET_RESOLUTION[0] - 100, None), method="caption")
            tc = tc.with_position(("center", self.TARGET_RESOLUTION[1] * 0.65))
            tc = tc.with_start(start)
            tc = tc.with_duration(duration)
            text_clips.append(tc)
        if text_clips:
            return CompositeVideoClip([video] + text_clips)
        return video

    def _add_moviepy_watermark(self, video: VideoClip) -> VideoClip:
        try:
            wm = TextClip(text="Made with Harpy", font_size=20, color="white", font="Arial")
            wm = wm.with_opacity(0.5)
            wm = wm.with_position(("right", "bottom"))
            wm = wm.margin(right=20, bottom=20, opacity=0)
            wm = wm.with_duration(video.duration)
            return CompositeVideoClip([video, wm])
        except Exception:
            return video

    def _create_placeholder_clip(self, audio_path: Path) -> VideoClip:
        try:
            audio = AudioFileClip(str(audio_path))
            clip = ColorClip(size=self.TARGET_RESOLUTION, color=(20, 20, 40), duration=audio.duration)
            audio.close()
            return clip
        except Exception:
            return ColorClip(size=self.TARGET_RESOLUTION, color=(20, 20, 40), duration=5)
