"""Tests for the orchestrator and agent modules."""

import tempfile
from unittest.mock import MagicMock, patch

from core.config import Config
from core.deepseek_client import ChatResponse, DeepSeekClient, Usage
from core.orchestrator import Orchestrator
from core.queue import Flywheel, QueueManager, StageOutput
from core.skill_loader import SkillLoader


def _mock_config() -> Config:
    return Config(
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com/v1",
        deepseek_model="deepseek-chat",
        skills_dir="skills/affiliate-skills",
    )


def _mock_chat_response(content: str = "Mock response") -> ChatResponse:
    return ChatResponse(
        content=content,
        usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        model="deepseek-chat",
    )


class TestOrchestrator:
    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_orchestrator_initialization(self, _mock_registry: MagicMock) -> None:
        config = _mock_config()
        orchestrator = Orchestrator(config)
        assert "research" in orchestrator._agents
        assert "content" in orchestrator._agents
        assert "landing" in orchestrator._agents
        assert "distribution" in orchestrator._agents
        assert "analytics" in orchestrator._agents
        assert "meta" in orchestrator._agents

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_get_agent(self, _mock_registry: MagicMock) -> None:
        config = _mock_config()
        orchestrator = Orchestrator(config)
        agent = orchestrator.get_agent("research")
        assert agent is not None
        assert agent.stage == "research"

        assert orchestrator.get_agent("nonexistent") is None

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_approve_stage_advances(self, _mock_registry: MagicMock) -> None:
        config = _mock_config()
        orchestrator = Orchestrator(config)
        fw = Flywheel.create(niche="Test")

        fw.set_stage_output("research", StageOutput(skills_executed=["test"]))
        orchestrator.approve_stage(fw, "research")

        assert fw.stages["research"].status == "completed"
        assert fw.current_stage == "content"

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_reject_stage_resets(self, _mock_registry: MagicMock) -> None:
        config = _mock_config()
        orchestrator = Orchestrator(config)
        fw = Flywheel.create(niche="Test")

        orchestrator.reject_stage(fw, "research", "Needs more data")
        assert fw.stages["research"].status == "in_progress"
        assert fw.stages["research"].feedback == "Needs more data"

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_full_flywheel_loop_closure(self, _mock_registry: MagicMock) -> None:
        config = _mock_config()
        orchestrator = Orchestrator(config)
        fw = Flywheel.create(niche="Test")

        for stage in Flywheel.stage_order()[:-1]:
            fw.set_stage_output(stage, StageOutput(skills_executed=["test"]))
            orchestrator.approve_stage(fw, stage)

        last = Flywheel.stage_order()[-1]
        fw.set_stage_output(last, StageOutput(skills_executed=["analytics"]))
        orchestrator.approve_stage(fw, last)

        assert fw.iteration == 2
        assert fw.current_stage == "research"


class TestBaseAgent:
    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_skill_loading(self, _mock_registry: MagicMock) -> None:
        from modules.research import ResearchAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)

        agent = ResearchAgent(client, loader)
        assert agent.stage == "research"
        assert len(agent.skill_slugs) == 5
        assert "trending-content-scout" in agent.skill_slugs


class TestAgentsExist:
    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_research_agent(self, _mock_registry: MagicMock) -> None:
        from modules.research import ResearchAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = ResearchAgent(client, loader)
        assert agent.stage == "research"
        assert len(agent.skill_slugs) == 5

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_content_agent(self, _mock_registry: MagicMock) -> None:
        from modules.content import ContentAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = ContentAgent(client, loader)
        assert agent.stage == "content"
        assert len(agent.skill_slugs) == 4

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_landing_agent(self, _mock_registry: MagicMock) -> None:
        from modules.landing import LandingAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = LandingAgent(client, loader)
        assert agent.stage == "landing"
        assert len(agent.skill_slugs) == 4

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_distribution_agent(self, _mock_registry: MagicMock) -> None:
        from modules.distribution import DistributionAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = DistributionAgent(client, loader)
        assert agent.stage == "distribution"
        assert len(agent.skill_slugs) == 2

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_analytics_agent(self, _mock_registry: MagicMock) -> None:
        from modules.analytics import AnalyticsAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = AnalyticsAgent(client, loader)
        assert agent.stage == "analytics"
        assert len(agent.skill_slugs) == 3

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    def test_meta_agent(self, _mock_registry: MagicMock) -> None:
        from modules.meta import MetaAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = MetaAgent(client, loader)
        assert agent.stage == "meta"
        assert len(agent.skill_slugs) == 2


class TestDeepSeekClient:
    def test_client_initialization(self) -> None:
        config = _mock_config()
        client = DeepSeekClient(config)
        assert client.config.deepseek_api_key == "test-key"
        assert client.config.deepseek_model == "deepseek-chat"

    def test_build_messages_with_system_prompt(self) -> None:
        config = _mock_config()
        client = DeepSeekClient(config)
        msgs = client._build_messages(
            [{"role": "user", "content": "Hello"}],
            system_prompt="You are helpful.",
        )
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are helpful."
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "Hello"

    def test_build_messages_without_system_prompt(self) -> None:
        config = _mock_config()
        client = DeepSeekClient(config)
        msgs = client._build_messages(
            [{"role": "user", "content": "Hello"}],
        )
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_parse_response(self) -> None:
        config = _mock_config()
        client = DeepSeekClient(config)
        data = {
            "choices": [{"message": {"content": "Hi!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            "model": "deepseek-chat",
        }
        resp = client._parse_response(data)
        assert resp.content == "Hi!"
        assert resp.usage.prompt_tokens == 10
        assert resp.usage.completion_tokens == 2
        assert resp.usage.total_tokens == 12
        assert resp.finish_reason == "stop"
