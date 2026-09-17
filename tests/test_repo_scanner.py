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


def test_issue_terms_add_domain_symbols():
    scanner = RepositoryScanner(Path("/tmp"))
    terms = scanner.issue_terms(
        "Make wildcard mention permissions configurable per-channel", ""
    )
    assert "realm_can_mention_many_users_group" in terms
    assert "can_mention_many_users" in terms
    assert "GroupPermissionSetting" in terms
    assert "do_change_stream_group_based_setting" in terms


def test_find_relevant_files_ranks_by_keyword_hits():
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
    scanner = RepositoryScanner(Path("/tmp"))
    with patch("app.repo_scanner.subprocess.run") as mock_run:
        files = scanner.find_relevant_files(["per", "an", "the"])

    mock_run.assert_not_called()
    assert files == []


def test_find_relevant_files_weights_rare_terms_higher():
    scanner = RepositoryScanner(Path("/tmp"))
    mapping = {
        "wildcard": "zerver/models/streams.py\n",
        "description": "docs/a.md\ndocs/b.md\ndocs/c.md\ndocs/d.md\n",
    }
    with patch("app.repo_scanner.subprocess.run", side_effect=_mock_grep(mapping)):
        files = scanner.find_relevant_files(["wildcard", "description"])

    assert files[0] == "zerver/models/streams.py"


def test_find_relevant_files_deprioritizes_locale_catalogs():
    scanner = RepositoryScanner(Path("/tmp"))
    mapping = {
        "mention": "locale/fr/translations.json\nweb/src/compose.js\n",
    }
    with patch("app.repo_scanner.subprocess.run", side_effect=_mock_grep(mapping)):
        files = scanner.find_relevant_files(["mention"])

    assert files.index("web/src/compose.js") < files.index("locale/fr/translations.json")


def test_find_relevant_files_prefers_source_over_tests():
    scanner = RepositoryScanner(Path("/tmp"))
    mapping = {
        "wildcard": "zerver/lib/permissions.py\nzerver/tests/test_perms.py\n",
    }
    with patch("app.repo_scanner.subprocess.run", side_effect=_mock_grep(mapping)):
        files = scanner.find_relevant_files(["wildcard"])

    assert files.index("zerver/lib/permissions.py") < files.index("zerver/tests/test_perms.py")


def test_extract_keywords():
    scanner = RepositoryScanner(Path("/tmp"))
    keywords = scanner.extract_keywords(
        "Fix typo in documentation",
        "There is a typo in the README file that needs fixing."
    )
    assert "typo" in keywords
    assert "documentation" in keywords
    assert "readme" in keywords
    assert "fixing" in keywords
    assert "the" not in keywords
    assert "in" not in keywords
    assert "a" not in keywords


def test_extract_keywords_filters_stopwords():
    scanner = RepositoryScanner(Path("/tmp"))
    keywords = scanner.extract_keywords(
        "The issue is about the thing",
        "This and that are not important"
    )
    assert "thing" in keywords
    assert "important" in keywords
    assert "about" in keywords
    assert "the" not in keywords
    assert "is" not in keywords
    assert "this" not in keywords
    assert "and" not in keywords
    assert "that" not in keywords
    assert "are" not in keywords
    assert "not" not in keywords


def test_build_context_for_issue_uses_domain_terms():
    scanner = MagicMock(spec=RepositoryScanner)
    scanner.current_commit.return_value = "abc123"
    scanner.find_issue_files.return_value = (
        ["realm_can_mention_many_users_group"],
        ["web/src/compose_validate.ts"],
    )
    scanner.get_file_context.return_value = "const permission = true;"

    issue = {
        "number": 38384,
        "title": "Make wildcard mention permissions configurable per-channel",
        "body": "",
    }

    context = build_context_for_issue(scanner, issue)

    scanner.find_issue_files.assert_called_once_with(issue["title"], issue["body"])
    assert context["commit"] == "abc123"
    assert context["keywords"] == ["realm_can_mention_many_users_group"]
    assert context["files"] == ["web/src/compose_validate.ts"]
    assert "web/src/compose_validate.ts" in context["file_contents"]
