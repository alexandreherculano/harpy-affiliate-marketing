"""Video factory — compose stock clips, voiceover, and captions into final MP4."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.logger import get_logger

logger = get_logger()

try:
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeVideoClip,
        ImageClip,
        TextClip,
        VideoClip,
        VideoFileClip,
        concatenate_videoclips,
    )
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False


@dataclass
class VideoOutput:
    video_path: Path
    duration: float
    resolution: tuple[int, int]
    file_size_mb: float = 0.0
    components: dict[str, Any] = field(default_factory=dict)


class VideoFactory:
    """Compose final video from clips, audio, and captions using MoviePy."""

    TARGET_RESOLUTION = (1080, 1920)
    FPS = 30

    def __init__(self) -> None:
        if not MOVIEPY_AVAILABLE:
            logger.warning(
                "MoviePy not available. Install with: pip install moviepy"
            )

    def compose_video(
        self,
        script_text: str,
        clips: list[Path],
        audio_path: Path,
        captions: list[dict] | None = None,
        output_path: str | Path | None = None,
        add_watermark: bool = True,
    ) -> VideoOutput:
        """Compose the final video using MoviePy.

        Args:
            script_text: The full script for overlay/title
            clips: List of video/image file paths
            audio_path: Path to voiceover MP3
            captions: Optional list of {text, start, end} dicts
            output_path: Output MP4 path (defaults to temp)
            add_watermark: Add "Made with Harpy" watermark
        """
        if not MOVIEPY_AVAILABLE:
            return self._mock_compose(script_text, clips, audio_path, captions, output_path)

        output = Path(output_path) if output_path else Path(tempfile.gettempdir()) / "harpy_video" / "output.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)

        video_clips = self._load_clips(clips)

        if not video_clips:
            video_clips = [self._create_placeholder_clip(audio_path)]

        audio = AudioFileClip(str(audio_path))
        total_duration = audio.duration

        video = self._assemble_video(video_clips, total_duration)
        video = video.with_audio(audio)

        if captions:
            video = self._add_captions(video, captions)

        if add_watermark:
            video = self._add_watermark(video)

        video.write_videofile(
            str(output),
            fps=self.FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2,
        )

        file_size = output.stat().st_size / (1024 * 1024) if output.exists() else 0

        for clip in video_clips:
            try:
                clip.close()
            except Exception:
                pass
        audio.close()
        video.close()

        logger.info("Video rendered: %s (%.1fs, %.1fMB)", output, total_duration, file_size)
        return VideoOutput(
            video_path=output,
            duration=total_duration,
            resolution=self.TARGET_RESOLUTION,
            file_size_mb=round(file_size, 2),
            components={
                "clips_count": len(video_clips),
                "captions_count": len(captions) if captions else 0,
                "audio_provider": "from_file",
            },
        )

    def _load_clips(self, paths: list[Path]) -> list[VideoClip]:
        clips: list[VideoClip] = []
        for p in paths:
            if not p.exists():
                logger.warning("Clip not found: %s", p)
                continue
            try:
                clip = VideoFileClip(str(p))
                clip = clip.resized(width=self.TARGET_RESOLUTION[0], height=self.TARGET_RESOLUTION[1])
                clips.append(clip)
            except Exception as e:
                logger.warning("Failed to load clip %s: %s", p, e)
        return clips

    def _assemble_video(
        self, clips: list[VideoClip], total_duration: float
    ) -> VideoClip:
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

    def _add_captions(
        self, video: VideoClip, captions: list[dict]
    ) -> VideoClip:
        text_clips = []
        for cap in captions:
            txt = cap.get("text", "")
            start = cap.get("start", 0)
            end = cap.get("end", 0)
            duration = end - start

            if duration <= 0 or not txt:
                continue

            tc = TextClip(
                text=txt,
                font_size=48,
                color="white",
                stroke_color="black",
                stroke_width=2,
                font="Arial",
                size=(self.TARGET_RESOLUTION[0] - 100, None),
                method="caption",
            )
            tc = tc.with_position(("center", self.TARGET_RESOLUTION[1] * 0.65))
            tc = tc.with_start(start)
            tc = tc.with_duration(duration)
            text_clips.append(tc)

        if text_clips:
            return CompositeVideoClip([video] + text_clips)
        return video

    def _add_watermark(self, video: VideoClip) -> VideoClip:
        try:
            wm = TextClip(
                text="Made with Harpy",
                font_size=20,
                color="white",
                font="Arial",
            )
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
            clip = ColorClip(
                size=self.TARGET_RESOLUTION,
                color=(20, 20, 40),
                duration=audio.duration,
            )
            audio.close()
            return clip
        except Exception:
            return ColorClip(
                size=self.TARGET_RESOLUTION,
                color=(20, 20, 40),
                duration=5,
            )

    def _mock_compose(
        self,
        script_text: str,
        clips: list[Path],
        audio_path: Path,
        captions: list[dict] | None,
        output_path: str | Path | None,
    ) -> VideoOutput:
        """Return mock output when MoviePy is not available."""
        output = Path(output_path) if output_path else Path("outputs/mock_output.mp4")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.touch()

        logger.info("Video mock composed: %s (MoviePy not installed)", output)
        return VideoOutput(
            video_path=output,
            duration=15.0,
            resolution=self.TARGET_RESOLUTION,
            file_size_mb=0.0,
            components={
                "clips_count": len(clips),
                "captions_count": len(captions) if captions else 0,
                "note": "MoviePy not available — empty placeholder file",
            },
        )
