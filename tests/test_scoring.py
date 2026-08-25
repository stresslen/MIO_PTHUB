import json

import pytest

from app.config import settings
from app.models.scoring_rule import ScoreResult
from app.pipeline.extract import AIAuthenticationError, AIQuotaOrAPIError
from app.pipeline.scoring import AIScoringEngine


def _evaluate(engine: AIScoringEngine):
    return engine.evaluate(
        title="Gói thầu số hóa hồ sơ",
        need_summary="Xây dựng hệ thống OCR",
        need_categories=["OCR / Số hóa tài liệu"],
        budget_value=3_000_000_000.0,
        location="Hà Nội",
        contact_email=None,
        contact_phone=None,
        deadline=None,
        published_at=None,
        relevance=0.9,
    )


def test_scoring_returns_only_gemini_result(monkeypatch):
    engine = AIScoringEngine()
    expected = ScoreResult(
        total_score=85,
        recommended_action="EMAIL",
        reasons=["AI đánh giá"],
        evaluated_by="ai_test",
    )
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(engine, "_evaluate_with_gemini", lambda **kwargs: expected)

    assert _evaluate(engine) is expected


def test_malformed_gemini_json_is_not_rule_scored(monkeypatch):
    engine = AIScoringEngine()
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    def malformed(**kwargs):
        raise json.JSONDecodeError("Unterminated string", '"broken', 0)

    monkeypatch.setattr(engine, "_evaluate_with_gemini", malformed)

    with pytest.raises(AIQuotaOrAPIError, match="không hợp lệ"):
        _evaluate(engine)
    assert not hasattr(engine, "_evaluate_rule_based")


def test_missing_gemini_key_stops_scoring(monkeypatch):
    engine = AIScoringEngine()
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", None)

    with pytest.raises(AIAuthenticationError, match="GEMINI_API_KEY"):
        _evaluate(engine)


def test_ai_response_controls_score_and_action():
    engine = AIScoringEngine()
    result = engine._parse_ai_response({
        "total_score": 95,
        "recommended_action": "NURTURE",
        "score_reasons": ["+25 Nhu cầu rõ ràng"],
        "breakdown": [
            {"rule_name": "demand", "points": 25, "reason": "Nhu cầu rõ ràng"}
        ],
        "sales_strategy_suggestion": "Liên hệ trực tiếp",
    })

    assert result.total_score == 95
    assert result.recommended_action == "NURTURE"
    assert result.evaluated_by.startswith("ai_")


def test_invalid_gemini_action_is_rejected():
    engine = AIScoringEngine()
    with pytest.raises(ValueError, match="recommended_action"):
        engine._parse_ai_response({
            "total_score": 85,
            "recommended_action": "VISIT",
            "score_reasons": ["Có nhu cầu"],
            "sales_strategy_suggestion": "Liên hệ.",
        })


def test_non_gemini_provider_is_rejected(monkeypatch):
    engine = AIScoringEngine()
    monkeypatch.setattr(settings, "ai_provider", "openai")
    with pytest.raises(AIAuthenticationError, match="chỉ hỗ trợ AI_PROVIDER=gemini"):
        _evaluate(engine)
