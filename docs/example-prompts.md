# Example Prompts for UFS-Chem PR Review MCP

This guide provides practical prompt patterns and copy-pasteable examples for interacting with the `ufs-chem-pr-review-mcp` server in Gemini, Antigravity CLI, or any MCP-compatible environment.

When the MCP server is configured in your client (e.g. `~/.gemini/config/mcp_config.json`), the agent automatically has access to all review tools. You do not need to construct raw JSON-RPC requests—simply ask the assistant in natural language.

---

## The Core Prompting Formula

For the highest-quality review output, structure your prompt with these key elements:

```text
[Action + Tool Context] + [Repository & Target (PR # or Diff)] + [Desired Focus] + [Output Format]
```

| Component | Purpose | Example |
| :--- | :--- | :--- |
| **Tool Context** | Naming the MCP server or tool guides the agent to invoke the specialized tool rather than guessing. | *"Using the `ufs-chem-pr-review` MCP server..."* |
| **Target & Scope** | Specific tracked repository name and pull request number or local git diff. | *"...evaluate `ufs-community/CATChem` PR #42..."* |
| **Focus Areas** | Tells the agent which domain heuristics to prioritize. | *"...focus on atmospheric chemistry units, double precision (`_rk`), and ESMF return checks..."* |
| **Output Style** | Instructs how findings should be formatted for actionability. | *"...provide a critical summary followed by inline ````suggestion```` blocks."* |

---

## Example Prompts by Use Case

### 1. Live GitHub Pull Request Review (`evaluate_pr`)

The agent invokes `evaluate_pr` to fetch the pull request diff from GitHub, query relevant historical comments from the SQLite review database, run automated Ponytail over-engineering audits and UFS-Chem domain rules, and synthesize a comprehensive review.

#### Atmospheric Chemistry & ESMF Compliance Review
> *"Please conduct an in-depth code review for `ufs-community/CATChem` PR #42 using the `ufs-chem-pr-review` MCP server. Focus on atmospheric chemistry unit conversions (ppm/ppb to kg/kg), Fortran double-precision constants (`1.0_rk`), and ESMF return code checking."*

#### Pruning & Simplicity Audit (Ponytail Focus)
> *"Review PR #25 in `ufs-community/CECE` using the MCP review tools. Audit specifically for over-engineering, dead code, and redundant abstractions. Detail which lines can be removed to reduce complexity."*

#### 1-Click Actionable Suggestions
> *"Evaluate PR #30 in `noaa-emc/HELM` using `evaluate_pr`. Provide a critical summary of findings followed by inline ````suggestion```` blocks that I can paste directly into a GitHub review."*

#### Summary-Only Executive Overview
> *"Use `evaluate_pr` on `ufs-community/CATChem` PR #50 with `review_mode='summary_only'`. Highlight only high-risk blockers and breaking changes."*

---

### 2. Local Diff & Pre-Commit Review (`evaluate_diff`)

If you are developing locally and want to verify changes before pushing to GitHub or opening a pull request, use `evaluate_diff`. This runs completely offline against your local SQLite database without making external GitHub API calls.

#### Reviewing Uncommitted Git Changes
> *"Run `git diff` on my current workspace and evaluate the output using `evaluate_diff` for `ufs-community/CATChem`. Check if any modifications violate our Fortran memory allocation or precision rules before I open a PR."*

#### Pasting a Unified Diff
> *"Please evaluate the following git diff using `evaluate_diff` against `ufs-community/CECE` and flag any issues past reviewers have commonly brought up:*
>
> *```diff*
> *diff --git a/src/chemistry/rates.F90 b/src/chemistry/rates.F90*
> *--- a/src/chemistry/rates.F90*
> *+++ b/src/chemistry/rates.F90*
> *@@ -45,3 +45,4 @@*
> *+  rate = 1.0 * temp_k*
> *```"*

---

### 3. Historical Precedent Search (`search_review_history`)

Use `search_review_history` to query the 1,100+ indexed review comments using SQLite FTS5 lexical search and ranking.

#### Chemistry & Physical Unit Conversions
> *"Use the `ufs-chem-pr-review` search tool to check past review discussions in CATChem regarding molecular weight ratio conversions and normalization from volume mixing ratio (ppm) to mass mixing ratio (kg/kg)."*

#### ESMF / NUOPC Interface Checks
> *"Search review history across all repositories for reviewer comments related to `ESMF_StateGet` return codes and `ESMF_LogFoundError`."*

#### High-Performance Computing & OpenMP Directives
> *"Search historical review comments in `ufs-community/CECE` for past discussions on OpenMP SIMD loop safety and data race prevention."*

#### Memory Management Precedents
> *"Find past review comments regarding dynamic array allocations (`allocate`) and mandatory `stat=rc, errmsg=msg` validation in Fortran modules."*

---

### 4. Repository Review Health & Analytics (`get_repo_review_stats`)

Retrieve repository review metrics, comment volumes, follow-up rates, and top reviewer distributions.

#### Repository Stats Query
> *"Show me review statistics for `ufs-community/CATChem` using the MCP server, including total comments, follow-up modification rate, and top reviewers."*

#### Cross-Repository Comparison
> *"Using `get_repo_review_stats`, summarize and compare review activity and category trends between `ufs-community/CATChem`, `ufs-community/CECE`, and `noaa-emc/HELM`."*

---

### 5. Patch Generation (`generate_patch`)

The agent can combine multiple code patches into a single machine-applicable unified diff patch for application via `git apply`.

#### Automated Patch Generation Prompt
> *"Review the uncommitted changes in my working tree using `evaluate_diff`. If there are any double-precision or allocate status violations, generate a unified diff patch that fixes them so I can apply it with `git apply`."*

---

## Using the Built-in MCP Prompt Template

The MCP server also exports a pre-packaged prompt template: [`review_pr`](../src/ufs_chem_pr_review_mcp/server.py).

If your MCP client supports prompt selection or slash command integration, select `review_pr` and supply the arguments:
- **`repo`**: Repository identifier (e.g. `ufs-community/CATChem`)
- **`pr_number`**: Pull request number (e.g. `42`)
- **`output_format`**: `markdown` (default), `patch`, or `github_json`
- **`review_mode`**: `summary_and_inline` (default), `summary_only`, or `inline_only`
