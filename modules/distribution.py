"""S5 Distribution Agent — social media scheduling (TikTok + Instagram), email drip."""

from __future__ import annotations

from typing import Any

from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.queue import Flywheel, StageOutput
from core.skill_loader import SkillLoader
from modules.base import AgentResult, BaseAgent

logger = get_logger()


class DistributionAgent(BaseAgent):
    stage = "distribution"
    label = "S5 — Distribution (TikTok + Instagram)"
    skill_slugs = [
        "social-media-scheduler",
        "email-drip-sequence",
    ]

    def run(self, flywheel: Flywheel, feedback: str = "") -> AgentResult:
        context = flywheel.get_stage_context(self.stage)
        if feedback:
            context["feedback"] = feedback

        landing_data = (
            context.get("previous_stages", {})
            .get("landing", {})
            .get("output", {})
        )
        if landing_data:
            context["landing_data"] = landing_data

        raw_outputs: list[str] = []
        previous: list[dict[str, Any]] = []
        total_tokens = 0
        total_calls = 0

        for i, skill in enumerate(self.skills):
            task_context = dict(context)

            if skill.slug == "social-media-scheduler":
                platforms = flywheel.target_platforms
                task_context["platforms"] = platforms
                task_context["instruction"] = (
                    f"Create a 30-day social media content calendar for: {', '.join(platforms)}. "
                    "For TikTok: schedule 3-5 posts per week at peak times (7pm-10pm). "
                    "For Instagram: alternate between Reels (same format as TikTok), "
                    "Feed posts, Carousel posts, and Stories. "
                    "Include captions, hashtags, and recommended posting times for each platform. "
                    "Reels and TikTok videos can share the same content/scripts."
                )

            raw = self._execute_skill(skill, task_context, previous)
            raw_outputs.append(raw)
            previous.append({"skill_slug": skill.slug, "output": raw})
            total_calls += 1

        merged = self._merge_outputs(raw_outputs)
        merged["target_platforms"] = flywheel.target_platforms

        stage_output = StageOutput(
            skills_executed=self.skill_slugs,
            output=merged,
            deepseek_usage={
                "tokens_total": total_tokens,
                "calls": total_calls,
                "model": self.client.config.deepseek_model,
            },
        )

        logger.info("DistributionAgent completed — %d calls", total_calls)
        return AgentResult(stage=self.stage, output=stage_output, raw_responses=raw_outputs)
