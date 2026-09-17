import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass
class TestResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    passed: bool
    duration: float


class TestRunner:
    """Run tests and linting with an allowlist of safe commands."""
    
    # Zulip-specific test commands (from Zulip's testing documentation)
    ALLOWED_COMMANDS: ClassVar[dict[str, list[str]]] = {
        "lint": ["tools/lint", "--skip-provision-check", "--only=ruff,ruff-format"],
        "lint-python": ["tools/lint", "--skip-provision-check", "--only=ruff"],
        "lint-js": ["tools/lint", "--skip-provision-check", "--only=eslint"],
        "typecheck": ["tools/run-mypy", "--skip-provision-check"],
        "test-backend": ["./tools/test-backend", "--skip-provision-check"],
        "test-js-node": ["./tools/test-js-with-node", "--skip-provision-check"],
        "test-js-web": ["./tools/test-js-with-casper", "--skip-provision-check"],
        "test-all": ["./tools/test-all", "--skip-provision-check"],
        "migrations": ["./manage.py", "makemigrations", "--check", "--dry-run"],
    }
    
    # Generic fallback commands if not in Zulip repo
    GENERIC_COMMANDS: ClassVar[dict[str, list[str]]] = {
        "ruff": ["ruff", "check"],
        "ruff-format": ["ruff", "format", "--check"],
        "mypy": ["mypy"],
        "pytest": ["pytest", "-x", "-v"],
    }

    def __init__(self, repo_path: Path, timeout: int = 600):
        self.repo_path = repo_path
        self.timeout = timeout
        self._detect_repo_type()

    def _detect_repo_type(self):
        """Detect if this is a Zulip repo or generic Python project."""
        self.is_zulip = (self.repo_path / "tools" / "lint").exists()
        self.is_python = (self.repo_path / "pyproject.toml").exists() or \
                         (self.repo_path / "requirements.txt").exists()

    def get_allowed_commands(self) -> dict[str, list[str]]:
        """Get available test commands for this repo."""
        if self.is_zulip:
            return self.ALLOWED_COMMANDS
        return self.GENERIC_COMMANDS

    def run_command(self, command: list[str], cwd: Path | None = None) -> TestResult:
        """Run a command and return result."""
        import time
        work_dir = cwd or self.repo_path
        start = time.time()
        
        try:
            result = subprocess.run(
                command,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            duration = time.time() - start
            return TestResult(
                command=command,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                passed=result.returncode == 0,
                duration=duration,
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {self.timeout}s",
                passed=False,
                duration=self.timeout,
            )
        except OSError as e:
            return TestResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                passed=False,
                duration=time.time() - start,
            )

    def run_lint(self, cwd: Path | None = None) -> TestResult:
        """Run linting."""
        if self.is_zulip:
            return self.run_command(self.ALLOWED_COMMANDS["lint"], cwd)
        elif "ruff" in self.GENERIC_COMMANDS:
            return self.run_command(self.GENERIC_COMMANDS["ruff"], cwd)
        return TestResult(
            command=[], exit_code=-1, stdout="", stderr="No linter available", passed=False, duration=0
        )

    def run_typecheck(self, cwd: Path | None = None) -> TestResult:
        """Run type checking."""
        if self.is_zulip:
            return self.run_command(self.ALLOWED_COMMANDS["typecheck"], cwd)
        elif "mypy" in self.GENERIC_COMMANDS:
            return self.run_command(self.GENERIC_COMMANDS["mypy"], cwd)
        return TestResult(
            command=[], exit_code=-1, stdout="", stderr="No type checker available", passed=False, duration=0
        )

    def run_tests(self, test_path: str | None = None, cwd: Path | None = None) -> TestResult:
        """Run tests, optionally targeting a specific file/module."""
        if self.is_zulip and test_path:
            # Try to run specific backend test
            return self.run_command(
                ["./tools/test-backend", "--skip-provision-check", test_path],
                cwd
            )
        elif self.is_zulip:
            return self.run_command(self.ALLOWED_COMMANDS["test-backend"], cwd)
        elif "pytest" in self.GENERIC_COMMANDS:
            cmd = self.GENERIC_COMMANDS["pytest"][:]
            if test_path:
                cmd.append(test_path)
            return self.run_command(cmd, cwd)
        return TestResult(
            command=[], exit_code=-1, stdout="", stderr="No test runner available", passed=False, duration=0
        )

    def run_git_diff_check(self, cwd: Path | None = None) -> TestResult:
        """Run git diff --check for whitespace errors."""
        return self.run_command(["git", "diff", "--check"], cwd or self.repo_path)

    def run_relevant_tests(self, changed_files: list[str], cwd: Path | None = None) -> list[TestResult]:
        """Run tests relevant to changed files."""
        results = []
        
        # Always run git diff check
        results.append(self.run_git_diff_check(cwd))
        
        # Run lint on changed Python files
        py_files = [f for f in changed_files if f.endswith(".py")]
        if py_files:
            if self.is_zulip:
                # Run lint on specific files
                for f in py_files:
                    results.append(self.run_command(
                        ["tools/lint", "--skip-provision-check", "--only=ruff", f], cwd
                    ))
            elif "ruff" in self.GENERIC_COMMANDS:
                results.append(self.run_command(["ruff", "check", *py_files], cwd))
        
        # Run typecheck if Python files changed
        if py_files and (self.is_zulip or "mypy" in self.GENERIC_COMMANDS):
            results.append(self.run_typecheck(cwd))
        
        # Run tests for test files
        test_files = [f for f in changed_files if "test" in f and f.endswith(".py")]
        if test_files:
            for f in test_files:
                results.append(self.run_tests(f, cwd))
        
        return results

    def format_result(self, result: TestResult) -> str:
        """Format a test result for display."""
        status = "✓ PASS" if result.passed else "✗ FAIL"
        lines = [
            f"{status} {' '.join(result.command)} ({result.duration:.1f}s)",
            f"  Exit code: {result.exit_code}",
        ]
        if result.stdout:
            lines.append(f"  STDOUT:\n{result.stdout[:2000]}")
        if result.stderr:
            lines.append(f"  STDERR:\n{result.stderr[:2000]}")
        return "\n".join(lines)