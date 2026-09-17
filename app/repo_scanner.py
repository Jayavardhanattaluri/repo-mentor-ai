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

    def find_relevant_files(self, keywords: list[str], max_files: int = 10) -> list[str]:
        """Find files matching keywords using git grep."""
        if not keywords:
            return []
        
        # Build grep pattern - search for any keyword
        pattern = "|".join(keywords[:5])  # Limit to first 5 keywords
        
        result = subprocess.run(
            ["git", "grep", "-l", "-i", "-E", pattern],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []
        
        # Filter out test files for now, prioritize source files
        source_files = [f for f in files if not f.startswith("tests/") and not f.endswith("_test.py")]
        test_files = [f for f in files if f.startswith("tests/") or f.endswith("_test.py")]
        
        # Return source files first, then test files
        return (source_files + test_files)[:max_files]

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