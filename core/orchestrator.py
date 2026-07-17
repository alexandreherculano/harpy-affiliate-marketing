"""Orchestrator — runs the flywheel loop, coordinating agents across all stages."""

from __future__ import annotations

from typing import Any

from core.config import Config
from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.queue import Flywheel, QueueManager, StageOutput, StageState
from core.skill_loader import SkillLoader
from modules.analytics import AnalyticsAgent
from modules.base import AgentResult, BaseAgent
from modules.content import ContentAgent
from modules.distribution import DistributionAgent
from modules.landing import LandingAgent
from modules.meta import MetaAgent
from modules.research import ResearchAgent

logger = get_logger()

STAGE_ORDER = ["research", "content", "landing", "distribution", "analytics"]


class Orchestrator:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.queue = QueueManager(config.output_dir)
        self.client = DeepSeekClient(config)
        self.loader = SkillLoader(config.skills_dir)
        self._agents: dict[str, BaseAgent] = {
            "research": ResearchAgent(self.client, self.loader),
            "content": ContentAgent(self.client, self.loader),
            "landing": LandingAgent(self.client, self.loader),
            "distribution": DistributionAgent(self.client, self.loader),
            "analytics": AnalyticsAgent(self.client, self.loader),
            "meta": MetaAgent(self.client, self.loader),
        }

    def get_agent(self, stage: str) -> BaseAgent | None:
        return self._agents.get(stage)

    def run_stage(self, flywheel: Flywheel, feedback: str = "") -> AgentResult:
        stage = flywheel.current_stage
        if not stage:
            raise ValueError("No stage in progress or awaiting approval.")

        agent = self.get_agent(stage)
        if not agent:
            raise ValueError(f"No agent registered for stage: {stage}")

        logger.info(
            "Running stage %s for flywheel %s (%s)",
            stage,
            flywheel.flywheel_id,
            flywheel.niche,
        )
        result = agent.run(flywheel, feedback=feedback)
        flywheel.set_stage_output(stage, result.output)
        self.queue.save_flywheel(flywheel)
        return result

    def approve_stage(self, flywheel: Flywheel, stage: str) -> None:
        flywheel.approve_stage(stage)
        current_idx = STAGE_ORDER.index(stage) if stage in STAGE_ORDER else -1

        if current_idx == len(STAGE_ORDER) - 1:
            self._close_flywheel_loop(flywheel)
        else:
            next_stage = flywheel.current_stage
            if next_stage:
                logger.info(
                    "Advanced flywheel %s to stage: %s",
                    flywheel.flywheel_id,
                    next_stage,
                )

        self.queue.save_flywheel(flywheel)

    def reject_stage(self, flywheel: Flywheel, stage: str, feedback: str) -> None:
        flywheel.reject_stage(stage, feedback)
        self.queue.save_flywheel(flywheel)
        logger.info(
            "Rejected stage %s for flywheel %s — feedback: %s",
            stage,
            flywheel.flywheel_id,
            feedback,
        )

    def _close_flywheel_loop(self, flywheel: Flywheel) -> None:
        analytics_data = flywheel.stages.get("analytics", StageState())
        current_iteration = flywheel.iteration

        logger.info(
            "Flywheel %s iteration %d complete — closing loop to S1",
            flywheel.flywheel_id,
            current_iteration,
        )

        flywheel.iteration += 1
        for stage in STAGE_ORDER:
            flywheel.stages[stage].status = "pending"
            flywheel.stages[stage].output = {}
            flywheel.stages[stage].skills_executed = []
        flywheel.stages["research"].status = "in_progress"
        flywheel.touch()

        if analytics_data and analytics_data.output:
            research_stage = flywheel.stages["research"]
            research_stage.output = {
                "previous_iteration_analytics": analytics_data.output,
                "iteration": current_iteration,
            }

    def run_full_flywheel(
        self,
        flywheel: Flywheel,
        interactive: bool = True,
    ) -> Flywheel:
        import sys

        while flywheel.current_stage:
            stage = flywheel.current_stage
            st_state = flywheel.stages.get(stage)

            if st_state and st_state.status == "awaiting_approval":
                if interactive:
                    approved = self._prompt_approval(flywheel, stage)
                else:
                    approved = True

                if approved:
                    self.approve_stage(flywheel, stage)
                else:
                    feedback = input("> Feedback for re-execution: ").strip()
                    self.reject_stage(flywheel, stage, feedback)
                    result = self.run_stage(flywheel, feedback=feedback)
                    self._display_result(result)
                continue

            result = self.run_stage(flywheel)
            self._display_result(result)

            if interactive:
                approved = self._prompt_approval(flywheel, stage)
                if approved:
                    self.approve_stage(flywheel, stage)
                else:
                    feedback = input("> Feedback for re-execution: ").strip()
                    self.reject_stage(flywheel, stage, feedback)
            else:
                self.approve_stage(flywheel, stage)

        return flywheel

    def _display_result(self, result: AgentResult) -> None:
        agent = self.get_agent(result.stage)
        label = agent.label if agent else result.stage
        skills = result.output.skills_executed
        tokens = result.output.deepseek_usage.get("tokens_total", 0)
        calls = result.output.deepseek_usage.get("calls", 0)

        print(f"\n{'=' * 60}")
        print(f"  {label} — Complete")
        print(f"  Skills executed: {', '.join(skills)}")
        print(f"  DeepSeek calls: {calls}, tokens: {tokens}")
        print(f"{'=' * 60}")

        for i, raw in enumerate(result.raw_responses):
            truncated = raw[:500] + "..." if len(raw) > 500 else raw
            print(f"\n  --- Skill {i + 1}: {skills[i] if i < len(skills) else '?'} ---")
            print(f"  {truncated}")

    def _prompt_approval(self, flywheel: Flywheel, stage: str) -> bool:
        st = flywheel.stages.get(stage)
        skills = st.skills_executed if st else []
        print(f"\n{'~' * 50}")
        print(f"  Stage: {stage} | Skills: {', '.join(skills)}")
        print(f"  Flywheel: {flywheel.niche} (iteration {flywheel.iteration})")
        print(f"{'~' * 50}")
        choice = input("  Approve? [y/n/e(dit)]: ").strip().lower()
        if choice == "y":
            return True
        if choice == "e":
            print("  Edit mode: enter feedback to refine output, then re-approve.")
            fb = input("  > Feedback: ").strip()
            self.reject_stage(flywheel, stage, fb)
            result = self.run_stage(flywheel, feedback=fb)
            self._display_result(result)
            return self._prompt_approval(flywheel, stage)
        return False
