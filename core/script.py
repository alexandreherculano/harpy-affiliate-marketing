"""Standalone Script Agent — generate short-form video scripts, captions, and hashtags.

Uses DeepSeek API with affiliate-skills (tiktok-script-writer, viral-post-writer).
Outputs ready-to-film scripts for TikTok and Instagram Reels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.config import Config, load_config
from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.skill_loader import Skill, SkillLoader

logger = get_logger()


@dataclass
class ScriptOutput:
    title: str = ""
    hook: str = ""
    script: str = ""
    duration: str = ""
    cta: str = ""
    raw: str = ""


@dataclass
class CaptionOutput:
    primary: str = ""
    alternatives: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class HashtagOutput:
    tags: list[str] = field(default_factory=list)
    grouped: dict[str, list[str]] = field(default_factory=dict)
    raw: str = ""


@dataclass
class ScriptResult:
    niche: str
    product_name: str
    script_tiktok: ScriptOutput = field(default_factory=ScriptOutput)
    script_instagram: ScriptOutput = field(default_factory=ScriptOutput)
    captions: CaptionOutput = field(default_factory=CaptionOutput)
    hashtags: HashtagOutput = field(default_factory=HashtagOutput)
    summary: str = ""


class ScriptAgent:
    """Generates short-form video scripts, captions, and hashtags for affiliate content."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config(require_api_key=False)
        self.client = DeepSeekClient(self.config)
        self.loader = SkillLoader(self.config.skills_dir)

    def generate_script(
        self,
        product_name: str,
        niche: str,
        platforms: list[str] | None = None,
        research_context: str = "",
        dry_run: bool = False,
    ) -> dict[str, ScriptOutput]:
        """Generate short-form video scripts for each target platform.

        Uses skill: tiktok-script-writer
        """
        if platforms is None:
            platforms = ["tiktok", "instagram"]

        skill = self.loader.get("tiktok-script-writer")
        if not skill:
            raise RuntimeError("Skill 'tiktok-script-writer' not found.")

        results: dict[str, ScriptOutput] = {}

        for platform in platforms:
            if dry_run:
                results[platform] = self._mock_script(niche, product_name, platform)
                continue

            prompt = (
                f"Write a short-form video script for **{platform.upper()}** "
                f"(also compatible with {'Instagram Reels' if platform == 'tiktok' else 'TikTok'}).\n\n"
                f"**Product:** {product_name}\n"
                f"**Niche:** {niche}\n"
                f"**Target format:** 9:16 vertical, 15-60 seconds\n"
            )
            if research_context:
                prompt += f"\n**Research data:**\n{research_context}\n"

            prompt += (
                f"\nCreate a script with these sections clearly labeled:\n"
                f"1. **HOOK** (first 3 seconds — stop the scroll)\n"
                f"2. **PROBLEM** (what pain point does {product_name} solve)\n"
                f"3. **DEMO** (show the product in action, key benefit)\n"
                f"4. **RESULT** (transformation or outcome)\n"
                f"5. **CTA** (call to action — check bio, link below, etc.)\n\n"
                f"Include:\n"
                f"- Visual directions [in brackets]\n"
                f"- Estimated timing per section\n"
                f"- Platform-specific best practices for {platform}\n\n"
                f"After your script, output a JSON block:\n"
                f'{{"title": "...", "hook": "...", "duration": "...", "cta": "...", '
                f'"script": "full script text"}}'
            )

            raw = self._call_skill(skill, prompt)
            parsed = self._parse_json(raw)

            results[platform] = ScriptOutput(
                title=parsed.get("title", f"{product_name} — {platform}"),
                hook=parsed.get("hook", ""),
                script=parsed.get("script", raw),
                duration=parsed.get("duration", "30s"),
                cta=parsed.get("cta", "Link in bio!"),
                raw=raw,
            )

        return results

    def generate_captions(
        self,
        product_name: str,
        script_text: str = "",
        niche: str = "",
        dry_run: bool = False,
    ) -> CaptionOutput:
        """Generate Instagram/TikTok caption options using viral-post-writer.

        Uses skill: viral-post-writer
        """
        skill = self.loader.get("viral-post-writer")
        if not skill:
            raise RuntimeError("Skill 'viral-post-writer' not found.")

        if dry_run:
            return self._mock_captions(product_name)

        prompt = (
            f"Write 3 Instagram/TikTok caption options for a video promoting **{product_name}**.\n\n"
            f"Niche: {niche}\n"
        )
        if script_text:
            prompt += f"Video script context:\n```\n{script_text[:1000]}\n```\n\n"

        prompt += (
            "Generate:\n"
            "1. **Primary caption** — optimized with emojis, line breaks, and a soft CTA\n"
            "2. **Alternative A** — shorter, punchy, question-based hook\n"
            "3. **Alternative B** — story-driven, longer form with value teaching\n\n"
            "Include FTC-compliant affiliate disclosure in each caption.\n\n"
            "After your captions, output a JSON block:\n"
            '{"primary": "...", "alternatives": ["...", "..."]}'
        )

        raw = self._call_skill(skill, prompt)
        parsed = self._parse_json(raw)

        return CaptionOutput(
            primary=parsed.get("primary", raw),
            alternatives=parsed.get("alternatives", []),
            raw=raw,
        )

    def generate_hashtags(
        self,
        topic: str,
        niche: str = "",
        platform: str = "tiktok",
        dry_run: bool = False,
    ) -> HashtagOutput:
        """Generate optimized hashtag sets for TikTok and Instagram.

        No specific skill slug — uses prompt engineering with DeepSeek directly.
        """
        if dry_run:
            return self._mock_hashtags(topic, platform)

        prompt = (
            f"Generate an optimized hashtag strategy for a **{platform.upper()}** post "
            f"about **{topic}**.\n\n"
            f"Niche: {niche}\n\n"
            "Generate hashtags grouped by category:\n"
            "1. **BROAD** — 3-5 large tags (1M+ posts) for reach\n"
            "2. **NICHE** — 5-8 medium tags (50K-500K) for targeted discovery\n"
            "3. **SPECIFIC** — 3-5 small tags (<50K) for algorithm loyalty\n\n"
            f"Total: 12-18 hashtags optimized for {platform}.\n\n"
            "After your tags, output a JSON block:\n"
            '{"tags": ["..."], "grouped": {"broad": ["..."], "niche": ["..."], "specific": ["..."]}}'
        )

        response = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are a hashtag strategist for social media affiliate marketing. "
                "Generate optimized, platform-specific hashtag sets that maximize reach "
                "and discovery. Output clean, structured JSON."
            ),
        )

        parsed = self._parse_json(response.content)

        return HashtagOutput(
            tags=parsed.get("tags", []),
            grouped=parsed.get("grouped", {}),
            raw=response.content,
        )

    def run_full_script(
        self,
        product_name: str,
        niche: str,
        platforms: list[str] | None = None,
        research_context: str = "",
        dry_run: bool = False,
    ) -> ScriptResult:
        """Run all script generation steps and return consolidated output."""
        if platforms is None:
            platforms = ["tiktok", "instagram"]

        logger.info(
            "ScriptAgent starting — product=%s niche=%s dry_run=%s",
            product_name,
            niche,
            dry_run,
        )

        scripts = self.generate_script(
            product_name=product_name,
            niche=niche,
            platforms=platforms,
            research_context=research_context,
            dry_run=dry_run,
        )

        tiktok_script = scripts.get("tiktok", ScriptOutput())
        combined_text = tiktok_script.script or ""

        captions = self.generate_captions(
            product_name=product_name,
            script_text=combined_text,
            niche=niche,
            dry_run=dry_run,
        )

        hashtags = self.generate_hashtags(
            topic=product_name,
            niche=niche,
            platform=platforms[0],
            dry_run=dry_run,
        )

        summary_lines = [
            f"Scripts generated for {len(scripts)} platform(s): {', '.join(scripts.keys())}.",
        ]
        if tiktok_script.hook:
            summary_lines.append(f"TikTok hook: \"{tiktok_script.hook}\"")
        if captions.primary:
            first_line = captions.primary.split("\n")[0][:100]
            summary_lines.append(f"Primary caption: \"{first_line}...\"")
        if hashtags.tags:
            summary_lines.append(f"Hashtags: {len(hashtags.tags)} tags generated")

        logger.info("ScriptAgent complete for: %s", product_name)
        return ScriptResult(
            niche=niche,
            product_name=product_name,
            script_tiktok=scripts.get("tiktok", ScriptOutput()),
            script_instagram=scripts.get("instagram", ScriptOutput()),
            captions=captions,
            hashtags=hashtags,
            summary="\n".join(summary_lines),
        )

    def _call_skill(self, skill: Skill, prompt: str) -> str:
        logger.info("Calling skill: %s", skill.slug)
        response = self.client.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=skill.system_prompt,
        )
        logger.info(
            "Skill %s complete — %d tokens",
            skill.slug,
            response.usage.total_tokens,
        )
        return response.content

    def _parse_json(self, raw: str) -> dict[str, Any]:
        import json
        import re

        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}

    def _mock_script(
        self, niche: str, product: str, platform: str
    ) -> ScriptOutput:
        platform_name = {"tiktok": "TikTok", "instagram": "Instagram Reels"}.get(
            platform, platform
        )
        return ScriptOutput(
            title=f"{product} Review — {platform_name}",
            hook=f"Stop buying {niche} products that don't work. I found THE one.",
            script=(
                f"[HOOK — 0-3s]\n"
                f"🎬 【Text overlay: \"Stop wasting money on {niche} gadgets\"】\n"
                f"Voice: \"I tested 5 {niche} devices. Only ONE actually delivered.\"\n\n"
                f"[PROBLEM — 3-10s]\n"
                f"【B-roll of frustrated user with competing products】\n"
                f"Voice: \"Most {niche} products overpromise and underdeliver.\"\n\n"
                f"[DEMO — 10-25s]\n"
                f"【Screen recording of {product} in action】\n"
                f"Voice: \"Then I found {product}. Here's what happened...\"\n\n"
                f"[RESULT — 25-35s]\n"
                f"【Before/After split screen】\n"
                f"Voice: \"In just 7 days, everything changed.\"\n\n"
                f"[CTA — 35-40s]\n"
                f"【Point down to comments/bio】\n"
                f"Voice: \"Link in bio to get {product}. You're welcome.\""
            ),
            duration="40s",
            cta="Link in bio to get yours!",
            raw="[DRY RUN] Mock script — no API call made.",
        )

    def _mock_captions(self, product: str) -> CaptionOutput:
        return CaptionOutput(
            primary=(
                f"🚨 I finally found the {product} that actually works.\n\n"
                f"After testing 5 different options, this one stands out. "
                f"Here's why 👇\n\n"
                f"Full review in my bio.\n\n"
                f"#ad #affiliate"
            ),
            alternatives=[
                f"What's the ONE {product} you'd recommend to a friend? "
                f"Mine is linked in bio. #affiliate",
                f"I spent $500 testing {product} alternatives so you don't have to. "
                f"Here's what I learned... 🧵",
            ],
            raw="[DRY RUN] Mock captions — no API call made.",
        )

    def _mock_hashtags(self, topic: str, platform: str) -> HashtagOutput:
        return HashtagOutput(
            tags=[
                f"#{topic.replace(' ', '')}",
                f"#{topic.replace(' ', '')}Review",
                "#TechReview",
                "#SmartHome",
                "#GadgetReview",
                "#TikTokMadeMeBuyIt",
                "#MustHave",
                "#HomeTech",
                "#LifeHack",
                "#ProductReview",
            ],
            grouped={
                "broad": ["#TechReview", "#SmartHome", "#GadgetReview"],
                "niche": [
                    f"#{topic.replace(' ', '')}",
                    f"#{topic.replace(' ', '')}Review",
                    "#TikTokMadeMeBuyIt",
                ],
                "specific": ["#HomeTech", "#LifeHack", "#ProductReview", "#MustHave"],
            },
            raw="[DRY RUN] Mock hashtags — no API call made.",
        )
