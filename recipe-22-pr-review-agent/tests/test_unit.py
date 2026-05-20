import json

from agent import review_pr
from lib.config import sample_pr_path


def test_review_pr_dry_run():
    payload = json.loads(sample_pr_path().read_text(encoding="utf-8"))
    result = review_pr(payload, dry_run=True)
    assert result.dry_run is True
    assert result.pr_number == 42
    assert "InstaVM PR Review" in result.review_markdown
