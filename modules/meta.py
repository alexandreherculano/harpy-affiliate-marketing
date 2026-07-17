"""S8 Meta Agent — funnel planning, compliance checking, category design."""

from __future__ import annotations

from typing import Any

from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.queue import Flywheel, StageOutput
from core.skill_loader import SkillLoader
from modules.base import AgentResult, BaseAgent

logger = get_logger()


class MetaAgent(BaseAgent):
    stage = "meta"
    label = "S8 — Meta (Planning & Compliance)"
    skill_slugs = [
        "funnel-planner",
        "compliance-checker",
    ]

    def run(self, flywheel: Flywheel, feedback: str = "") -> AgentResult:
        context = flywheel.get_stage_context("meta")
        context["all_stages"] = {
            key: {"status": st.status, "output": st.output}
            for key, st in flywheel.stages.items()
        }
        if feedback:
            context["feedback"] = feedback

        raw_outputs: list[str] = []
        previous: list[dict[str, Any]] = []
        total_tokens = 0
        total_calls = 0

        for i, skill in enumerate(self.skills):
            task_context = dict(context)

            if skill.slug == "compliance-checker":
                task_context["platforms"] = flywheel.target_platforms
                task_context["instruction"] = (
                    "Audit all generated content for FTC affiliate disclosure compliance "
                    "AND platform-specific rules for: "
                    f"{', '.join(flywheel.target_platforms)}. "
                    "Flag any violations and provide fix recommendations. "
                    "Check TikTok branded content policies and Instagram's branded content tool requirements."
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

        logger.info("MetaAgent completed — %d calls", total_calls)
        return AgentResult(stage=self.stage, output=stage_output, raw_responses=raw_outputs)
