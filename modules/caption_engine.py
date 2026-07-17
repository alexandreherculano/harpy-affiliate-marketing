"""Caption engine — generate timed captions synchronized with audio."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from core.logger import get_logger

logger = get_logger()


@dataclass
class CaptionSegment:
    text: str
    start: float
    end: float
    index: int = 0


@dataclass
class CaptionTrack:
    segments: list[CaptionSegment] = field(default_factory=list)
    total_duration: float = 0.0
    word_count: int = 0
    style: str = "default"


class CaptionEngine:
    """Generate timed, word-synced captions for short-form video."""

    def __init__(self) -> None:
        self._default_wpm = 150  # words per minute

    def generate_captions(
        self,
        text: str,
        total_duration: float | None = None,
        words_per_segment: int = 4,
        gap: float = 0.15,
    ) -> CaptionTrack:
        """Split text into timed caption segments.

        If total_duration is not provided, estimates from word count at 150 WPM.
        """
        words = [w for w in re.findall(r'\S+', text.strip()) if w]
        if not words:
            return CaptionTrack()

        if total_duration is None:
            total_duration = len(words) / self._default_wpm * 60

        segment_count = max(1, len(words) // words_per_segment)
        seg_duration = total_duration / segment_count

        segments: list[CaptionSegment] = []
        idx = 0
        for seg_idx in range(segment_count):
            chunk = words[idx : idx + words_per_segment]
            if not chunk:
                break
            idx += words_per_segment

            start = seg_idx * seg_duration + gap
            end = start + seg_duration
            if seg_idx == segment_count - 1:
                end = total_duration

            segments.append(CaptionSegment(
                text=" ".join(chunk),
                start=round(start, 2),
                end=round(end, 2),
                index=seg_idx,
            ))

        return CaptionTrack(
            segments=segments,
            total_duration=total_duration,
            word_count=len(words),
        )

    def generate_from_script(
        self,
        script_text: str,
        total_duration: float | None = None,
        words_per_segment: int = 3,
    ) -> CaptionTrack:
        """Parse a script (with [SECTION — ts] markers) into timed captions."""
        script_text = re.sub(r'【.*?】', '', script_text)
        script_text = re.sub(r'\[.*?\]', '', script_text)
        lines = [
            line.strip()
            for line in script_text.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]
        clean_text = " ".join(lines)

        return self.generate_captions(
            text=clean_text,
            total_duration=total_duration,
            words_per_segment=words_per_segment,
        )

    def to_srt(self, track: CaptionTrack) -> str:
        """Convert caption track to SRT format."""
        srt_lines: list[str] = []
        for seg in track.segments:
            srt_lines.append(str(seg.index + 1))
            srt_lines.append(
                f"{self._format_srt_time(seg.start)} --> {self._format_srt_time(seg.end)}"
            )
            srt_lines.append(seg.text)
            srt_lines.append("")
        return "\n".join(srt_lines)

    def to_json(self, track: CaptionTrack) -> str:
        """Convert caption track to JSON format."""
        return json.dumps(
            {
                "segments": [
                    {
                        "text": s.text,
                        "start": s.start,
                        "end": s.end,
                        "index": s.index,
                    }
                    for s in track.segments
                ],
                "total_duration": track.total_duration,
                "word_count": track.word_count,
            },
            indent=2,
        )

    def save_srt(self, track: CaptionTrack, filepath: str | Path) -> Path:
        """Save caption track as SRT file."""
        fp = Path(filepath)
        fp.write_text(self.to_srt(track), encoding="utf-8")
        logger.info("Captions saved: %s (%d segments)", fp, len(track.segments))
        return fp

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"
