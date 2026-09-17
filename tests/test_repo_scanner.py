from pathlib import Path
from unittest.mock import MagicMock, patch

from app.repo_scanner import RepositoryScanner, build_context_for_issue


def _mock_grep(mapping: dict[str, str]):
    """Return a subprocess.run replacement serving canned git grep output."""
    def _run(cmd, **kwargs):
        term = cmd[-1]
        result = MagicMock()
        result.stdout = mapping.get(term, "")
        result.stderr = ""
        result.returncode = 0
        return result
    return _run


def test_find_relevant_files_ranks_by_keyword_hits():
    """Files matching more keywords rank first."""
    scanner = RepositoryScanner(Path("/tmp"))
    mapping = {
        "wildcard": "zerver/lib/permissions.py\nweb/src/compose.js\n",
        "mention": "zerver/lib/permissions.py\n",
    }
    with patch("app.repo_scanner.subprocess.run", side_effect=_mock_grep(mapping)):
        files = scanner.find_relevant_files(["wildcard", "mention"])

    assert files[0] == "zerver/lib/permissions.py"
    assert "web/src/compose.js" in files


def test_find_relevant_files_excludes_metadata_dirs():
    """Dot-directories and .github never surface as relevant files."""
    scanner = RepositoryScanner(Path("/tmp"))
    mapping = {
        "wildcard": ".claude/rules/x.md\n.github/workflows/ci.yml\nzerver/models/streams.py\n",
    }
    with patch("app.repo_scanner.subprocess.run", side_effect=_mock_grep(mapping)):
        files = scanner.find_relevant_files(["wildcard"])

    assert ".claude/rules/x.md" not in files
    assert ".github/workflows/ci.yml" not in files
    assert files == ["zerver/models/streams.py"]


def test_find_relevant_files_ignores_short_terms():
    """Terms of length <= 3 are not searched (they match substrings everywhere)."""
    scanner = RepositoryScanner(Path("/tmp"))
    with patch("app.repo_scanner.subprocess.run") as mock_run:
        files = scanner.find_relevant_files(["per", "an", "the"])

    mock_run.assert_not_called()
    assert files == []


def test_find_relevant_files_weights_rare_terms_higher():
    """A file matching a rare term outranks one matching only a common term."""
    scanner = RepositoryScanner(Path("/tmp"))
    mapping = {
        "wildcard": "zerver/models/streams.py\n",
        "description": "docs/a.md\ndocs/b.md\ndocs/c.md\ndocs/d.md\n",
    }
    with patch("app.repo_scanner.subprocess.run", side_effect=_mock_grep(mapping)):
        files = scanner.find_relevant_files(["wildcard", "description"])

    assert files[0] == "zerver/models/streams.py"


def test_find_relevant_files_deprioritizes_locale_catalogs():
    """Generated translation catalogs sort after real files on equal scores."""
    scanner = RepositoryScanner(Path("/tmp"))
    mapping = {
        "mention": "locale/fr/translations.json\nweb/src/compose.js\n",
    }
    with patch("app.repo_scanner.subprocess.run", side_effect=_mock_grep(mapping)):
        files = scanner.find_relevant_files(["mention"])

    assert files.index("web/src/compose.js") < files.index("locale/fr/translations.json")


def test_find_relevant_files_prefers_source_over_tests():
    """On equal hit counts, source files come before test files."""
    scanner = RepositoryScanner(Path("/tmp"))
    mapping = {
        "wildcard": "zerver/lib/permissions.py\nzerver/tests/test_perms.py\n",
    }
    with patch("app.repo_scanner.subprocess.run", side_effect=_mock_grep(mapping)):
        files = scanner.find_relevant_files(["wildcard"])

    assert files.index("zerver/lib/permissions.py") < files.index("zerver/tests/test_perms.py")


def test_extract_keywords():
    """Test keyword extraction from issue text."""
    scanner = RepositoryScanner(Path("/tmp"))
    
    keywords = scanner.extract_keywords(
        "Fix typo in documentation",
        "There is a typo in the README file that needs fixing."
    )
    
    assert "typo" in keywords
    assert "documentation" in keywords
    assert "readme" in keywords
    assert "fixing" in keywords
    # Stopwords should be filtered
    assert "the" not in keywords
    assert "in" not in keywords
    assert "a" not in keywords


def test_extract_keywords_filters_stopwords():
    """Test that common stopwords are filtered out."""
    scanner = RepositoryScanner(Path("/tmp"))
    
    keywords = scanner.extract_keywords(
        "The issue is about the thing",
        "This and that are not important"
    )
    
    # "issue" is in stopwords list, so it's filtered
    assert "thing" in keywords
    assert "important" in keywords
    assert "about" in keywords  # "about" is not in stopwords
    assert "the" not in keywords
    assert "is" not in keywords
    assert "this" not in keywords
    assert "and" not in keywords
    assert "that" not in keywords
    assert "are" not in keywords
    assert "not" not in keywords


def test_build_context_for_issue_mock():
    """Test build_context_for_issue with mocked scanner."""
    mock_scanner = MagicMock(spec=RepositoryScanner)
    mock_scanner.current_commit.return_value = "abc123"
    mock_scanner.extract_keywords.return_value = ["test", "feature"]
    mock_scanner.find_relevant_files.return_value = ["src/test.py", "tests/test_test.py"]
    mock_scanner.get_file_context.return_value = "def test():\n    pass"
    
    issue = {
        "number": 123,
        "title": "Test issue",
        "body": "Test body",
        "html_url": "https://github.com/zulip/zulip/issues/123",
    }
    
    context = build_context_for_issue(mock_scanner, issue)
    
    assert context["commit"] == "abc123"
    assert context["keywords"] == ["test", "feature"]
    assert context["files"] == ["src/test.py", "tests/test_test.py"]
    assert "src/test.py" in context["file_contents"]
    assert "tests/test_test.py" in context["file_contents"]