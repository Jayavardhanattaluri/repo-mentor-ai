import pytest

from app.patch_validator import (
    PatchValidationError,
    validate_allowed_paths,
    validate_patch_format,
)


VALID_PATCH = """diff --git a/app/example.py b/app/example.py
--- a/app/example.py
+++ b/app/example.py
@@ -1,1 +1,2 @@
 old
+new
"""


def test_validate_patch_format_accepts_valid_diff():
    assert validate_patch_format(VALID_PATCH).startswith("diff --git ")


def test_validate_patch_format_rejects_markdown_fences():
    with pytest.raises(PatchValidationError, match="Markdown fences"):
        validate_patch_format(f"```diff\n{VALID_PATCH}```")


def test_validate_patch_format_rejects_truncated_ellipsis():
    with pytest.raises(PatchValidationError, match="truncated"):
        validate_patch_format(VALID_PATCH + "...\n")


def test_validate_patch_format_rejects_missing_hunk():
    patch = """diff --git a/app/example.py b/app/example.py
--- a/app/example.py
+++ b/app/example.py
"""
    with pytest.raises(PatchValidationError, match="hunk"):
        validate_patch_format(patch)


def test_validate_allowed_paths_rejects_unapproved_file():
    with pytest.raises(PatchValidationError, match="unapproved"):
        validate_allowed_paths(VALID_PATCH, {"app/other.py"})


def test_validate_allowed_paths_accepts_approved_file():
    validate_allowed_paths(VALID_PATCH, {"app/example.py"})
