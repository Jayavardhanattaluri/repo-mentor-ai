def score_issue(issue: dict) -> dict:
    labels = {
        label["name"].lower()
        for label in issue.get("labels", [])
    }

    text = (
        issue.get("title", "") + "\n" +
        issue.get("body", "")
    ).lower()

    score = 0
    reasons = []

    if "good first issue" in labels:
        score += 3
        reasons.append("good first issue")

    if "help wanted" in labels:
        score += 3
        reasons.append("help wanted")

    if not issue.get("assignees"):
        score += 2
        reasons.append("unassigned")

    if any(word in text for word in ["docs", "documentation", "typo"]):
        score += 2
        reasons.append("documentation-oriented")

    if "difficult" in labels:
        score -= 3
        reasons.append("marked difficult")

    if any(
        word in text
        for word in ["security", "authentication", "authorization"]
    ):
        score -= 3
        reasons.append("security-sensitive")

    # Penalize very old issues (stale)
    # Note: would need updated_at parsing for full implementation

    return {
        "issue_number": issue["number"],
        "title": issue["title"],
        "score": score,
        "reasons": reasons,
        "labels": [l["name"] for l in issue.get("labels", [])],
        "assignees": [a["login"] for a in issue.get("assignees", [])],
        "url": issue["html_url"],
    }


def rank_issues(issues: list[dict]) -> list[dict]:
    scored = [score_issue(issue) for issue in issues]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored