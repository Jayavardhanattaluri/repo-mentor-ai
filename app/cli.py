import json
import subprocess
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table

from app.config import ZULIP_REPO_PATH
from app.github_client import GitHubClient
from app.issue_ranker import rank_issues
from app.llm_client import LLMClient
from app.patch_manager import PatchManager
from app.prompts import (
    INVESTIGATION_PROMPT,
    PATCH_PROMPT,
    PLAN_PROMPT,
    PROPOSAL_PROMPT,
    build_investigation_prompt,
    build_patch_prompt,
    build_plan_prompt,
    build_proposal_prompt,
)
from app.repo_scanner import RepositoryScanner, build_context_for_issue
from app.test_runner import TestRunner

app = typer.Typer()
console = Console()


@app.command()
def fetch_issues(
    label: str = typer.Option(
        "help wanted",
        help="GitHub label to filter by.",
    ),
):
    """Fetch open issues from Zulip repository."""
    client = GitHubClient()
    try:
        issues = client.list_issues(labels=label)
        console.print(f"[green]Fetched {len(issues)} issues[/green]")
        for issue in issues:
            labels = ", ".join(l["name"] for l in issue.get("labels", []))
            console.print(f"  #{issue['number']}: {issue['title']} [{labels}]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]GitHub API error: {e.response.status_code}[/red]")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="rank-issues")
def rank_issues_cmd(
    label: str = typer.Option(
        "help wanted",
        help="GitHub label to filter by.",
    ),
    limit: int = typer.Option(
        30,
        help="Number of issues to fetch and rank.",
    ),
):
    """Fetch and rank issues by beginner-friendliness."""
    client = GitHubClient()
    try:
        issues = client.list_issues(labels=label)
        if limit:
            issues = issues[:limit]
        ranked = rank_issues(issues)

        table = Table(title=f"Top {len(ranked)} Issues (ranked)")
        table.add_column("Rank", justify="right", style="cyan")
        table.add_column("Score", justify="right", style="green")
        table.add_column("Issue", style="white")
        table.add_column("Labels", style="dim")
        table.add_column("Reasons", style="yellow")

        for i, issue in enumerate(ranked, 1):
            labels_str = ", ".join(issue["labels"])
            reasons_str = ", ".join(issue["reasons"]) if issue["reasons"] else "—"
            table.add_row(
                str(i),
                str(issue["score"]),
                f"#{issue['issue_number']}: {issue['title'][:60]}",
                labels_str,
                reasons_str,
            )

        console.print(table)

    except httpx.HTTPStatusError as e:
        console.print(f"[red]GitHub API error: {e.response.status_code}[/red]")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def analyze(
    issue_number: int,
    save: bool = typer.Option(
        True,
        help="Save analysis to outputs/issue-<number>/",
    ),
    use_llm: bool = typer.Option(
        True,
        help="Use LLM for analysis (requires NVIDIA_API_KEY)",
    ),
):
    """Analyze an issue: find relevant files and generate LLM investigation."""
    client = GitHubClient()
    try:
        # Fetch issue details
        issue = client.get_issue(issue_number)
        
        console.print(f"[green]Analyzing issue #{issue_number}: {issue['title']}[/green]")
        
        # Initialize repo scanner
        if not ZULIP_REPO_PATH.exists():
            console.print(f"[red]Zulip repo not found at {ZULIP_REPO_PATH}[/red]")
            console.print("[yellow]Set ZULIP_REPO_PATH in .env[/yellow]")
            raise typer.Exit(1)
        
        scanner = RepositoryScanner(ZULIP_REPO_PATH)
        
        # Build context
        context = build_context_for_issue(scanner, issue)
        
        # Display results
        console.print(f"\n[cyan]Repository commit:[/cyan] {context['commit'][:12]}")
        console.print(f"[cyan]Keywords:[/cyan] {', '.join(context['keywords'])}")
        console.print(f"\n[cyan]Relevant files ({len(context['files'])} found):[/cyan]")
        
        for i, f in enumerate(context['files'][:10], 1):
            console.print(f"  {i}. {f}")
        
        # LLM Investigation
        investigation_md = ""
        if use_llm:
            console.print("\n[cyan]Generating LLM investigation...[/cyan]")
            llm = LLMClient()
            user_prompt = build_investigation_prompt(issue, context)
            investigation_md = llm.complete(INVESTIGATION_PROMPT, user_prompt)
            console.print(Markdown(investigation_md))
        
        # Save to file
        if save:
            output_dir = Path("outputs") / f"issue-{issue_number}"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save metadata
            metadata = {
                "repository": "zulip/zulip",
                "issue_number": issue_number,
                "repository_commit": context['commit'],
                "issue_title": issue['title'],
                "issue_url": issue['html_url'],
                "keywords": context['keywords'],
                "files_found": context['files'],
            }
            (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
            
            # Save investigation markdown
            if use_llm and investigation_md:
                (output_dir / "01-investigation.md").write_text(investigation_md)
            else:
                # Fallback to basic markdown
                md = f"""# Issue Investigation

## Issue Identity
- Repository: zulip/zulip
- Issue number: {issue_number}
- Commit analyzed: {context['commit']}
- Issue URL: {issue['html_url']}

## Keywords Extracted
{', '.join(context['keywords'])}

## Relevant Files
"""
                for i, f in enumerate(context['files'], 1):
                    md += f"{i}. `{f}`\n"
                
                md += "\n## File Contents\n"
                for f, content in context['file_contents'].items():
                    md += f"\n### `{f}`\n```python\n{content}\n```\n"
                
                (output_dir / "01-investigation.md").write_text(md)
            
            console.print(f"\n[green]Analysis saved to {output_dir}/[/green]")
        
    except httpx.HTTPStatusError as e:
        console.print(f"[red]GitHub API error: {e.response.status_code}[/red]")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Git error: {e.stderr}[/red]")
        raise typer.Exit(1)


def _load_context_and_investigation(issue_number: int) -> tuple[dict, str]:
    """Load saved context and investigation for an issue."""
    output_dir = Path("outputs") / f"issue-{issue_number}"
    
    # Load metadata
    metadata_path = output_dir / "metadata.json"
    if not metadata_path.exists():
        console.print(f"[red]No analysis found for issue {issue_number}. Run 'analyze' first.[/red]")
        raise typer.Exit(1)
    
    metadata = json.loads(metadata_path.read_text())
    
    # Load investigation
    investigation_path = output_dir / "01-investigation.md"
    investigation = investigation_path.read_text() if investigation_path.exists() else ""
    
    # Rebuild context from metadata
    if not ZULIP_REPO_PATH.exists():
        console.print(f"[red]Zulip repo not found at {ZULIP_REPO_PATH}[/red]")
        raise typer.Exit(1)
    
    scanner = RepositoryScanner(ZULIP_REPO_PATH)
    issue = {"title": metadata["issue_title"], "body": "", "number": issue_number, "html_url": metadata["issue_url"]}
    context = build_context_for_issue(scanner, issue)
    context["commit"] = metadata["repository_commit"]
    
    return context, investigation


@app.command()
def plan(
    issue_number: int,
    save: bool = typer.Option(True, help="Save plan to outputs/issue-<number>/02-plan.md"),
):
    """Generate implementation plan from investigation."""
    context, investigation = _load_context_and_investigation(issue_number)
    
    console.print(f"[green]Generating plan for issue #{issue_number}[/green]")
    
    llm = LLMClient()
    issue = {"title": context.get("issue_title", ""), "number": issue_number, "body": "", "html_url": ""}
    user_prompt = build_plan_prompt(issue, investigation, context)
    plan_md = llm.complete(PLAN_PROMPT, user_prompt)
    
    console.print(Markdown(plan_md))
    
    if save:
        output_dir = Path("outputs") / f"issue-{issue_number}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "02-plan.md").write_text(plan_md)
        console.print(f"\n[green]Plan saved to {output_dir}/02-plan.md[/green]")


@app.command()
def proposal(
    issue_number: int,
    save: bool = typer.Option(True, help="Save proposal to outputs/issue-<number>/03-proposal.md"),
):
    """Generate senior-to-junior proposal from plan."""
    context, _investigation = _load_context_and_investigation(issue_number)
    
    # Load plan
    plan_path = Path("outputs") / f"issue-{issue_number}" / "02-plan.md"
    if not plan_path.exists():
        console.print("[red]No plan found. Run 'plan' first.[/red]")
        raise typer.Exit(1)
    plan_md = plan_path.read_text()
    
    console.print(f"[green]Generating proposal for issue #{issue_number}[/green]")
    
    llm = LLMClient()
    issue = {"title": context.get("issue_title", ""), "number": issue_number}
    user_prompt = build_proposal_prompt(issue, plan_md, context)
    proposal_md = llm.complete(PROPOSAL_PROMPT, user_prompt)
    
    console.print(Markdown(proposal_md))
    
    if save:
        output_dir = Path("outputs") / f"issue-{issue_number}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "03-proposal.md").write_text(proposal_md)
        console.print(f"\n[green]Proposal saved to {output_dir}/03-proposal.md[/green]")


@app.command()
def patch(
    issue_number: int,
    save: bool = typer.Option(True, help="Save patch to outputs/issue-<number>/03-proposed.patch"),
):
    """Generate unified diff patch from plan."""
    context, _investigation = _load_context_and_investigation(issue_number)
    
    # Load plan
    plan_path = Path("outputs") / f"issue-{issue_number}" / "02-plan.md"
    if not plan_path.exists():
        console.print("[red]No plan found. Run 'plan' first.[/red]")
        raise typer.Exit(1)
    plan_md = plan_path.read_text()
    
    console.print(f"[green]Generating patch for issue #{issue_number}[/green]")
    
    llm = LLMClient()
    issue = {"title": context.get("issue_title", ""), "number": issue_number}
    user_prompt = build_patch_prompt(issue, plan_md, context)
    # Large token budget: reasoning models can burn tokens before emitting the diff
    patch = llm.complete(PATCH_PROMPT, user_prompt, temperature=0.1, max_tokens=8000)
    
    # Display patch with syntax highlighting
    syntax = Syntax(patch, "diff", theme="monokai", line_numbers=True)
    console.print(syntax)

    # Detect empty / placeholder / truncated diffs so `apply` doesn't fail cryptically
    is_placeholder = (
        "diff --git" not in patch
        or "@@" not in patch
        or ("dev/null" in patch and "--- a/" not in patch)
    )
    if is_placeholder:
        console.print("[red]LLM returned an empty/placeholder/truncated diff.[/red]")
        if "@@" not in patch:
            console.print("[yellow]The diff was cut off (no @@ hunk headers) — likely token budget.[/yellow]")
            console.print("[yellow]Just re-run 'patch' again to retry with the larger budget.[/yellow]")
        else:
            console.print("[yellow]The supplied file context may not include the source files.[/yellow]")
            console.print("[yellow]Re-run 'analyze' on the fresh Zulip clone, then 'plan', then 'patch'.[/yellow]")

    if save:
        output_dir = Path("outputs") / f"issue-{issue_number}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "03-proposed.patch").write_text(patch, encoding="utf-8")
        console.print(f"\n[green]Patch saved to {output_dir}/03-proposed.patch[/green]")
        console.print("[yellow]Review the patch before applying![/yellow]")


@app.command()
def apply(
    issue_number: int,
    patch_file: str = typer.Option(None, "--patch", help="Patch file path (default: outputs/issue-<number>/03-proposed.patch)"),
    no_test: bool = typer.Option(False, help="Skip running tests after applying"),
):
    """Apply patch to isolated git worktree."""
    output_dir = Path("outputs").resolve() / f"issue-{issue_number}"

    # Determine patch file (resolve to absolute so `git apply` works
    # when cwd is the worktree, not repo-mentor-ai)
    if patch_file:
        patch_path = Path(patch_file).resolve()
    else:
        patch_path = output_dir / "03-proposed.patch"

    if not patch_path.exists():
        console.print(f"[red]Patch file not found: {patch_path}[/red]")
        raise typer.Exit(1)

    # Reject empty / placeholder / truncated patches before touching git
    patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
    if (
        "diff --git" not in patch_text
        or "@@" not in patch_text
        or ("dev/null" in patch_text and "--- a/" not in patch_text)
    ):
        console.print("[red]Patch file is empty, a placeholder, or truncated (no @@ hunks).[/red]")
        console.print("[yellow]Re-run 'patch' to regenerate, then 'apply' again.[/yellow]")
        raise typer.Exit(1)
    
    # Load context to get repo path
    _, _ = _load_context_and_investigation(issue_number)
    
    if not ZULIP_REPO_PATH.exists():
        console.print(f"[red]Zulip repo not found at {ZULIP_REPO_PATH}[/red]")
        raise typer.Exit(1)
    
    # Create patch manager
    pm = PatchManager(ZULIP_REPO_PATH)
    
    console.print(f"[green]Creating worktree for issue #{issue_number}...[/green]")
    try:
        worktree_path, branch_name = pm.create_worktree(issue_number)
        console.print(f"  Worktree: {worktree_path}")
        console.print(f"  Branch: {branch_name}")
    except RuntimeError as e:
        console.print(f"[red]Failed to create worktree: {e}[/red]")
        raise typer.Exit(1)
    
    # Validate patch
    console.print("[green]Validating patch...[/green]")
    result = pm.validate_patch(worktree_path, patch_path)
    if not result.success:
        console.print(f"[red]Patch validation failed: {result.message}[/red]")
        console.print(result.stderr)
        pm.remove_worktree(issue_number)
        raise typer.Exit(1)
    console.print("  ✓ Patch validates")
    
    # Apply patch
    console.print("[green]Applying patch...[/green]")
    result = pm.apply_patch(worktree_path, patch_path)
    if not result.success:
        console.print(f"[red]Patch application failed: {result.message}[/red]")
        console.print(result.stderr)
        pm.remove_worktree(issue_number)
        raise typer.Exit(1)
    console.print("  ✓ Patch applied")
    
    # Show diff
    diff = pm.show_diff(worktree_path)
    if diff:
        syntax = Syntax(diff, "diff", theme="monokai", line_numbers=True)
        console.print(syntax)
    
    diff_stat = pm.show_diff_stat(worktree_path)
    if diff_stat:
        console.print(f"\n[cyan]Diff stat:[/cyan]\n{diff_stat}")
    
    # Run tests
    if not no_test:
        console.print("\n[green]Running tests...[/green]")
        runner = TestRunner(worktree_path)
        changed_files = pm.get_changed_files(worktree_path)
        
        results = runner.run_relevant_tests(changed_files, worktree_path)
        
        all_passed = True
        for r in results:
            status = "✓" if r.passed else "✗"
            console.print(f"  {status} {' '.join(r.command)} ({r.duration:.1f}s)")
            if not r.passed:
                all_passed = False
                if r.stderr:
                    console.print(f"    STDERR: {r.stderr[:500]}")
        
        if all_passed:
            console.print("\n[green]All tests passed![/green]")
        else:
            console.print("\n[red]Some tests failed![/red]")
    
    console.print(f"\n[green]Worktree ready at: {worktree_path}[/green]")
    console.print(f"[cyan]To inspect: cd {worktree_path} && git diff[/cyan]")
    console.print(f"[cyan]To commit: cd {worktree_path} && git add -A && git commit -m 'Fix issue #{issue_number}'[/cyan]")


@app.command()
def diff(
    issue_number: int,
):
    """Show diff of applied patch in worktree."""
    if not ZULIP_REPO_PATH.exists():
        console.print(f"[red]Zulip repo not found at {ZULIP_REPO_PATH}[/red]")
        raise typer.Exit(1)
    
    pm = PatchManager(ZULIP_REPO_PATH)
    branch_name = f"issue-{issue_number}-auto"
    worktree_path = pm.worktree_base / branch_name
    
    if not worktree_path.exists():
        console.print(f"[red]No worktree found for issue {issue_number}. Run 'apply' first.[/red]")
        raise typer.Exit(1)
    
    diff = pm.show_diff(worktree_path)
    if diff:
        syntax = Syntax(diff, "diff", theme="monokai", line_numbers=True)
        console.print(syntax)
    else:
        console.print("[yellow]No changes in worktree[/yellow]")
    
    diff_stat = pm.show_diff_stat(worktree_path)
    if diff_stat:
        console.print(f"\n[cyan]Diff stat:[/cyan]\n{diff_stat}")


@app.command()
def test(
    issue_number: int,
    command: str = typer.Option(None, "--command", help="Specific test command to run (lint, typecheck, test)"),
):
    """Run tests in the worktree."""
    if not ZULIP_REPO_PATH.exists():
        console.print(f"[red]Zulip repo not found at {ZULIP_REPO_PATH}[/red]")
        raise typer.Exit(1)
    
    pm = PatchManager(ZULIP_REPO_PATH)
    branch_name = f"issue-{issue_number}-auto"
    worktree_path = pm.worktree_base / branch_name
    
    if not worktree_path.exists():
        console.print(f"[red]No worktree found for issue {issue_number}. Run 'apply' first.[/red]")
        raise typer.Exit(1)
    
    runner = TestRunner(worktree_path)
    
    if command:
        if command == "lint":
            result = runner.run_lint(worktree_path)
        elif command == "typecheck":
            result = runner.run_typecheck(worktree_path)
        elif command == "test":
            result = runner.run_tests(cwd=worktree_path)
        else:
            console.print(f"[red]Unknown command: {command}[/red]")
            raise typer.Exit(1)
        
        console.print(runner.format_result(result))
    else:
        # Run relevant tests based on changed files
        changed_files = pm.get_changed_files(worktree_path)
        console.print(f"[cyan]Changed files: {', '.join(changed_files) if changed_files else 'none'}[/cyan]")
        
        results = runner.run_relevant_tests(changed_files, worktree_path)
        
        all_passed = True
        for r in results:
            console.print(runner.format_result(r))
            if not r.passed:
                all_passed = False
        
        if all_passed:
            console.print("\n[green]All tests passed![/green]")
        else:
            console.print("\n[red]Some tests failed![/red]")


@app.command()
def validate(issue_number: int):
    """Validate patch and run full test suite in worktree."""
    if not ZULIP_REPO_PATH.exists():
        console.print(f"[red]Zulip repo not found at {ZULIP_REPO_PATH}[/red]")
        raise typer.Exit(1)
    
    pm = PatchManager(ZULIP_REPO_PATH)
    branch_name = f"issue-{issue_number}-auto"
    worktree_path = pm.worktree_base / branch_name
    
    if not worktree_path.exists():
        console.print(f"[red]No worktree found for issue {issue_number}. Run 'apply' first.[/red]")
        raise typer.Exit(1)
    
    runner = TestRunner(worktree_path)
    
    console.print("[green]Running validation checks...[/green]\n")
    
    # Run lint
    console.print("[cyan]Running linter...[/cyan]")
    result = runner.run_lint(worktree_path)
    console.print(runner.format_result(result))
    if not result.passed:
        console.print("[red]Lint failed![/red]")
        raise typer.Exit(1)
    
    # Run typecheck
    console.print("\n[cyan]Running type checker...[/cyan]")
    result = runner.run_typecheck(worktree_path)
    console.print(runner.format_result(result))
    if not result.passed:
        console.print("[red]Type check failed![/red]")
        raise typer.Exit(1)
    
    # Run tests
    console.print("\n[cyan]Running tests...[/cyan]")
    result = runner.run_tests(cwd=worktree_path)
    console.print(runner.format_result(result))
    if not result.passed:
        console.print("[red]Tests failed![/red]")
        raise typer.Exit(1)
    
    console.print("\n[green]All validation checks passed![/green]")


@app.command()
def cleanup(
    issue_number: int,
):
    """Remove the worktree for an issue."""
    if not ZULIP_REPO_PATH.exists():
        console.print(f"[red]Zulip repo not found at {ZULIP_REPO_PATH}[/red]")
        raise typer.Exit(1)
    
    pm = PatchManager(ZULIP_REPO_PATH)
    result = pm.remove_worktree(issue_number)
    
    if result.success:
        console.print(f"[green]Worktree for issue #{issue_number} removed[/green]")
    else:
        console.print(f"[red]Failed to remove worktree: {result.message}[/red]")
        raise typer.Exit(1)


@app.command()
def implement(issue_number: int):
    """Generate implementation for an issue (placeholder for Milestone 5+)."""
    console.print("[yellow]Implement command not yet implemented[/yellow]")


@app.command()
def report(issue_number: int):
    """Generate final report (placeholder for Milestone 6+)."""
    console.print("[yellow]Report command not yet implemented[/yellow]")


if __name__ == "__main__":
    app()