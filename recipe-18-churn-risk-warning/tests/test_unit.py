from agent import load_fixtures, scan_churn_risk


def test_load_fixtures_merges():
    accounts = load_fixtures()
    assert len(accounts) == 3
    assert accounts[0]["intercom"]["sentiment_score"] is not None


def test_scan_churn_risk_dry_run():
    result = scan_churn_risk(dry_run=True)
    assert result.dry_run is True
    assert result.accounts_scored == 3
    assert result.high_risk >= 1


def test_scan_churn_risk_llm_mock(monkeypatch):
    monkeypatch.setenv("MAIL_DRY_RUN", "1")
    monkeypatch.setenv("SLACK_DRY_RUN", "1")

    class FakeLLM:
        def complete_json(self, system, user):
            return {
                "accounts": [
                    {
                        "customer_id": "cus_globex",
                        "customer_name": "Globex",
                        "risk_score": 91,
                        "risk_level": "high",
                        "signals": ["past_due", "negative sentiment"],
                        "recommended_action": "Executive outreach today",
                    }
                ],
                "summary": "One account needs immediate attention.",
            }

    result = scan_churn_risk(llm=FakeLLM())
    assert result.high_risk == 1
    assert result.dry_run is False
