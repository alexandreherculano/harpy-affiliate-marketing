"""Voiceover engine — gTTS with optional ElevenLabs premium support."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import Config, load_config
from core.logger import get_logger

logger = get_logger()

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False


@dataclass
class VoiceoverResult:
    text: str
    audio_path: Path
    duration: float
    provider: str = "gtts"
    language: str = "en"


class VoiceoverEngine:
    """Generate AI voiceover from text using gTTS (free) or ElevenLabs (premium)."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config(require_api_key=False)
        self.elevenlabs_key = getattr(self.config, "elevenlabs_api_key", "") or ""

    def generate_voiceover(
        self,
        text: str,
        language: str = "en",
        output_dir: str | None = None,
        voice: str = "default",
    ) -> VoiceoverResult:
        """Generate TTS audio from text.

        Uses ElevenLabs if API key is configured, otherwise falls back to gTTS.
        """
        if self.elevenlabs_key:
            return self._elevenlabs_tts(text, language, output_dir, voice)

        return self._gtts_tts(text, language, output_dir)

    def _gtts_tts(
        self,
        text: str,
        language: str = "en",
        output_dir: str | None = None,
    ) -> VoiceoverResult:
        if not GTTS_AVAILABLE:
            raise ImportError(
                "gTTS is not installed. Run: pip install gtts"
            )

        dest = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "harpy_voice"
        dest.mkdir(parents=True, exist_ok=True)

        tts = gTTS(text=text, lang=language, slow=False)
        audio_path = dest / f"voiceover_{hash(text) % 100000}.mp3"
        tts.save(str(audio_path))

        duration = self._estimate_duration(text)

        logger.info(
            "gTTS voiceover saved: %s (est. %.1fs)",
            audio_path,
            duration,
        )
        return VoiceoverResult(
            text=text,
            audio_path=audio_path,
            duration=duration,
            provider="gtts",
            language=language,
        )

    def _elevenlabs_tts(
        self,
        text: str,
        language: str = "en",
        output_dir: str | None = None,
        voice: str = "default",
    ) -> VoiceoverResult:
        import requests

        dest = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "harpy_voice"
        dest.mkdir(parents=True, exist_ok=True)

        voice_id = "21m00Tcm4TlvDq8ikWAM" if voice == "default" else voice
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": self.elevenlabs_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
            },
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()

        audio_path = dest / f"voiceover_eleven_{hash(text) % 100000}.mp3"
        audio_path.write_bytes(resp.content)

        duration = self._estimate_duration(text)

        logger.info(
            "ElevenLabs voiceover saved: %s (est. %.1fs)",
            audio_path,
            duration,
        )
        return VoiceoverResult(
            text=text,
            audio_path=audio_path,
            duration=duration,
            provider="elevenlabs",
            language=language,
        )

    @staticmethod
    def _estimate_duration(text: str) -> float:
        """Estimate audio duration: ~150 words per minute = 2.5 wps."""
        words = len(text.split())
        return max(words / 2.5, 2.0)
