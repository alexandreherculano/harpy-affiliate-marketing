"""Integration-style tests for agent module execution with mocked DeepSeek."""

from unittest.mock import MagicMock, patch

from core.config import Config
from core.deepseek_client import ChatResponse, DeepSeekClient, Usage
from core.queue import Flywheel, StageOutput
from core.skill_loader import SkillLoader


def _mock_config() -> Config:
    return Config(
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com/v1",
        deepseek_model="deepseek-chat",
        skills_dir="skills/affiliate-skills",
    )


def _mock_response(content: str = '{"result": "ok"}') -> ChatResponse:
    return ChatResponse(
        content=content,
        usage=Usage(prompt_tokens=50, completion_tokens=25, total_tokens=75),
        model="deepseek-chat",
    )


class TestResearchAgentRun:
    @patch.object(SkillLoader, "_load_registry", return_value=None)
    @patch.object(DeepSeekClient, "chat")
    def test_run_returns_agent_result(
        self, mock_chat: MagicMock, _mock_registry: MagicMock
    ) -> None:
        from modules.research import ResearchAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = ResearchAgent(client, loader)

        mock_chat.return_value = _mock_response()

        flywheel = Flywheel.create(niche="AI Tools", platforms=["tiktok", "instagram"])
        result = agent.run(flywheel)

        assert result.stage == "research"
        assert isinstance(result.output, StageOutput)
        assert len(result.output.skills_executed) == 5
        assert "trending-content-scout" in result.output.skills_executed
        assert "niche-opportunity-finder" in result.output.skills_executed
        assert "affiliate-program-search" in result.output.skills_executed
        assert "content-angle-ranker" in result.output.skills_executed
        assert "traffic-analyzer" in result.output.skills_executed
        assert result.output.output is not None
        assert result.output.deepseek_usage["calls"] == 5

    @patch.object(SkillLoader, "_load_registry", return_value=None)
    @patch.object(DeepSeekClient, "chat")
    def test_run_with_feedback_retry(
        self, mock_chat: MagicMock, _mock_registry: MagicMock
    ) -> None:
        from modules.research import ResearchAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = ResearchAgent(client, loader)

        mock_chat.return_value = _mock_response()

        flywheel = Flywheel.create(niche="AI Tools")
        result = agent.run(flywheel, feedback="More TikTok-specific data needed")
        assert result.stage == "research"


class TestContentAgentRun:
    @patch.object(SkillLoader, "_load_registry", return_value=None)
    @patch.object(DeepSeekClient, "chat")
    def test_run_with_platforms(
        self, mock_chat: MagicMock, _mock_registry: MagicMock
    ) -> None:
        from modules.content import ContentAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = ContentAgent(client, loader)

        mock_chat.return_value = _mock_response()

        flywheel = Flywheel.create(niche="AI Tools", platforms=["tiktok", "instagram"])
        result = agent.run(flywheel)

        assert result.stage == "content"
        assert len(result.output.skills_executed) == 4
        assert "tiktok-script-writer" in result.output.skills_executed
        assert "viral-post-writer" in result.output.skills_executed
        assert "infographic-generator" in result.output.skills_executed
        assert "content-research-brief" in result.output.skills_executed


class TestDistributionAgentRun:
    @patch.object(SkillLoader, "_load_registry", return_value=None)
    @patch.object(DeepSeekClient, "chat")
    def test_run_with_dual_platforms(
        self, mock_chat: MagicMock, _mock_registry: MagicMock
    ) -> None:
        from modules.distribution import DistributionAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)
        agent = DistributionAgent(client, loader)

        mock_chat.return_value = _mock_response()

        flywheel = Flywheel.create(
            niche="AI Tools", platforms=["tiktok", "instagram"]
        )
        result = agent.run(flywheel)

        assert result.stage == "distribution"
        assert len(result.output.skills_executed) == 2
        assert "social-media-scheduler" in result.output.skills_executed
        assert "email-drip-sequence" in result.output.skills_executed
        # Verify output has platform context
        call_args = mock_chat.call_args_list[0]
        kwargs = call_args[1] if len(call_args) > 1 else {}
        messages = kwargs.get("messages", call_args[0][0] if call_args[0] else [])
        # The first message should reference the platforms
        if messages:
            content = messages[0].get("content", "")
            assert "tiktok" in content.lower() or "instagram" in content.lower()


class TestFlywheelIntegration:
    @patch.object(SkillLoader, "_load_registry", return_value=None)
    @patch.object(DeepSeekClient, "chat")
    def test_full_flow_with_mocked_llm(
        self, mock_chat: MagicMock, _mock_registry: MagicMock
    ) -> None:
        from modules.research import ResearchAgent
        from modules.content import ContentAgent
        from modules.landing import LandingAgent
        from modules.distribution import DistributionAgent
        from modules.analytics import AnalyticsAgent

        config = _mock_config()
        client = DeepSeekClient(config)
        loader = SkillLoader(config.skills_dir)

        mock_chat.return_value = _mock_response('{"status": "complete", "data": {"key": "val"}}')

        flywheel = Flywheel.create(
            niche="Productivity SaaS",
            platforms=["tiktok", "instagram"],
        )

        agents = [
            ResearchAgent(client, loader),
            ContentAgent(client, loader),
            LandingAgent(client, loader),
            DistributionAgent(client, loader),
            AnalyticsAgent(client, loader),
        ]

        results = []
        for agent in agents:
            result = agent.run(flywheel)
            results.append(result)
            flywheel.set_stage_output(agent.stage, result.output)
            flywheel.approve_stage(agent.stage)

        assert len(results) == 5
        assert flywheel.iteration == 2
        # All stages should be reset pending except research
        assert flywheel.current_stage == "research"
