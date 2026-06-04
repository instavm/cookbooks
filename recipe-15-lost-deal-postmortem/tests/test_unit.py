from agent import analyze_transcript


def test_analyze_transcript_dry_run():
    result = analyze_transcript("We lost on price and timing.", deal_name="Acme", dry_run=True)
    assert result.dry_run is True
    assert result.postmortem["deal_name"] == "Acme"
    assert "Dry run" in result.postmortem["loss_reason"]


def test_analyze_transcript_llm_mock(monkeypatch):
    class FakeLLM:
        def complete_json(self, system, user):
            return {
                "deal_name": "Acme",
                "loss_reason": "Budget",
                "competitor": "RivalCo",
                "objections": ["price"],
                "what_went_well": ["discovery"],
                "what_to_improve": ["ROI case"],
                "recommended_actions": ["send ROI deck"],
                "confidence": 0.82,
            }

    result = analyze_transcript("Buyer cited budget.", deal_name="Acme", llm=FakeLLM())
    assert result.postmortem["loss_reason"] == "Budget"
    assert result.postmortem["confidence"] == 0.82
