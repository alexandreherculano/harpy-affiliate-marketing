"""S1 Research Agent — trend scouting, niche analysis, program search, angle ranking."""

from __future__ import annotations

from typing import Any

from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.queue import Flywheel, StageOutput
from core.skill_loader import SkillLoader
from modules.base import AgentResult, BaseAgent

logger = get_logger()


class ResearchAgent(BaseAgent):
    stage = "research"
    label = "S1 — Research & Discovery"
    skill_slugs = [
        "trending-content-scout",
        "niche-opportunity-finder",
        "affiliate-program-search",
        "content-angle-ranker",
        "traffic-analyzer",
    ]

    def run(self, flywheel: Flywheel, feedback: str = "") -> AgentResult:
        context = flywheel.get_stage_context(self.stage)
        if feedback:
            context["feedback"] = feedback
            logger.info("ResearchAgent retrying with feedback: %s", feedback)

        raw_outputs: list[str] = []
        previous: list[dict[str, Any]] = []
        total_tokens = 0
        total_calls = 0

        for i, skill in enumerate(self.skills):
            raw = self._execute_skill(skill, context, previous)
            raw_outputs.append(raw)
            previous.append({"skill_slug": skill.slug, "output": raw})
            total_calls += 1

        merged = self._merge_outputs(raw_outputs)
        merged["niche"] = flywheel.niche
        merged["niche_slug"] = flywheel.niche_slug
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

        logger.info(
            "ResearchAgent completed — %d calls, %d tokens",
            total_calls,
            total_tokens,
        )
        return AgentResult(stage=self.stage, output=stage_output, raw_responses=raw_outputs)
