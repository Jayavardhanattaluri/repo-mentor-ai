# repo-mentor-ai

LLM-assisted open-source issue solver for [zulip/zulip](https://github.com/zulip/zulip).

It fetches open Zulip issues, ranks them by beginner-friendliness, finds the
relevant source files in a local Zulip checkout, and uses an LLM
(NVIDIA NIM, OpenAI-compatible API) to produce an investigation, an
implementation plan, senior-to-junior guidance, and a unified-diff patch.
Patches are applied only to an **isolated git worktree** — never to your main
checkout — and validated with linting and tests.

> Core principle: the LLM may suggest and generate changes, but the developer
> must inspect, test, understand, and approve them. This tool never posts
> comments, pushes code, or opens pull requests.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | `python --version` |
| git | `git --version` |
| GitHub account | For a read-only Personal Access Token |
| NVIDIA account | For a NIM API key at [build.nvidia.com](https://build.nvidia.com) |
| ~2 GB disk | Zulip clone is large |

---

## 2. Setup

### 2.1 Clone this project and install

```bash
git clone <your-repo-mentor-ai-url> repo-mentor-ai
cd repo-mentor-ai

python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

pip install -e .
```

### 2.2 Clone Zulip (separate directory, short path recommended)

```bash
# Windows: enable long paths first (Zulip has very long fixture paths).
# Run once, no admin needed:
git config --global core.longpaths true

git clone https://github.com/zulip/zulip.git C:\Users\<you>\zulip
# Linux / macOS:
# git clone https://github.com/zulip/zulip.git ~/zulip
```

### 2.3 Create a GitHub token (read-only)

1. Go to <https://github.com/settings/tokens/new>
2. Give it a name like `repo-mentor-ai-readonly`
3. Scope: `public_repo` is enough (public data only)
4. Copy the token (starts with `ghp_`)

### 2.4 Create an NVIDIA NIM API key

1. Sign in at <https://build.nvidia.com>
2. Generate an API key (starts with `nvapi-`)

### 2.5 Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=nvidia/nemotron-3-super-120b-a12b
ZULIP_REPO_PATH=C:\Users\<you>\zulip
OUTPUT_DIR=outputs
MAX_FILE_CHARS=12000
```

> `ZULIP_REPO_PATH` must be the **absolute path to the Zulip clone**
> (not to this project). Never commit `.env` — it is already gitignored.

To list models your key can access:

```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
client = OpenAI(api_key=os.getenv('NVIDIA_API_KEY'),
                base_url='https://integrate.api.nvidia.com/v1')
for m in client.models.list().data:
    print(m.id)
"
```

---

## 3. Verify it works (smoke test, ~2 minutes)

Run these in order. Each step must succeed before moving on.

### Step 1 — CLI loads

```bash
python -m app.cli --help
```

Expected: a table of commands (`fetch-issues`, `rank-issues`, `analyze`,
`plan`, `proposal`, `patch`, `apply`, `diff`, `test`, `validate`, `cleanup`).

### Step 2 — Unit tests pass

```bash
python -m pytest tests/ -v
```

Expected: `25 passed`.

### Step 3 — Lint is clean

```bash
ruff check app/ tests/
```

Expected: `All checks passed!`

### Step 4 — Fetch real issues from GitHub

```bash
python -m app.cli fetch-issues --label "help wanted"
```

Expected: `Fetched 30 issues` followed by issue numbers and titles.
This proves your `GITHUB_TOKEN` works.

### Step 5 — Rank issues

```bash
python -m app.cli rank-issues --label "help wanted"
```

Expected: a ranked table (highest score first) with reasons such as
`help wanted`, `unassigned`, `good first issue`.

### Step 6 — Analyze without the LLM (no API cost)

```bash
python -m app.cli analyze 38384 --no-use-llm
```

Expected: repository commit SHA, extracted keywords, a list of relevant
files, and `Analysis saved to outputs\issue-38384/`. This proves
`ZULIP_REPO_PATH` points at a real Zulip checkout.

If you see `Zulip repo not found`, fix `ZULIP_REPO_PATH` in `.env`.

### Step 7 — Full LLM pipeline (uses API credits)

```bash
python -m app.cli analyze 38384
python -m app.cli plan 38384
python -m app.cli proposal 38384
python -m app.cli patch 38384
```

Expected after each step: rendered Markdown (or diff) plus a saved file:

```text
outputs/issue-38384/
├── metadata.json
├── 01-investigation.md
├── 02-plan.md
├── 03-proposal.md
└── 03-proposed.patch
```

Before applying, **open `03-proposed.patch` and read it**. It must contain
real hunks (`diff --git a/...`, `--- a/...`, `+++ b/...`, `@@ ... @@`).
If it is empty or a `dev/null` placeholder, just re-run `patch` (LLM
output is non-deterministic).

### Step 8 — Apply to an isolated worktree

```bash
python -m app.cli apply 38384 --no-test
```

Expected: worktree created under `<zulip>/.worktrees/issue-38384-auto`,
patch validates (`git apply --check`), patch applies, diff shown.
Your main Zulip checkout is untouched. Clean up with:

```bash
python -m app.cli cleanup 38384
```

If all 8 steps pass, the setup works end to end. ✅

---

## 4. Command reference

| Command | What it does |
|---|---|
| `fetch-issues --label "..."` | List open zulip/zulip issues (PRs excluded) |
| `rank-issues --label "..." --limit 30` | Rank issues by beginner-friendliness score |
| `analyze <number> [--no-use-llm]` | Find relevant files + LLM investigation → `01-investigation.md` |
| `plan <number>` | Implementation plan → `02-plan.md` (needs `analyze` first) |
| `proposal <number>` | Senior-to-junior guidance → `03-proposal.md` (needs `plan` first) |
| `patch <number>` | Unified diff → `03-proposed.patch` (needs `plan` first) |
| `apply <number> [--no-test] [--patch PATH]` | Validate + apply patch in isolated worktree, run relevant tests |
| `diff <number>` | Show worktree diff |
| `test <number> [--command lint\|typecheck\|test]` | Run relevant tests in worktree |
| `validate <number>` | Full validation: lint + typecheck + tests |
| `cleanup <number>` | Remove the worktree |

Typical flow for one issue:

```bash
python -m app.cli rank-issues --label "help wanted"
python -m app.cli analyze 38384
python -m app.cli plan 38384
python -m app.cli patch 38384
# ... review outputs/issue-38384/03-proposed.patch ...
python -m app.cli apply 38384 --no-test
python -m app.cli test 38384
python -m app.cli cleanup 38384
```

---

## 5. Configuration

| Variable | Description |
|---|---|
| `GITHUB_TOKEN` | GitHub Personal Access Token (`public_repo` scope is enough) |
| `NVIDIA_API_KEY` | NVIDIA NIM API key |
| `NVIDIA_BASE_URL` | Default: `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_MODEL` | Default: `nvidia/nemotron-3-super-120b-a12b` (verified working; `meta/llama-3.1-70b-instruct` is end-of-life and returns HTTP 410) |
| `ZULIP_REPO_PATH` | Absolute path to local Zulip clone |
| `OUTPUT_DIR` | Output directory (default: `outputs`) |
| `MAX_FILE_CHARS` | Max characters per file sent to the LLM (default: `12000`) |

---

## 6. Project structure

```text
repo-mentor-ai/
├── app/
│   ├── config.py         # Environment-based configuration
│   ├── models.py         # Pydantic models (Issue, IssueScore, TestResult)
│   ├── github_client.py  # GitHub REST client (filters out pull requests)
│   ├── issue_ranker.py   # Deterministic beginner-friendliness scoring
│   ├── repo_scanner.py   # git grep search, keyword extraction, file context
│   ├── llm_client.py     # NVIDIA NIM OpenAI-compatible client
│   ├── prompts.py        # Safe, structured prompts (anti-hallucination rules)
│   ├── patch_manager.py  # Isolated git worktrees, patch validation/application
│   ├── test_runner.py    # Allowlisted test/lint commands
│   └── cli.py            # Typer CLI
├── tests/                # Pytest suite (mocked externals, no API calls)
├── fixtures/             # Sample GitHub / LLM payloads
├── outputs/              # Per-issue artifacts (gitignored)
├── .env.example
├── pyproject.toml
└── plan.md               # Full design document
```

---

## 7. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `Missing required environment variable` | `.env` missing or not in project root; copy from `.env.example` |
| GitHub `401 Unauthorized` | Token invalid/expired; create a new one with `public_repo` scope |
| GitHub `403 rate limit` | Unauthenticated or exhausted quota; wait or check token is sent |
| `Zulip repo not found` | `ZULIP_REPO_PATH` wrong; must be absolute path to the Zulip clone |
| `410 ... reached its end of life` | Model retired (e.g. `meta/llama-3.1-70b-instruct`); switch `NVIDIA_MODEL` to `nvidia/nemotron-3-super-120b-a12b` |
| `404 ... Not found for account` | Your key can't access that model; list models (2.5) and pick one |
| `analyze` hangs / times out | Large model or slow network; retry, or use `--no-use-llm` to test the non-LLM path |
| `Filename too long` during worktree creation (Windows) | Run `git config --global core.longpaths true`, then re-clone Zulip to a short path |
| `can't open patch ... No such file` | Fixed in current version (absolute patch path); `git pull` latest |
| `No valid patches in input` | Patch file is empty/placeholder/truncated; re-run `patch` and review the file before `apply` |
| `patch` saves `03-proposed.rejected.txt` instead | LLM returned reasoning prose, not a diff — file context lacked the plan's source files; re-run `analyze` (search now ranks by keyword rarity and excludes `.claude/`/`.github/`), then `plan`, then `patch` |
| `Plan lists files not in repo (excluded)` | Plan hallucinated paths; only existing files are fed to the patch step, others are flagged in the prompt — review `02-plan.md` critically |
| `UnicodeEncodeError` on Windows console | Display-only issue with Markdown rendering; the saved `.md` file is correct — open it directly |

---

## 8. Safety notes

- The GitHub token only needs **read** access for all current features.
- Patches are validated with `git apply --check` and applied only inside
  `ZULIP_REPO_PATH/.worktrees/issue-<number>-auto`, never in your main checkout.
- Test commands come from a fixed allowlist — the LLM cannot execute arbitrary shell.
- Always review `03-proposed.patch` before `apply`. The tool refuses to
  generate patches for files outside the supplied context, but human review
  is still required.
- No GitHub write operations exist in this version (no comments, pushes, or PRs).

---

## 9. Status

Working: fetch → rank → analyze → plan → proposal → patch → apply →
diff/test/validate → cleanup.

Not yet implemented: `implement` and `report` placeholders, iterative
repair loop (failure analysis → revised patch → re-test), and any GitHub
write integration (draft PRs, comments) — all require explicit human approval
by design. See `plan.md` for the full roadmap.
