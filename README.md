# ufs-chem-pr-review-mcp

[![CI](https://github.com/benkozi/ufs-chem-pr-review-mcp/actions/workflows/ci.yaml/badge.svg)](https://github.com/benkozi/ufs-chem-pr-review-mcp/actions/workflows/ci.yaml)
[![Coverage: 100%](https://img.shields.io/badge/Coverage-100%25-brightgreen.svg)](https://github.com/benkozi/ufs-chem-pr-review-mcp)
[![Python: 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

Local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server providing historical review retrieval, Ponytail over-engineering audits, UFS-Chem domain rules, and machine-applicable patch generation for atmospheric chemistry repositories within the Unified Forecast System (UFS).

---

## Key Features

- **Zero Runtime LLM in Server**: The server operates deterministically using SQLite FTS5 lexical/keyword search, AST/regex heuristic matching, and domain rule engines. Structured context is supplied directly to the user's client LLM for synthesis.
- **Machine-Applicable Patches**: Provides patches formatted for immediate application via `git apply` or 1-click GitHub review ````suggestion ```` blocks.
- **Atmospheric Chemistry Domain Rules**:
  - Double-precision constants (`1.0_rk`) enforcement in Fortran computations.
  - Verification of molar mass ratio conversions ($M_{spec}/M_{air}$) for ppm/ppb to kg/kg mixing ratios.
  - Mandatory `stat=rc, errmsg=msg` checks on dynamic allocations (`allocate`).
  - Return code validations on ESMF / NUOPC interface calls (`ESMF_SUCCESS`).
- **Ponytail Over-Engineering Engine**:
  - Flags dead stubs, commented code, and unnecessary custom logic.
  - Respects NUOPC interface dummy variables and OpenMP SIMD loop directives.
- **STDIO Transport Integrity**:
  - Logging strictly directed to `sys.stderr` to prevent JSON-RPC transport frame corruption. Zero `print()` statements (enforced by Ruff `T201`).
- **100% Unit Test Coverage**: Strictly verified with `--cov-fail-under=100`.

---

## Tracked Repositories

Configured in [`config/repositories.yaml`](file:///Users/bkoziol/sandbox/git-benkozi/ufs-chem-pr-review-mcp/config/repositories.yaml):
- `ufs-community/CATChem`: Chemistry & Aerosol Translation Component for UFS
- `ufs-community/CECE`: Chemistry Emissions and Chemistry Evaluator
- `ufs-community/ufs-chem-container`: Containerized build and run environments for UFS-Chem
- `benkozi/ufs-chem-assay`: Benchmarking and validation harnesses
- `noaa-emc/HELM`: Atmospheric composition and air quality modeling tools

---

## Installation & Setup

### Prerequisites
- Python 3.13
- [uv](https://docs.astral.sh/uv/) package manager

### Install
```bash
git clone https://github.com/benkozi/ufs-chem-pr-review-mcp.git
cd ufs-chem-pr-review-mcp
uv sync --all-groups
```

### Configure MCP Client

#### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "ufs-chem-pr-review": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/ufs-chem-pr-review-mcp",
        "run",
        "ufs-chem-pr-review-mcp"
      ],
      "env": {
        "UFS_CHEM_GITHUB_TOKEN": "ghp_your_token_here",
        "UFS_CHEM_DB_PATH": "/absolute/path/to/ufs-chem-pr-review-mcp/data/reviews.sqlite3",
        "UFS_CHEM_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

#### Antigravity CLI / Gemini Sidecar
```json
{
  "name": "ufs-chem-pr-review-mcp",
  "command": "uv",
  "args": [
    "--directory",
    "/absolute/path/to/ufs-chem-pr-review-mcp",
    "run",
    "ufs-chem-pr-review-mcp"
  ],
  "env": {
    "UFS_CHEM_GITHUB_TOKEN": "ghp_your_token_here"
  }
}
```

---

## CLI Sync Usage

Use `ufs-chem-pr-review-sync` to populate and refresh your local review database from GitHub:

```bash
# Sync all configured repositories
uv run ufs-chem-pr-review-sync --config config/repositories.yaml

# Sync a specific repository with optional pruning (opt-in for large datasets)
uv run ufs-chem-pr-review-sync \
  --repo ufs-community/CATChem \
  --retention-days 180 \
  --max-records 500
```

---

## MCP Server Capabilities

### Tools
- `evaluate_pr`: Evaluates a GitHub PR by number, runs Ponytail and domain rules, retrieves matching historical review comments, and outputs structured review context.
- `evaluate_diff`: Analyzes raw unified diff text locally without making external GitHub API calls.
- `search_review_history`: Performs full-text search (SQLite FTS5) across past review comments with repository, language, and category filters.
- `get_repo_review_stats`: Returns review metrics, comment volumes, and top category patterns for a repository.
- `format_review_output`: Formats findings into `markdown`, `patch` (`git apply`), or `github_json` format.
- `generate_patch`: Combines multiple `CodePatch` hunks into a single unified diff patch.

### Resources
- `ufs-chem://repositories`: JSON catalog of tracked repositories and branch configurations.
- `ufs-chem://guidelines/{category}`: Review guidelines and pitfalls for specific categories (e.g., `chemistry_physics`, `esmf_nuopc`, `overengineering`).

### Prompts
- `review_pr`: Prompting template that guides the user's client LLM through an atmospheric chemistry pull request review workflow.

---

## Development & Quality Assurance

```bash
# Run unit test suite with 100% coverage gate
uv run pytest --cov=ufs_chem_pr_review_mcp --cov-report=term-missing --cov-fail-under=100

# Run static type checking
uv run mypy

# Run linting and format checking
uv run ruff check
uv run ruff format --check
uv run yamllint .
```