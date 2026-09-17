import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PatchResult:
    success: bool
    message: str
    stdout: str = ""
    stderr: str = ""


class PatchManager:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.worktree_base = repo_path / ".worktrees"
        self.worktree_base.mkdir(exist_ok=True)

    def create_worktree(self, issue_number: int, base_branch: str = "main") -> tuple[Path, str]:
        """Create an isolated worktree for the issue."""
        branch_name = f"issue-{issue_number}-auto"
        worktree_path = self.worktree_base / branch_name
        
        # Remove existing worktree if it exists
        if worktree_path.exists():
            self.remove_worktree(issue_number)
        
        # Create worktree
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path), base_branch],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")
        
        return worktree_path, branch_name

    def remove_worktree(self, issue_number: int) -> PatchResult:
        """Remove the worktree for an issue."""
        branch_name = f"issue-{issue_number}-auto"
        worktree_path = self.worktree_base / branch_name
        
        if not worktree_path.exists():
            return PatchResult(True, "Worktree does not exist")
        
        # Remove worktree
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        
        if result.returncode != 0:
            return PatchResult(False, f"Failed to remove worktree: {result.stderr}")
        
        # Delete branch
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        
        return PatchResult(True, "Worktree removed")

    def validate_patch(self, worktree_path: Path, patch_path: Path) -> PatchResult:
        """Validate a patch can be applied cleanly."""
        result = subprocess.run(
            ["git", "apply", "--check", str(patch_path)],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        
        if result.returncode == 0:
            return PatchResult(True, "Patch validates successfully", result.stdout, result.stderr)
        else:
            return PatchResult(False, f"Patch validation failed: {result.stderr}", result.stdout, result.stderr)

    def apply_patch(self, worktree_path: Path, patch_path: Path) -> PatchResult:
        """Apply a validated patch."""
        result = subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        
        if result.returncode == 0:
            return PatchResult(True, "Patch applied successfully", result.stdout, result.stderr)
        else:
            return PatchResult(False, f"Patch application failed: {result.stderr}", result.stdout, result.stderr)

    def show_diff(self, worktree_path: Path) -> str:
        """Show the diff of changes in the worktree."""
        result = subprocess.run(
            ["git", "diff"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout

    def show_diff_stat(self, worktree_path: Path) -> str:
        """Show diff statistics."""
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout

    def get_changed_files(self, worktree_path: Path) -> list[str]:
        """Get list of changed files."""
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            return result.stdout.strip().split("\n")
        return []

    def reset_worktree(self, worktree_path: Path) -> PatchResult:
        """Reset worktree to clean state."""
        result = subprocess.run(
            ["git", "checkout", ".", "--"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return PatchResult(True, "Worktree reset")
        return PatchResult(False, f"Reset failed: {result.stderr}")

    def commit_changes(self, worktree_path: Path, message: str) -> PatchResult:
        """Commit changes in the worktree."""
        # Stage all changes
        result = subprocess.run(
            ["git", "add", "-A"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return PatchResult(False, f"Git add failed: {result.stderr}")
        
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return PatchResult(True, "Changes committed")
        return PatchResult(False, f"Commit failed: {result.stderr}")