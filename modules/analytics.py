"""S6 Analytics Agent — conversion tracking, performance reports, SEO audit."""

from __future__ import annotations

from typing import Any

from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.queue import Flywheel, StageOutput
from core.skill_loader import SkillLoader
from modules.base import AgentResult, BaseAgent

logger = get_logger()


class AnalyticsAgent(BaseAgent):
    stage = "analytics"
    label = "S6 — Analytics & Feedback Loop"
    skill_slugs = [
        "conversion-tracker",
        "performance-report",
        "seo-audit",
    ]

    def run(self, flywheel: Flywheel, feedback: str = "") -> AgentResult:
        context = flywheel.get_stage_context(self.stage)
        if feedback:
            context["feedback"] = feedback

        dist_data = (
            context.get("previous_stages", {})
            .get("distribution", {})
            .get("output", {})
        )
        if dist_data:
            context["distribution_data"] = dist_data

        raw_outputs: list[str] = []
        previous: list[dict[str, Any]] = []
        total_tokens = 0
        total_calls = 0

        for i, skill in enumerate(self.skills):
            task_context = dict(context)

            if skill.slug == "performance-report":
                task_context["platforms"] = flywheel.target_platforms
                task_context["instruction"] = (
                    "Generate a performance report covering TikTok AND Instagram metrics: "
                    "views, likes, shares, comments, saves, CTR, conversion rate. "
                    "Compare platform performance. Provide actionable optimization "
                    "recommendations for the next iteration of the flywheel."
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

        logger.info("AnalyticsAgent completed — %d calls", total_calls)
        return AgentResult(stage=self.stage, output=stage_output, raw_responses=raw_outputs)
