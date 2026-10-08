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

## Getting Started

### 1. Prerequisites & Authentication

- **Runtime**: Python 3.13 and [uv](https://docs.astral.sh/uv/) (or [Docker](https://www.docker.com/))
- **GitHub Access**:
  - **Recommended**: Local [GitHub CLI (`gh`)](https://cli.github.com/) authenticated via `gh auth login` (read-only token is fully sufficient).
  - **Alternative**: A GitHub Personal Access Token (PAT) with `repo` or `public_repo` read scope, set via `UFS_CHEM_GITHUB_TOKEN` or `GITHUB_TOKEN`.

GitHub credentials are automatically resolved in this priority order:
1. Explicit CLI argument: `--token <PAT>`
2. Application environment variable: `UFS_CHEM_GITHUB_TOKEN`
3. Standard environment variable: `GITHUB_TOKEN`
4. Local GitHub CLI session: `gh auth token`

---

### 2. Installation & Initial Database Sync

Clone the repository and install dependencies:
```bash
git clone https://github.com/benkozi/ufs-chem-pr-review-mcp.git
cd ufs-chem-pr-review-mcp
uv sync --all-groups
```

Populate historical review comments from the tracked repositories into the local SQLite database:
```bash
# Ingest historical reviews across all configured UFS-Chem repositories
uv run ufs-chem-pr-review-sync --config config/repositories.yaml
```

> [!NOTE]
> If you are authenticated with `gh`, the sync tool runs automatically without needing to pass a token. If `gh` is unauthenticated, pass `--token <PAT>` or set `GITHUB_TOKEN`.

---

### 3. Configuring the MCP Server

You can run the MCP server using either **`uv` (recommended)** or a **Docker container**.

#### Option A: Native Execution with `uv` (Recommended)

##### MCP Client Configuration (`~/.gemini/config/mcp_config.json`)
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
        "UFS_CHEM_DB_PATH": "/absolute/path/to/ufs-chem-pr-review-mcp/data/ufs_chem_reviews.sqlite3",
        "UFS_CHEM_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

---

#### Option B: Containerized Execution with Docker (Completely Self-Contained)

The Docker image clones the repository internally and bundles the entire review database, rules, and configuration. **No host directory or volume mounts are required.**

##### 1. Build the Docker Image
```bash
docker build -t ufs-chem-pr-review-mcp:latest .
```
*(Optionally specify a branch or tag: `docker build --build-arg REPO_REF=main -t ufs-chem-pr-review-mcp:latest .`)*

##### 2. Configure MCP Client with Docker (`~/.gemini/config/mcp_config.json`)
```json
{
  "mcpServers": {
    "ufs-chem-pr-review": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "GITHUB_TOKEN",
        "ufs-chem-pr-review-mcp:latest"
      ]
    }
  }
}
```

> [!TIP]
> **Key Docker Flags for MCP**:
> - **`-i` (interactive)**: Required. Keeps standard input (`STDIN`) open so the host client can send JSON-RPC requests to the MCP server.
> - **Do NOT use `-t` (TTY)**: A pseudo-TTY converts `\n` to `\r\n` and injects escape sequences that corrupt JSON-RPC protocol framing.
> - **`-e GITHUB_TOKEN`**: Forwards your host `GITHUB_TOKEN` environment variable into the container for evaluating live GitHub pull requests with `evaluate_pr`.
> - **Optional custom database mount**: If you wish to mount an external database from your host, you can add `-v /path/to/host/data:/app/data` (without `:ro`). If omitted, the container uses its internal database.

---

### 4. Verification & Example Prompts

After saving your configuration and restarting your client:
1. In Antigravity / Gemini: Open **Additional Options (...) > MCP Servers** and confirm `ufs-chem-pr-review` is connected.
2. Test a query with the assistant:
   > *"Show me review statistics for ufs-community/CATChem using ufs-chem-pr-review."*

> [!TIP]
> Check out [**`docs/example-prompts.md`**](docs/example-prompts.md) for a comprehensive collection of copy-pasteable prompt recipes covering live PR evaluations, local diff auditing, historical precedent search, and patch generation.


## CLI Sync Usage

Use `ufs-chem-pr-review-sync` to populate and refresh your local review database from GitHub.

> [!IMPORTANT]
> Synchronization strictly requires a GitHub token (via `--token`, `UFS_CHEM_GITHUB_TOKEN`, `GITHUB_TOKEN`, or local `gh auth login`). Unauthenticated sync is blocked to prevent consuming anonymous rate limits.

```bash
# Sync all configured repositories (uses gh auth token if logged in)
uv run ufs-chem-pr-review-sync --config config/repositories.yaml

# Sync with an explicit token
uv run ufs-chem-pr-review-sync --token "ghp_your_token_here"

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
- `ufs-chem://guidelines`: JSON index listing all available guideline categories and descriptions.
- `ufs-chem://guidelines/{category}`: Full markdown guidelines and reviewer instructions for specific categories (`fortran`, `cpp`, `bash`, `python`, `ee2`, `hpc-libraries`, `chemistry_physics`, `esmf_nuopc`, `ponytail`).

### Prompts
- `review_pr`: Prompting template that guides the user's client LLM through an atmospheric chemistry pull request review workflow. See [**`docs/example-prompts.md`**](docs/example-prompts.md) for usage patterns.

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

---

## Acknowledgements

The code quality definitions, reviewer personas, and high-performance computing guidelines embedded in [`src/ufs_chem_pr_review_mcp/resources/guidelines/`](src/ufs_chem_pr_review_mcp/resources/guidelines/) and [`.agents/rules/`](.agents/rules/) are sourced from the NOAA NWS Office of Modeling and Development (OMD) and NCO HPC Environment Equivalence (EE2) instructions developed by Barry Baker ([@bbakernoaa](https://github.com/bbakernoaa)) in [`bbakernoaa/template-test`](https://github.com/bbakernoaa/template-test/tree/develop/.github/instructions).

These include:
- **Flux Protocol** ([`fortran.instructions.md`](src/ufs_chem_pr_review_mcp/resources/guidelines/fortran.instructions.md)): Modern Fortran (2018+) standards, explicit typing, pure compute kernels, and OpenMP variable scoping.
- **Forge Protocol** ([`cpp.instructions.md`](src/ufs_chem_pr_review_mcp/resources/guidelines/cpp.instructions.md)): Modern C++23 standards, strict RAII, and Fortran column-major memory layout interoperability (`std::mdspan`).
- **Aero Protocol** ([`python.instructions.md`](src/ufs_chem_pr_review_mcp/resources/guidelines/python.instructions.md)): Python standards for meteorological data processing, Pangeo ecosystem (`xarray`, `dask`), and lazy task graphs.
- **NCO EE2 Standards** ([`ee2-standards.md`](src/ufs_chem_pr_review_mcp/resources/guidelines/ee2-standards.md)): HPC Environment Equivalence operational production rules and error-handling hierarchies.
- **HPC Scientific Libraries** ([`hpc-libraries.md`](src/ufs_chem_pr_review_mcp/resources/guidelines/hpc-libraries.md)): ESMF/NUOPC return code validation, ParallelIO (PIO), parallel NetCDF-4, and Zarr.
- **Bash Standards** ([`bash.instructions.md`](src/ufs_chem_pr_review_mcp/resources/guidelines/bash.instructions.md)): Google Shell style and EE2 J-Job hierarchy.