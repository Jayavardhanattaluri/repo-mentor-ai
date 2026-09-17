from unittest.mock import MagicMock, patch

from app.github_client import GitHubClient


def test_pull_requests_are_excluded():
    """Pull requests should be filtered out from issues list."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"number": 1, "title": "Real issue"},
        {"number": 2, "title": "PR", "pull_request": {}},
        {"number": 3, "title": "Another issue"},
    ]
    mock_response.raise_for_status.return_value = None

    with patch("httpx.Client.get", return_value=mock_response):
        client = GitHubClient()
        issues = client.list_issues()

    assert len(issues) == 2
    assert issues[0]["number"] == 1
    assert issues[1]["number"] == 3


def test_issue_score_model():
    """Test IssueScore model validation."""
    from app.models import IssueScore

    score = IssueScore(issue_number=123, score=5, reasons=["good first issue", "unassigned"])
    assert score.issue_number == 123
    assert score.score == 5
    assert len(score.reasons) == 2


def test_test_result_model():
    """Test TestResult model validation."""
    from app.models import TestResult

    result = TestResult(
        command=["git", "diff", "--check"],
        exit_code=0,
        stdout="",
        stderr="",
        passed=True,
    )
    assert result.passed is True
    assert result.exit_code == 0