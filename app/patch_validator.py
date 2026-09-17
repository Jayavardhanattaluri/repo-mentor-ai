import re


class PatchValidationError(ValueError):
    """Raised when an LLM response is not a safe unified diff."""


def extract_diff(text: str) -> str:
    """Extract and validate the unified-diff portion of an LLM response."""
    text = text.strip()
    if "```" in text:
        raise PatchValidationError("Patch contains Markdown fences")

    start = text.find("diff --git ")
    if start == -1:
        raise PatchValidationError("No unified diff found")

    patch = text[start:]
    if "\x00" in patch:
        raise PatchValidationError("Patch contains null bytes")
    if re.search(r"^\s*\.\.\.\s*$", patch, re.MULTILINE):
        raise PatchValidationError("Patch appears truncated")

    return patch + "\n"


def changed_paths(patch: str) -> set[str]:
    """Return paths from unified-diff new-file headers."""
    return {
        match.group(1)
        for match in re.finditer(r"^\+\+\+ b/(.+)$", patch, re.MULTILINE)
    }


def validate_patch_format(text: str) -> str:
    """Validate basic unified-diff structure and return normalized text."""
    patch = extract_diff(text)
    if not re.search(r"^diff --git a/.+ b/.+$", patch, re.MULTILINE):
        raise PatchValidationError("Missing git diff header")
    if not re.search(r"^--- a/.+$", patch, re.MULTILINE):
        raise PatchValidationError("Missing old-file header")
    if not re.search(r"^\+\+\+ b/.+$", patch, re.MULTILINE):
        raise PatchValidationError("Missing new-file header")
    if not re.search(r"^@@ .+ @@", patch, re.MULTILINE):
        raise PatchValidationError("Missing hunk header")

    # A unified diff must have at least one actual added or removed line.
    if not re.search(r"^[+-](?!\+\+\+|---)", patch, re.MULTILINE):
        raise PatchValidationError("Patch contains no additions or deletions")

    return patch


def validate_allowed_paths(patch: str, allowed: set[str]) -> None:
    """Reject patches that modify paths outside the approved file set."""
    actual = changed_paths(patch)
    unexpected = actual - allowed
    if unexpected:
        raise PatchValidationError(
            f"Patch changes unapproved files: {sorted(unexpected)}"
        )
