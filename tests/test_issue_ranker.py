from app.issue_ranker import rank_issues, score_issue


def test_score_issue_good_first_issue():
    """Issue with 'good first issue' label gets high score."""
    issue = {
        "number": 1,
        "title": "Fix typo",
        "body": "",
        "labels": [{"name": "good first issue"}, {"name": "help wanted"}],
        "assignees": [],
        "html_url": "https://github.com/zulip/zulip/issues/1",
    }
    result = score_issue(issue)
    assert result["score"] >= 6  # good first issue (3) + help wanted (3)
    assert "good first issue" in result["reasons"]
    assert "help wanted" in result["reasons"]


def test_score_issue_unassigned_bonus():
    """Unassigned issues get bonus points."""
    issue = {
        "number": 2,
        "title": "Add docs",
        "body": "documentation update",
        "labels": [{"name": "help wanted"}],
        "assignees": [],
        "html_url": "https://github.com/zulip/zulip/issues/2",
    }
    result = score_issue(issue)
    assert "unassigned" in result["reasons"]
    assert result["score"] >= 5  # help wanted (3) + unassigned (2)


def test_score_issue_docs_bonus():
    """Documentation-related issues get bonus."""
    issue = {
        "number": 3,
        "title": "Fix typo in README",
        "body": "typo in documentation",
        "labels": [{"name": "help wanted"}],
        "assignees": [{"login": "someone"}],
        "html_url": "https://github.com/zulip/zulip/issues/3",
    }
    result = score_issue(issue)
    assert "documentation-oriented" in result["reasons"]


def test_score_issue_difficult_penalty():
    """Issues marked 'difficult' get penalty."""
    issue = {
        "number": 4,
        "title": "Hard task",
        "body": "",
        "labels": [{"name": "help wanted"}, {"name": "difficult"}],
        "assignees": [],
        "html_url": "https://github.com/zulip/zulip/issues/4",
    }
    result = score_issue(issue)
    assert "marked difficult" in result["reasons"]
    assert result["score"] == 2  # help wanted (3) + unassigned (2) - difficult (3)


def test_score_issue_security_penalty():
    """Security-related issues get penalty."""
    issue = {
        "number": 5,
        "title": "Fix authentication bug",
        "body": "authentication vulnerability",
        "labels": [{"name": "help wanted"}],
        "assignees": [],
        "html_url": "https://github.com/zulip/zulip/issues/5",
    }
    result = score_issue(issue)
    assert "security-sensitive" in result["reasons"]
    assert result["score"] == 2  # help wanted (3) + unassigned (2) - security (3)


def test_rank_issues_sorts_by_score():
    """Rank sorts issues by score descending."""
    issues = [
        {"number": 1, "title": "Low", "body": "", "labels": [{"name": "help wanted"}], "assignees": [{"login": "a"}], "html_url": ""},
        {"number": 2, "title": "High", "body": "", "labels": [{"name": "good first issue"}, {"name": "help wanted"}], "assignees": [], "html_url": ""},
    ]
    ranked = rank_issues(issues)
    assert ranked[0]["issue_number"] == 2
    assert ranked[1]["issue_number"] == 1
    assert ranked[0]["score"] > ranked[1]["score"]