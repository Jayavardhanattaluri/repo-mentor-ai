import re
import subprocess
from pathlib import Path

from app.config import MAX_FILE_CHARS


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
        
        # Remove common words
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
        
        # Extract words (alphanumeric + underscore)
        words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text)
        
        # Filter: length > 2, not stopword, not all caps (likely acronym)
        keywords = [
            w for w in words
            if len(w) > 2 and w not in stopwords and not w.isupper()
        ]
        
        # Deduplicate, preserve order
        seen = set()
        unique = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        
        # Return top 10 keywords
        return unique[:10]

    # Directories that never contain implementation code
    EXCLUDED_PREFIXES = (".", ".github/")

    def find_relevant_files(self, keywords: list[str], max_files: int = 10) -> list[str]:
        """Find files matching keywords using git grep.

        Runs one search per keyword and ranks files by how many distinct
        keywords they match, so files relevant to the whole issue surface
        above files that merely contain a common substring. Short terms
        (e.g. "per") and metadata directories (e.g. ".claude/", ".github/")
        are excluded because they match nearly everything.
        """
        # Drop short terms: they match substrings everywhere ("per" hits
        # "super", "person", "perform", ...) and drown out real signals.
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

        # Weight each term by rarity: a file matching "wildcard" (dozens of
        # hits repo-wide) is far more relevant than one matching only
        # "description" (thousands of hits, mostly docs and locale catalogs).
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
            # Highest score first, generated catalogs last, then source
            # before tests, then name for determinism.
            return (-scores[path], is_generated_catalog, is_test, path)

        return sorted(scores, key=sort_key)[:max_files]

    def get_file_context(self, file_path: str, max_lines: int = 100) -> str:
        """Read a file and return bounded content."""
        content = self.read_file(file_path)
        lines = content.split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... (truncated, {len(lines)} total lines)"
        return content


def build_context_for_issue(scanner: RepositoryScanner, issue: dict) -> dict:
    """Build repository context for an issue."""
    keywords = scanner.extract_keywords(issue.get("title", ""), issue.get("body", ""))
    files = scanner.find_relevant_files(keywords)
    
    file_contents = {}
    for f in files[:5]:  # Limit to 5 files for context
        file_contents[f] = scanner.get_file_context(f)
    
    return {
        "commit": scanner.current_commit(),
        "keywords": keywords,
        "files": files,
        "file_contents": file_contents,
    }