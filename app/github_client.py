import httpx

from app.config import GITHUB_TOKEN

BASE_URL = "https://api.github.com"
REPOSITORY = "zulip/zulip"


class GitHubClient:
    def __init__(self):
        self.client = httpx.Client(
            base_url=BASE_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )

    def list_issues(self, labels: str | None = None) -> list[dict]:
        params = {
            "state": "open",
            "per_page": 30,
            "sort": "updated",
            "direction": "desc",
        }

        if labels:
            params["labels"] = labels

        response = self.client.get(
            f"/repos/{REPOSITORY}/issues",
            params=params,
        )
        response.raise_for_status()

        return [
            item for item in response.json()
            if "pull_request" not in item
        ]

    def get_issue(self, number: int) -> dict:
        response = self.client.get(
            f"/repos/{REPOSITORY}/issues/{number}",
        )
        response.raise_for_status()
        return response.json()

    def get_comments(self, number: int) -> list[dict]:
        response = self.client.get(
            f"/repos/{REPOSITORY}/issues/{number}/comments",
        )
        response.raise_for_status()
        return response.json()