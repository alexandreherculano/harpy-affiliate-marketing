"""BaseAgent — abstract class for all flywheel stage agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.deepseek_client import DeepSeekClient
from core.logger import get_logger
from core.queue import Flywheel, StageOutput
from core.skill_loader import Skill, SkillLoader

logger = get_logger()


@dataclass
class AgentResult:
    stage: str
    output: StageOutput
    raw_responses: list[str] = field(default_factory=list)


class BaseAgent(ABC):
    stage: str
    skill_slugs: list[str]
    label: str

    def __init__(
        self,
        client: DeepSeekClient,
        loader: SkillLoader,
    ) -> None:
        self.client = client
        self.loader = loader
        self._skills: list[Skill] | None = None

    @property
    def skills(self) -> list[Skill]:
        if self._skills is None:
            self._skills = self.loader.get_many(self.skill_slugs)
        return self._skills

    @abstractmethod
    def run(self, flywheel: Flywheel, feedback: str = "") -> AgentResult:
        ...

    def _execute_skill(
        self,
        skill: Skill,
        context: dict[str, Any],
        previous_outputs: list[dict[str, Any]],
    ) -> str:
        messages: list[dict[str, str]] = []

        if previous_outputs:
            prev_text = "\n\n---\n\n".join(
                self._format_previous(i, p) for i, p in enumerate(previous_outputs)
            )
            messages.append({
                "role": "user",
                "content": f"## Previous skill outputs in this stage\n\n{prev_text}\n\n## Current task\n\nExecute skill `{skill.name}` ({skill.slug}) using the context below.\n\nStage context:\n{self._format_context(context)}",
            })
        else:
            messages.append({
                "role": "user",
                "content": f"Execute skill `{skill.name}` ({skill.slug}).\n\nStage context:\n{self._format_context(context)}",
            })

        logger.info("Executing skill: %s", skill.slug)
        response = self.client.chat(
            messages=messages,
            system_prompt=skill.system_prompt,
        )
        logger.info(
            "Skill %s complete — %d tokens",
            skill.slug,
            response.usage.total_tokens,
        )
        return response.content

    def _format_context(self, context: dict[str, Any]) -> str:
        import json

        return json.dumps(context, indent=2, ensure_ascii=False, default=str)

    def _format_previous(self, index: int, output: dict[str, Any]) -> str:
        import json

        return f"### Skill {index + 1} output\n\n{json.dumps(output, indent=2, ensure_ascii=False, default=str)}"

    def _merge_outputs(self, raw_outputs: list[str]) -> dict[str, Any]:
        merged: dict[str, Any] = {"raw_skill_outputs": []}
        for i, raw in enumerate(raw_outputs):
            merged["raw_skill_outputs"].append({
                "skill_index": i,
                "skill_slug": self.skill_slugs[i] if i < len(self.skill_slugs) else "unknown",
                "content": raw,
            })
        if raw_outputs:
            merged["final_output"] = raw_outputs[-1]
        return merged

    def _extract_json_from_response(self, raw: str) -> dict[str, Any]:
        import json
        import re

        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return {}
