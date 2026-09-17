from app.prompts import build_patch_prompt, parse_plan_files


def test_parse_plan_files_extracts_backticked_paths():
    """Backticked repo paths are extracted from the Files to Modify section."""
    plan_md = (
        "# Implementation Plan\n"
        "## Files to Modify\n"
        "- `zerver/models/streams.py` - Add field\n"
        "- `zerver/views/streams.py` - API\n"
        "\n"
        "## Steps\n"
        "1. Do the thing mentioning `code` inline\n"
    )
    assert parse_plan_files(plan_md) == [
        "zerver/models/streams.py",
        "zerver/views/streams.py",
    ]


def test_parse_plan_files_ignores_prose_and_duplicates():
    """Non-path spans and repeats are skipped."""
    plan_md = (
        "## Files to Modify\n"
        "- `zerver/models/streams.py`\n"
        "- `some prose`\n"
        "- `zerver/models/streams.py`\n"
    )
    assert parse_plan_files(plan_md) == ["zerver/models/streams.py"]


def test_parse_plan_files_empty_without_section():
    """No Files to Modify section means no paths."""
    assert parse_plan_files("# Plan\n## Steps\n1. do stuff\n") == []


def test_parse_plan_files_bare_bullet_paths():
    """Bare paths (no backticks), including '(inferred)' markers, are found."""
    plan_md = (
        "## Files to Modify\n"
        "- zerver/openapi/zulip.yaml\n"
        "- zerver/models/streams.py (inferred)\n"
        "- Add a new field to the model\n"
        "\n"
        "## Steps\n"
        "1. stuff\n"
    )
    assert parse_plan_files(plan_md) == [
        "zerver/openapi/zulip.yaml",
        "zerver/models/streams.py",
    ]


def test_parse_plan_files_mixed_formats():
    """Backticked and bare paths mix, in order, deduplicated."""
    plan_md = (
        "## Files to Modify\n"
        "- `zerver/models/streams.py` - Add field\n"
        "- zerver/views/streams.py (inferred)\n"
        "- `zerver/models/streams.py`\n"
    )
    assert parse_plan_files(plan_md) == [
        "zerver/models/streams.py",
        "zerver/views/streams.py",
    ]


def test_build_patch_prompt_flags_missing_files():
    """Hallucinated plan paths are surfaced so the model avoids them."""
    context = {
        "commit": "abc123",
        "files": [],
        "file_contents": {},
        "plan_files_missing": ["zerver/lib/nope.py"],
    }
    prompt = build_patch_prompt({"title": "T", "number": 1}, "plan", context)
    assert "zerver/lib/nope.py" in prompt
    assert "do not reference these paths" in prompt.lower()


def test_build_patch_prompt_without_missing_files():
    """No missing-files section when everything exists."""
    context = {
        "commit": "abc123",
        "files": ["a.py"],
        "file_contents": {"a.py": "print(1)"},
    }
    prompt = build_patch_prompt({"title": "T", "number": 1}, "plan", context)
    assert "DO NOT EXIST" not in prompt
    assert "--- a.py ---" in prompt