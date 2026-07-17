"""Tests for flywheel queue and state management."""

import json
import tempfile
from pathlib import Path

from core.queue import Flywheel, QueueManager, StageOutput, StageState


class TestFlywheel:
    def test_create_flywheel(self) -> None:
        fw = Flywheel.create(niche="AI Video Tools", platforms=["tiktok", "instagram"])
        assert fw.niche == "AI Video Tools"
        assert fw.niche_slug == "ai-video-tools"
        assert "tiktok" in fw.target_platforms
        assert "instagram" in fw.target_platforms
        assert fw.current_stage == "research"
        assert fw.status == "active"
        assert fw.iteration == 1

    def test_stage_order(self) -> None:
        order = Flywheel.stage_order()
        assert order == ["research", "content", "landing", "distribution", "analytics"]

    def test_all_stages_initialized(self) -> None:
        fw = Flywheel.create(niche="Test")
        for stage in Flywheel.stage_order():
            assert stage in fw.stages
            if stage == "research":
                assert fw.stages[stage].status == "in_progress"
            else:
                assert fw.stages[stage].status == "pending"

    def test_current_stage(self) -> None:
        fw = Flywheel.create(niche="Test")
        assert fw.current_stage == "research"
        fw.stages["research"].status = "completed"
        assert fw.current_stage is None

    def test_set_stage_output(self) -> None:
        fw = Flywheel.create(niche="Test")
        output = StageOutput(
            skills_executed=["trending-content-scout"],
            output={"key": "value"},
            deepseek_usage={"tokens_total": 100, "calls": 1},
        )
        fw.set_stage_output("research", output)
        st = fw.stages["research"]
        assert st.status == "awaiting_approval"
        assert "trending-content-scout" in st.skills_executed
        assert st.output == {"key": "value"}

    def test_approve_stage_progression(self) -> None:
        fw = Flywheel.create(niche="Test")
        fw.approve_stage("research")
        assert fw.stages["research"].status == "completed"
        assert fw.stages["research"].approved_by_user is True
        assert fw.current_stage == "content"
        assert len(fw.human_approvals) == 1
        assert fw.human_approvals[0]["action"] == "approved"

    def test_reject_stage(self) -> None:
        fw = Flywheel.create(niche="Test")
        fw.reject_stage("research", "Not data-driven enough")
        st = fw.stages["research"]
        assert st.status == "in_progress"
        assert st.feedback == "Not data-driven enough"
        assert st.approved_by_user is False

    def test_stage_progression_through_all(self) -> None:
        fw = Flywheel.create(niche="Test")
        for stage in Flywheel.stage_order():
            fw.set_stage_output(stage, StageOutput(skills_executed=["test-skill"]))
            fw.approve_stage(stage)
            if stage != Flywheel.stage_order()[-1]:
                assert fw.stages[stage].status == "completed"

    def test_flywheel_loop_closure(self) -> None:
        fw = Flywheel.create(niche="Test")
        for stage in Flywheel.stage_order()[:-1]:
            fw.set_stage_output(stage, StageOutput(skills_executed=["test"]))
            fw.approve_stage(stage)

        last = Flywheel.stage_order()[-1]
        fw.set_stage_output(last, StageOutput(
            skills_executed=["analytics"],
            output={"conversions": 5, "top_niche": "AI tools"},
        ))
        fw.approve_stage(last)

        assert fw.iteration == 2
        assert fw.current_stage == "research"

    def test_get_stage_context(self) -> None:
        fw = Flywheel.create(niche="AI Tools")
        fw.set_stage_output("research", StageOutput(
            skills_executed=["trending-content-scout"],
            output={"program": "HeyGen"},
        ))
        fw.approve_stage("research")

        ctx = fw.get_stage_context("content")
        assert "niche" in ctx
        assert "previous_stages" in ctx
        assert "research" in ctx["previous_stages"]
        assert ctx["previous_stages"]["research"]["output"] == {"program": "HeyGen"}

    def test_empty_context_first_stage(self) -> None:
        fw = Flywheel.create(niche="Test")
        ctx = fw.get_stage_context("research")
        assert ctx["previous_stages"] == {}

    def test_completed_stages(self) -> None:
        fw = Flywheel.create(niche="Test")
        assert fw.completed_stages == []
        fw.set_stage_output("research", StageOutput())
        fw.approve_stage("research")
        assert fw.completed_stages == ["research"]


class TestQueueManager:
    def test_create_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            qm = QueueManager(tmpdir)
            fw = qm.create_flywheel(niche="Test Niche", platforms=["tiktok"])
            assert fw.niche_slug == "test-niche"

            loaded = qm.get_flywheel("test-niche")
            assert loaded is not None
            assert loaded.flywheel_id == fw.flywheel_id
            assert loaded.niche == "Test Niche"

    def test_list_flywheels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            qm = QueueManager(tmpdir)
            assert qm.list_flywheels() == []

            qm.create_flywheel(niche="AI Tools")
            qm.create_flywheel(niche="Health Wellness")
            flywheels = qm.list_flywheels()
            assert len(flywheels) == 2
            assert "ai-tools" in flywheels
            assert "health-wellness" in flywheels

    def test_delete_flywheel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            qm = QueueManager(tmpdir)
            fw = qm.create_flywheel(niche="Test")
            assert qm.delete_flywheel("test")
            assert qm.get_flywheel("test") is None
            assert qm.delete_flywheel("nonexistent") is False

    def test_load_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            qm = QueueManager(tmpdir)
            qm.create_flywheel(niche="Niche 1")
            qm.create_flywheel(niche="Niche 2")
            qm.create_flywheel(niche="Niche 3")

            all_fw = qm.load_all()
            assert len(all_fw) == 3
            niches = {fw.niche for fw in all_fw}
            assert niches == {"Niche 1", "Niche 2", "Niche 3"}

    def test_save_preserves_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            qm = QueueManager(tmpdir)
            fw = qm.create_flywheel(niche="Test")

            output = StageOutput(
                skills_executed=["skill-a", "skill-b"],
                output={"result": "ok"},
                deepseek_usage={"tokens_total": 500, "calls": 2},
            )
            fw.set_stage_output("research", output)
            fw.approve_stage("research")
            qm.save_flywheel(fw)

            loaded = qm.get_flywheel("test")
            assert loaded is not None
            assert loaded.completed_stages == ["research"]
            assert loaded.stages["research"].output == {"result": "ok"}
            assert loaded.current_stage == "content"
