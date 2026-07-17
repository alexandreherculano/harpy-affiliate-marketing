"""S2 Content Agent — script writing, viral posts, infographics, research briefs."""

from __future__ import annotations

from typing import Any

from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.queue import Flywheel, StageOutput
from core.skill_loader import SkillLoader
from modules.base import AgentResult, BaseAgent

logger = get_logger()


class ContentAgent(BaseAgent):
    stage = "content"
    label = "S2 — Content Creation"
    skill_slugs = [
        "content-research-brief",
        "tiktok-script-writer",
        "viral-post-writer",
        "infographic-generator",
    ]

    def run(self, flywheel: Flywheel, feedback: str = "") -> AgentResult:
        context = flywheel.get_stage_context(self.stage)
        if feedback:
            context["feedback"] = feedback

        research_data = context.get("previous_stages", {}).get("research", {}).get("output", {})
        if research_data:
            context["research_data"] = research_data

        raw_outputs: list[str] = []
        previous: list[dict[str, Any]] = []
        total_tokens = 0
        total_calls = 0

        for i, skill in enumerate(self.skills):
            task_context = dict(context)

            if skill.slug == "tiktok-script-writer":
                task_context["platforms"] = flywheel.target_platforms
                task_context["instruction"] = (
                    "Create short-form video scripts optimized for TikTok AND Instagram Reels. "
                    "Both platforms use the same 9:16 vertical format. Generate 2 script variations "
                    "per platform mentioned in the target_platforms."
                )
            elif skill.slug == "viral-post-writer":
                task_context["platforms"] = flywheel.target_platforms
                if "instagram" in flywheel.target_platforms:
                    task_context.setdefault("extra_platforms", []).append(
                        "Instagram Feed/Carousel — create posts adapted for Instagram's visual-first audience"
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

        logger.info("ContentAgent completed — %d calls", total_calls)
        return AgentResult(stage=self.stage, output=stage_output, raw_responses=raw_outputs)
