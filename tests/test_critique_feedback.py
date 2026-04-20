"""Tests for dqg.schemas.critique_feedback."""

from dqg.schemas.critique_feedback import CritiqueAction, CritiqueFeedback, CritiqueFeedbackItem


class TestCritiqueFeedbackItem:

    def test_basic_item(self):
        item = CritiqueFeedbackItem(
            target_id="REQ-001",
            action=CritiqueAction.MODIFY,
            reason="描述不完整",
            patch="新的描述",
            confidence=0.9,
        )
        assert item.target_id == "REQ-001"
        assert item.action == "modify"
        assert item.confidence == 0.9

    def test_low_confidence(self):
        item = CritiqueFeedbackItem(
            target_id="GAP-001",
            action=CritiqueAction.ADD,
            reason="可能遗漏",
            confidence=0.3,
        )
        assert item.confidence == 0.3


class TestCritiqueFeedback:

    def _make_feedback(self) -> CritiqueFeedback:
        return CritiqueFeedback(
            phase_id="Q01",
            items=[
                CritiqueFeedbackItem(
                    target_id="REQ-001", action=CritiqueAction.MODIFY,
                    reason="描述不完整", patch="新描述", confidence=0.9,
                    evidence_source="PRD 第3段",
                ),
                CritiqueFeedbackItem(
                    target_id="GAP-002", action=CritiqueAction.ADD,
                    reason="遗漏并发场景", patch="新增 GAP", confidence=0.85,
                ),
                CritiqueFeedbackItem(
                    target_id="REQ-003", action=CritiqueAction.DELETE,
                    reason="可能是误报", confidence=0.3,
                ),
            ],
            summary="REQ-001 描述不完整是最严重的问题",
        )

    def test_actionable_items_filters_low_confidence(self):
        fb = self._make_feedback()
        actionable = fb.actionable_items
        assert len(actionable) == 2  # confidence >= 0.5
        assert all(item.confidence >= 0.5 for item in actionable)

    def test_high_confidence_items(self):
        fb = self._make_feedback()
        high = fb.high_confidence_items
        assert len(high) == 2  # confidence >= 0.8
        assert all(item.confidence >= 0.8 for item in high)

    def test_render_for_worker(self):
        fb = self._make_feedback()
        rendered = fb.render_for_worker()
        assert "Critique 可执行反馈" in rendered
        assert "MODIFY REQ-001" in rendered
        assert "ADD GAP-002" in rendered
        # 低置信度的 REQ-003 不应出现
        assert "DELETE REQ-003" not in rendered
        assert "PRD 第3段" in rendered

    def test_render_empty_feedback(self):
        fb = CritiqueFeedback(phase_id="Q01", items=[])
        rendered = fb.render_for_worker()
        assert "无可执行" in rendered

    def test_model_validate(self):
        data = {
            "phase_id": "Q01",
            "items": [
                {"target_id": "REQ-001", "action": "modify", "reason": "test", "confidence": 0.9},
                {"target_id": "GAP-001", "action": "escalate", "reason": "严重", "confidence": 0.7},
            ],
            "summary": "test summary",
        }
        fb = CritiqueFeedback.model_validate(data)
        assert len(fb.items) == 2
        assert fb.items[0].action == CritiqueAction.MODIFY
        assert fb.items[1].action == CritiqueAction.ESCALATE
