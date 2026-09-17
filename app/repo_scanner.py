import re
import subprocess
from pathlib import Path

from app.config import MAX_FILE_CHARS


ISSUE_TERM_MAP = {
    "wildcard mention": [
        "wildcard_mention",
        "realm_can_mention_many_users_group",
        "can_mention_many_users",
        "wildcard_mention_threshold",
        "wildcard_mention_policy",
        "@all",
        "@everyone",
        "@stream",
    ],
    "channel permission": [
        "stream_permission",
        "stream_setting",
        "channel_permission",
        "GroupPermissionSetting",
        "stream_group",
        "do_change_stream_group_based_setting",
    ],
}


class RepositoryScanner:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def current_commit(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def search(self, query: str) -> str:
        result = subprocess.run(
            ["git", "grep", "-n", "-i", query],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout[:MAX_FILE_CHARS]

    def read_file(self, relative_path: str) -> str:
        path = self.repo_path / relative_path

        if not path.exists() or not path.is_file():
            return ""

        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )[:MAX_FILE_CHARS]

    def extract_keywords(self, issue_title: str, issue_body: str) -> list[str]:
        """Extract potential search keywords from issue text."""
        text = (issue_title + " " + issue_body).lower()

        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
            "been", "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "must", "can", "this",
            "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
            "my", "your", "his", "her", "its", "our", "their", "me", "him", "us",
            "them", "what", "which", "who", "whom", "whose", "where", "when", "why",
            "how", "all", "each", "few", "more", "most", "other", "some", "such",
            "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
            "just", "now", "then", "here", "there", "issue", "fix", "add", "remove", "update", "change", "improve", "make",
            "allow", "support", "enable", "disable", "create", "delete", "get", "set",
        }

        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text)
        keywords = [
            w for w in words
            if len(w) > 2 and w not in stopwords and not w.isupper()
        ]

        seen = set()
        unique = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)

        return unique[:10]

    EXCLUDED_PREFIXES = (".", ".github/")

    @staticmethod
    def issue_terms(issue_title: str, issue_body: str) -> list[str]:
        """Return exact repository symbols implied by known issue concepts."""
        text = f"{issue_title} {issue_body}".lower()
        terms: list[str] = []
        for phrase, candidates in ISSUE_TERM_MAP.items():
            if phrase in text:
                terms.extend(candidates)
        return list(dict.fromkeys(terms))

    def find_relevant_files(self, keywords: list[str], max_files: int = 10) -> list[str]:
        """Find relevant files using issue-specific symbols plus issue keywords.

        Exact domain symbols are searched before generic natural-language terms.
        Files are ranked by weighted distinct-term matches, with generated
        catalogs and tests deprioritized on ties.
        """
        terms = [k for k in keywords if len(k) > 3][:8]
        if not terms:
            return []

        matches: dict[str, set[str]] = {}
        for term in terms:
            result = subprocess.run(
                ["git", "grep", "-l", "-i", term],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            files = {
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
                and not line.strip().startswith(self.EXCLUDED_PREFIXES)
            }
            matches[term] = files

        scores: dict[str, float] = {}
        for term, files in matches.items():
            weight = 1.0 / max(len(files), 1)
            for path in files:
                scores[path] = scores.get(path, 0.0) + weight

        def sort_key(path: str) -> tuple:
            is_generated_catalog = path.startswith("locale/")
            is_test = path.startswith("tests/") or path.endswith(
                ("_test.py", ".test.cjs", ".test.js", ".test.ts")
            )
            return (-scores[path], is_generated_catalog, is_test, path)

        return sorted(scores, key=sort_key)[:max_files]

    def find_issue_files(
        self,
        issue_title: str,
        issue_body: str,
        max_files: int = 10,
    ) -> tuple[list[str], list[str]]:
        """Find files using exact domain terms first, then generic keywords."""
        domain_terms = self.issue_terms(issue_title, issue_body)
        keywords = self.extract_keywords(issue_title, issue_body)
        search_terms = list(dict.fromkeys(domain_terms + keywords))
        return search_terms, self.find_relevant_files(search_terms, max_files=max_files)

    def get_file_context(self, file_path: str, max_lines: int = 100) -> str:
        """Read a file and return bounded content."""
        content = self.read_file(file_path)
        lines = content.split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... (truncated, {len(lines)} total lines)"
        return content


def build_context_for_issue(scanner: RepositoryScanner, issue: dict) -> dict:
    """Build repository context for an issue."""
    keywords, files = scanner.find_issue_files(
        issue.get("title", ""), issue.get("body", "")
    )

    file_contents = {}
    for f in files[:5]:
        file_contents[f] = scanner.get_file_context(f)

    return {
        "commit": scanner.current_commit(),
        "keywords": keywords,
        "files": files,
        "file_contents": file_contents,
    }
