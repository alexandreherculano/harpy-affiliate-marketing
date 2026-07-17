"""S3+S4 Landing Agent — blog posts, bonus stacks, landing pages, bio links."""

from __future__ import annotations

from typing import Any

from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.queue import Flywheel, StageOutput
from core.skill_loader import SkillLoader
from modules.base import AgentResult, BaseAgent

logger = get_logger()


class LandingAgent(BaseAgent):
    stage = "landing"
    label = "S3+S4 — Blog, Landing & Bio"
    skill_slugs = [
        "affiliate-blog-builder",
        "bonus-stack-builder",
        "landing-page-creator",
        "bio-link-deployer",
    ]

    def run(self, flywheel: Flywheel, feedback: str = "") -> AgentResult:
        context = flywheel.get_stage_context(self.stage)
        if feedback:
            context["feedback"] = feedback

        content_data = (
            context.get("previous_stages", {})
            .get("content", {})
            .get("output", {})
        )
        if content_data:
            context["content_data"] = content_data

        raw_outputs: list[str] = []
        previous: list[dict[str, Any]] = []
        total_tokens = 0
        total_calls = 0

        for i, skill in enumerate(self.skills):
            task_context = dict(context)

            if skill.slug == "bio-link-deployer":
                task_context["platforms"] = flywheel.target_platforms
                task_context["instruction"] = (
                    "Create a Linktree-style bio link page. "
                    f"Target platforms: {', '.join(flywheel.target_platforms)}. "
                    "Include sections for the landing page URL, social profiles, "
                    "and the affiliate link."
                )

            raw = self._execute_skill(skill, task_context, previous)
            raw_outputs.append(raw)
            previous.append({"skill_slug": skill.slug, "output": raw})
            total_calls += 1

        merged = self._merge_outputs(raw_outputs)

        stage_output = StageOutput(
            skills_executed=self.skill_slugs,
            output=merged,
            deepseek_usage={
                "tokens_total": total_tokens,
                "calls": total_calls,
                "model": self.client.config.deepseek_model,
            },
        )

        logger.info("LandingAgent completed — %d calls", total_calls)
        return AgentResult(stage=self.stage, output=stage_output, raw_responses=raw_outputs)
