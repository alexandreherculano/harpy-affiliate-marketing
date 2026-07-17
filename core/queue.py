"""Flywheel state management — multi-niche support with structured stage tracking."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.logger import get_logger

logger = get_logger()


class StageOutput(BaseModel):
    skills_executed: list[str] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    deepseek_usage: dict[str, Any] = Field(default_factory=dict)
    approved_by_user: bool | None = None
    feedback: str = ""


class StageState(BaseModel):
    status: str = "pending"
    skills_executed: list[str] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    deepseek_usage: dict[str, Any] = Field(default_factory=dict)
    approved_by_user: bool | None = None
    feedback: str = ""
    started_at: str | None = None
    completed_at: str | None = None


class Flywheel(BaseModel):
    flywheel_id: str = Field(default_factory=lambda: f"fw_{uuid.uuid4().hex[:8]}")
    niche: str
    niche_slug: str
    status: str = "active"
    iteration: int = 1
    target_platforms: list[str] = Field(default_factory=lambda: ["tiktok", "instagram"])
    stages: dict[str, StageState] = Field(default_factory=dict)
    human_approvals: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def create(
        cls,
        niche: str,
        platforms: list[str] | None = None,
    ) -> Flywheel:
        slug = niche.lower().replace(" ", "-").replace("&", "and")
        stages: dict[str, StageState] = {}
        for stage_key in cls.stage_order():
            stages[stage_key] = StageState(status="pending")
        stages[cls.stage_order()[0]].status = "in_progress"

        return cls(
            niche=niche,
            niche_slug=slug,
            target_platforms=platforms or ["tiktok", "instagram"],
            stages=stages,
        )

    @property
    def current_stage(self) -> str | None:
        for stage in self.stage_order():
            st = self.stages.get(stage)
            if st and st.status in ("in_progress", "awaiting_approval"):
                return stage
        return None

    @property
    def completed_stages(self) -> list[str]:
        return [s for s in self.stage_order() if self.stages.get(s, StageState()).status == "completed"]

    @property
    def has_approved_output(self) -> bool:
        return bool(self.completed_stages)

    def advance_to_next_stage(self) -> str | None:
        current = self.current_stage
        order = self.stage_order()

        if current:
            idx = order.index(current)
            next_idx = idx + 1
        else:
            next_idx = 0
            for i, s in enumerate(order):
                if self.stages.get(s, StageState()).status == "pending":
                    next_idx = i
                    break

        if next_idx < len(order):
            next_stage = order[next_idx]
            self.stages[next_stage].status = "in_progress"
            self.stages[next_stage].started_at = datetime.now(timezone.utc).isoformat()
            self.touch()
            return next_stage
        return None

    def set_stage_output(self, stage: str, output: StageOutput) -> None:
        st = self.stages.setdefault(stage, StageState())
        st.status = "awaiting_approval"
        st.skills_executed = output.skills_executed
        st.output = output.output
        st.deepseek_usage = output.deepseek_usage
        st.completed_at = datetime.now(timezone.utc).isoformat()
        self.touch()

    def approve_stage(self, stage: str) -> None:
        st = self.stages[stage]
        st.status = "completed"
        st.approved_by_user = True
        self.human_approvals.append({
            "stage": stage,
            "action": "approved",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.advance_to_next_stage()
        self.touch()

    def reject_stage(self, stage: str, feedback: str) -> None:
        st = self.stages[stage]
        st.status = "in_progress"
        st.feedback = feedback
        st.approved_by_user = False
        self.human_approvals.append({
            "stage": stage,
            "action": "rejected",
            "feedback": feedback,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.touch()

    def get_stage_context(self, stage: str) -> dict[str, Any]:
        order = self.stage_order()
        idx = order.index(stage) if stage in order else -1
        context: dict[str, Any] = {
            "niche": self.niche,
            "niche_slug": self.niche_slug,
            "iteration": self.iteration,
            "target_platforms": self.target_platforms,
            "current_stage": stage,
            "previous_stages": {},
        }
        for i in range(idx):
            prev_key = order[i]
            prev_st = self.stages.get(prev_key)
            if prev_st and prev_st.status == "completed":
                context["previous_stages"][prev_key] = {
                    "output": prev_st.output,
                    "skills_executed": prev_st.skills_executed,
                }
        return context

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def stage_order() -> list[str]:
        return ["research", "content", "landing", "distribution", "analytics"]


class QueueManager:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _filepath(self, niche_slug: str) -> Path:
        return self.output_dir / f"{niche_slug}.json"

    def list_flywheels(self) -> list[str]:
        return sorted(
            p.stem for p in self.output_dir.glob("*.json") if p.is_file()
        )

    def get_flywheel(self, niche_slug: str) -> Flywheel | None:
        fp = self._filepath(niche_slug)
        if not fp.exists():
            return None
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            return Flywheel(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Failed to load flywheel %s: %s", niche_slug, e)
            return None

    def create_flywheel(
        self, niche: str, platforms: list[str] | None = None
    ) -> Flywheel:
        fw = Flywheel.create(niche=niche, platforms=platforms)
        self.save_flywheel(fw)
        logger.info("Created flywheel %s: %s", fw.flywheel_id, fw.niche)
        return fw

    def save_flywheel(self, fw: Flywheel) -> None:
        fw.touch()
        fp = self._filepath(fw.niche_slug)
        fp.write_text(fw.model_dump_json(indent=2), encoding="utf-8")
        logger.debug("Saved flywheel %s to %s", fw.flywheel_id, fp)

    def delete_flywheel(self, niche_slug: str) -> bool:
        fp = self._filepath(niche_slug)
        if fp.exists():
            fp.unlink()
            logger.info("Deleted flywheel %s", niche_slug)
            return True
        return False

    def load_all(self) -> list[Flywheel]:
        result: list[Flywheel] = []
        for slug in self.list_flywheels():
            fw = self.get_flywheel(slug)
            if fw:
                result.append(fw)
        return result
