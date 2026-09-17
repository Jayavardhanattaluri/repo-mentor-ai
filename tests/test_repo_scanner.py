from pathlib import Path
from unittest.mock import MagicMock

from app.repo_scanner import RepositoryScanner, build_context_for_issue


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