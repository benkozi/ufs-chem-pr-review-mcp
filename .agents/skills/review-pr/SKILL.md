---
name: review-pr
description: >-
  Conduct an in-depth, rigorous code review of a GitHub Pull Request given its URL,
  always pulling down existing and pending review comments and threads on the PR,
  critically evaluating the validity of existing comments against domain physics and rules,
  refreshing the review knowledge base, synthesizing Ponytail over-engineering analysis,
  NOAA OMD standards, and atmospheric chemistry physics rules, writing the complete prioritized
  review report to a specified file path, and immediately ingesting all findings into the review
  database. Supports optional local checkout in scratch space (including dependent applications)
  via `gh pr checkout` for in-depth code and cross-component analysis. Use this skill whenever the
  user provides a PR URL and asks for a review written to a file.
---

# `review-pr` Runbook

Execute an autonomous, multi-lens code review of a GitHub Pull Request across UFS-Chem repositories.

## Review Inputs
1. **GitHub PR URL** (Required): e.g., `https://github.com/ufs-community/CATChem/pull/123`
2. **Target Output File Path** (Required): e.g., `reviews/catch-123.md` or `pr-123-review.md`
3. **Local Scratch Space** (Optional): e.g., `scratch/reviews/<repo>-pr-<pr_number>/` or conversation scratch directory for checking out the PR code and dependent applications locally for deeper inspection.

---

## Autonomous Multi-Lens Review Pipeline


### Phase 0: Freshness Verification & On-Demand Incremental Sync
1. Parse the PR URL into `owner/repo` and `pr_number`.
2. Inspect `data/ufs_chem_reviews.sqlite3` to check the latest indexed review timestamp for `target_repo`:
   ```bash
   python3 -c "
   import sqlite3
   con = sqlite3.connect('data/ufs_chem_reviews.sqlite3')
   cur = con.cursor()
   row = cur.execute('''
       SELECT max(c.created_at)
       FROM review_comments c
       JOIN pull_requests p ON c.pr_id = p.id
       JOIN repositories r ON p.repo_id = r.id
       WHERE r.name = ?
   ''', ('${TARGET_REPO}',)).fetchone()
   print(row[0] if row and row[0] else 'NONE')
   "
   ```
3. If the timestamp is older than 24 hours, or if the repository has not been indexed, automatically run an incremental sync:
   ```bash
   uv run ufs-chem-pr-review-sync --repo <target_repo>
   ```
   *Live PR diffs and existing comments bypass local cache and are always fetched fresh from GitHub in Phase 2.*

### Phase 1: Input Validation & Path Preparation
1. Validate target output file path (e.g. `reviews/pr-123.md`).
2. Ensure parent directories exist:
   ```python
   from pathlib import Path

   Path(target_file).parent.mkdir(parents=True, exist_ok=True)
   ```

### Phase 2: Ingestion, Live/Pending Comment Pulling & CI Checks Verification
Call the MCP tool `evaluate_pr` on the `ufs-chem-pr-review` MCP server (via `call_mcp_tool` or directly):
- Arguments: `pr_url="<pr_url>"`, `output_format="json"`, `review_mode="summary_and_inline"`.
- Under the hood, the MCP server automatically:
  1. Retrieves the live PR unified diff and changed files from GitHub.
  2. Ingests all submitted inline review comments (`/pulls/{pr}/comments`).
  3. Ingests conversation thread and issue discussions (`/issues/{pr}/comments`).
  4. Ingests unsubmitted pending review draft comments (`/pulls/{pr}/reviews` -> `state == "PENDING"`).
  5. Queries `data/ufs_chem_reviews.sqlite3` using FTS5 for ranked historical review precedents.
  6. Executes automated Ponytail and UFS-Chem domain rules, returning the structured `ReviewContextResponse` payload.

**CI & Test Gating Verification**:
7. Query GitHub Actions CI status for the PR:
   ```bash
   gh pr checks <pr_number> --repo <owner>/<repo>
   ```
8. Audit CI workflow definitions (`.github/workflows/*.yml`) and build configuration:
   - Identify which test targets actually run in CI (`ctest`, custom shell scripts, lint hooks).
   - Uncover **Conditional Test Gating**: Search CMakeLists.txt and test harnesses for `if(EXISTS ...)` or environment gates that silently skip tests when fixture files (e.g., large NetCDF data) are absent from the CI environment.
   - Uncover **Orphaned / Standalone Tests**: Check whether modified shell test scripts (e.g. `tests/*.sh`) are actually registered as CTest tests or invoked by CI jobs.
   - Uncover **Manual-Only Hook Stages**: Check `.pre-commit-config.yaml` for `stages: [manual]` or hooks bypassed by default CI `pre-commit run`.

### Phase 2b: Local Scratch Space & Dependent Application Checkout (Optional / In-Depth Analysis)
For in-depth analysis beyond the PR diff hunks (e.g., verifying whole-file context, checking all call sites across the codebase, auditing cross-component coupling interfaces, or testing patches), the PR can be checked out locally in a scratch space.

1. **Local Scratch Space Setup**:
   - Use an isolated scratch directory within the workspace (e.g., `scratch/reviews/<repo>-pr-<pr_number>/` or within the conversation scratch space) to avoid mutating or dirtying the primary workspace git state.
   - Create the directory:
     ```bash
     mkdir -p scratch/reviews/<repo>-pr-<pr_number>
     ```

2. **PR Checkout via `gh pr checkout`**:
   - Always try to use `gh pr checkout` to check out the PR branch locally:
     ```bash
     cd scratch/reviews/<repo>-pr-<pr_number>
     # Clone repository if not already present in scratch space:
     gh repo clone <owner>/<repo> .
     # Check out the PR branch:
     gh pr checkout <pr_number>
     ```
   - **Why `gh pr checkout`**:
     - Automatically configures branch tracking for the PR branch.
     - Transparently handles PRs originating from external contributor forks.
     - Ensures the local working tree exactly matches the PR's latest head commit.
   - If working within an existing local clone of the target repository:
     - Use `gh pr checkout <pr_number>` directly, or use `git worktree add scratch/reviews/<repo>-pr-<pr_number> -b review-pr-<pr_number>` to keep active working tree edits isolated.

3. **Dependent Application Checkout**:
   - UFS-Chem components operate within an integrated coupled modeling ecosystem (CCPP physics, NUOPC / ESMF caps, shared emissions data, and containerized workflows). PR modifications in one repository frequently impact dependent applications.
   - Dependent applications can also be checked out into sibling scratch directories for cross-repository compatibility analysis:
     - **Common UFS-Chem Repositories & Dependencies**:
       - `ufs-community/CATChem`: CCPP Atmospheric Chemistry suite; couples to host models and emission components.
       - `ufs-community/CECE`: Chemistry Emission & Chemical Evolution; couples to CATChem chemistry drivers and input data readers.
       - `noaa-emc/HELM`: High-resolution Emission and Loss Modeling; feeds gridded emissions data into CECE/CATChem.
       - `ufs-community/ufs-chem-container`: Container definitions and submodule integration tests.
       - Coupled host models & workflows: `ufs-weather-model`, `ufs-srw-app`, or `AQM`.
     - **Checking Out Dependent Repositories**:
       ```bash
       mkdir -p scratch/reviews/<repo>-pr-<pr_number>/<dependent_repo>
       cd scratch/reviews/<repo>-pr-<pr_number>/<dependent_repo>
       gh repo clone <dependent_owner>/<dependent_repo> .
       # Checkout the relevant tracking branch (e.g., develop/main) or coupled PR branch:
       git checkout <target_branch>
       # (Or if there is a corresponding dependent PR: gh pr checkout <dependent_pr_number>)
       ```

4. **In-Depth Analysis Enabled by Scratch Space**:
   - **Whole-Codebase Call-Site Search**: Use `grep` or `rg` to verify all caller sites and references to modified functions, variables, Fortran `use` statements, or C++ headers across the full codebase.
   - **Cross-Component Interface Verification**: Audit function/subroutine signature changes against dependent applications to ensure NUOPC cap interfaces (`chem_init`, `chem_run`, `chem_finalize`), CCPP physics schemes, and data dictionary names match.
   - **Namelist & Configuration Schema Auditing**: Cross-reference YAML/nml configuration changes with dependent model components.
   - **Pre-commit & Build Hook Inspection**: Inspect CMake targets, run linters (`pre-commit run --all-files`), or verify compile dependencies locally.

### Phase 3: Live Discussion Reconciliation & Comment Validity Evaluation
Critically evaluate all comments returned in `existing_pr_comments`:
1. **Validity Evaluation**:
   - For every comment, evaluate its technical claim against the code in the PR diff:
     - *Physics & Units*: Does the formula actually require molecular weight scaling, or is the variable already converted?
     - *Algorithmic / Language*: Is the suggested array slice syntax safe, or does the loop have recurrence data dependencies ($x(i) = x(i-1) + a(i)$)?
     - *OMD & EE2 Standards*: Does the suggestion violate Flux Fortran (pure functions), Forge C++ (RAII), or EE2 path standards?
     - *Ponytail*: Is the reviewer proposing an over-engineered abstraction?
   - Assign validity:
     - `[VALID]`: Accurately identifies a genuine defect or standards violation.
     - `[INVALID / FALSE POSITIVE]`: Reviewer's claim is mathematically, physically, or architecturally incorrect. Author should dismiss.
     - `[OUTDATED]`: Formerly valid comment, but rendered moot by a newer commit.
     - `[PARTIALLY VALID]`: Valid observation, but proposed fix is flawed.
   - Formulate a clear, concise technical rationale for each evaluation.
2. **Resolution Status**:
   - Determine whether subsequent author commits addressed the comment (`[RESOLVED]` vs `[OPEN / UNADDRESSED]`).
3. **Pending Review Drafts (`is_pending == True`)**:
   - Treat user drafts as high-priority intent. Validate them, incorporate them directly into the review synthesis, and expand them with 1-click suggestion blocks and diff patches.
4. **Deduplication Guard**:
   - Suppress duplicate findings for issues already raised by peer reviewers, unless adding critical new evidence or validating the fix.
5. **CI False-Confidence / False-Green Reconcilation**:
   - Reconcile "all checks passed" status against the code diff: determine whether passing CI represents genuine test validation or false reassurance due to skipped/gated tests, unexercised branches, or missing test registration.

### Phase 4: Multi-Lens Deep Dive & Ponytail Scrutiny
1. **Ponytail Audit**:
   - Identify dead code, speculative complexity (YAGNI), unnecessary helper functions with single callers, and reinvented standard library routines.
   - Calculate net lines removable: $L_{removable} = L_{dead} + L_{speculative} + L_{shrink\_delta}$.
2. **NOAA OMD Coding Standards**:
   - Fortran: Explicit kind suffixes (`_rk` or `_r8`), OpenMP `default(none)`, pure functions for physics kernels, proper `&` line continuations.
   - C++: Strict RAII, zero raw owning pointers, Fortran memory layout ordering.
   - Bash: `set -euo pipefail`, Google style, no backgrounding (`&`), standard exit codes.
   - Python: Aero protocol, lazy evaluation, strict typing.
3. **UFS-Chem Domain & Atmospheric Physics**:
   - Check molar mass conversions ($M_{spec} / M_{air}$).
   - Verify mass conservation in reaction kinetics.
   - Verify error handling on ESMF calls (`ESMF_LogFoundError`).
   - Confirm dynamic allocations have `stat=rc, errmsg=msg`.
4. **Historical Precedents & Guidelines (MCP Server)**:
   - For deeper review precedent search, call `search_review_history` on MCP server `ufs-chem-pr-review`.
   - For domain guideline deep dives, read resource `ufs-chem://guidelines/{category}` (`fortran`, `cpp`, `chemistry_physics`, `ee2`, `ponytail`).
5. **External Web & Documentation Checks**:
   - Consult CCPP physics interfaces, ESMF API docs, or third-party libraries via `search_web` if unfamiliar constructs appear.
6. **Scratch Space & Dependent Application Cross-Analysis**:
   - If checked out locally in scratch space (Phase 2b), search caller sites across the whole repository (`rg "subroutine_or_symbol"`) to verify whether modified subroutine interfaces, Fortran `intent`, or parameter types broke un-diffed callers.
   - Check dependent applications in the scratch space for breaking interface changes, NUOPC coupling contract mismatches, or namelist incompatibilities.

### Phase 5: Severity Prioritization
Categorize every finding into standard severity tiers:
- **P0 — Blocker / Crash / Invalid Physics**: Numerical instability, incorrect molecular weight ratio, memory corruption, uninitialized variable in compute loop, ESMF deadlock, broken build/test harness.
- **P1 — Major / Architectural Bug**: Missing allocation status checks, resource leaks, OpenMP race conditions, breaking interface changes, violation of EE2 operational standards, missing test downloads or uncalled test fixtures.
- **P2 — Moderate / Over-Engineering**: Ponytail violations (dead code, reinvented standard library routines, excessive abstractions), anonymous namespaces in headers, non-standard Fortran kinds, non-vectorized scalar loops.
- **P3 — Minor / Nit**: Formatting, documentation typos, comment clarifications, misleading script error messages.

### Phase 6: Machine-Applicable Patches & Suggestions
For every finding:
- Identify exact file path and line numbers in the target repository.
- Provide a GitHub 1-click suggestion block (````suggestion\n<replacement>\n````).
- Include unified diff hunks ready for `git apply`.
- If the PR was checked out locally in scratch space, validate unified diff patches with `git apply --check` or verify syntax against the checked out files before including them in the report.

### Phase 7: Output File Generation & User Presentation
1. Write the complete, formatted report directly to the target file path using `write_to_file`.
2. Present a concise confirmation response to the user:
   - Executive verdict (APPROVE / REQUEST CHANGES / COMMENT).
   - CI check status & false-confidence analysis (why checks passed despite issues).
   - Validity breakdown of existing peer comments (valid, invalid, resolved).
   - Status of pending review drafts (incorporated items).
   - Prioritized finding counts ($N_{P0}, N_{P1}, N_{P2}, N_{P3}$).
   - Ponytail metric summary (Net lines removable).
   - Database Ingestion status (number of findings recorded to historical database).
   - Clickable file link to the generated review artifact.

### Phase 8: Immediate Database Ingestion (Default Hook)
Immediately after generating the review report, the agent automatically persists all actionable review findings into the local historical review database (`data/ufs_chem_reviews.sqlite3`):

1. **Invoke `record_review_comments`**:
   Call the `record_review_comments` tool on the `ufs-chem-pr-review` MCP server (via `call_mcp_tool` or directly):
   - Arguments:
     ```json
     {
       "pr_url": "<pr_url>",
       "review_file_path": "<target_output_file_path>"
     }
     ```
2. **Under the Hood Execution**:
   - The MCP tool parses all P0, P1, P2, and P3 findings and suggestions directly from the report file.
   - Computes deterministic synthetic node IDs (`local-review:<repo>#<pr>:<path>:<line>:<hash>`).
   - Inserts or updates the findings into `data/ufs_chem_reviews.sqlite3`.
   - SQLite FTS5 trigger `comments_ai` immediately indexes the findings into `comments_fts`.
3. **Precedent Availability**:
   - These findings are now immediately discoverable via `search_review_history` and will be ranked as historical precedents in subsequent reviews of other PRs.
   - If the user or developer subsequently posts these comments to GitHub and runs `ufs-chem-pr-review-sync`, the sync engine automatically reconciles matching coordinates and text, replacing the local draft with the official GitHub comment with zero duplicates.

---


## Output Report Schema

The generated markdown document MUST adhere to this structure:

```markdown
# Pull Request Review: [<owner>/<repo>#<pr_number>] - <pr_title>

## 1. Executive Summary & Verdict
- **Verdict**: [APPROVE | REQUEST CHANGES | COMMENT]
- **Target Repo & PR**: [<owner>/<repo>#<pr_number>](https://github.com/<owner>/<repo>/pull/<pr_number>)
- **Lines Removable (Ponytail)**: ~<N> lines
- **Findings Summary**: <P0_count> Blockers (P0), <P1_count> Majors (P1), <P2_count> Over-Engineering (P2), <P3_count> Nits (P3)
- **High-Level Takeaway**: <1-2 concise paragraphs summarizing architecture and correctness>

## 2. Existing PR Review Discussions, Validity Assessment & Status

| Author | File / Context | Summary of Prior Comment | Validity Verdict | Technical Validity Assessment & Status |
| :--- | :--- | :--- | :--- | :--- |
| `@peer_reviewer` | `chem_driver.F90:142` | Suggests SIMD on column loop | `[INVALID / FALSE POSITIVE]` | Loop carries vertical dependency; vectorization breaks solver stability. Author should dismiss. |
| `@user` (Pending Draft) | `cmaq_aero.F90:88` | Unchecked zero-division on radius | `[VALID - INCORPORATED & EXPANDED]` | Confirmed divide-by-zero risk; expanded with 1-click safe epsilon clamp suggestion below. |

## 3. GitHub Actions CI Checks & Test Coverage/Gating Analysis

| Workflow / Check Name | Result | Elapsed Time | Analysis & Gating Status |
| :--- | :--- | :--- | :--- |
| `Full CI (CECE)` | `[PASSED]` | 11m 44s | Passed, but CEDS-dependent tests (`test_nuopc_field_coupling`) skipped due to missing fixture. |
| `Lint and Format` | `[PASSED]` | 14s | Passed; `symilar` hooks were in `stages: [manual]` and did not run. |

- **False Confidence / Gating Explanation**: <Detailed analysis explaining why passing CI did not exercise latent defects>

## 4. Prioritized Action Items
- [ ] **[P0]** <Summary of blocker> — [chem/rates.F90:42](file:///path/to/repo/chem/rates.F90#L42)
- [ ] **[P1]** <Summary of major bug> — [chem/driver.F90:110](file:///path/to/repo/chem/driver.F90#L110)
- [ ] **[P2]** <Ponytail over-engineering reduction> — [chem/utils.F90:15](file:///path/to/repo/chem/utils.F90#L15)

## 5. Detailed Findings & Machine-Applicable Suggestions

Every `[P*]` finding MUST include the four core fields (`Location`, `Tag`, `Problem`, `Recommendation`), followed by an optional `1-Click Suggestion` block when an inline replacement applies:

### [P0] Numerical Instability / Physics Error
- **Location**: [`chem/rates.F90:42`](file:///path/to/repo/chem/rates.F90#L42)
- **Tag**: `[defect / physics]` | Lines affected: 4 lines
- **Problem**: <Clear explanation of defect, root cause, and runtime/scientific impact>
- **Recommendation**: <Actionable fix recommendation grounded in atmospheric chemistry physics and NOAA OMD standards>
- **1-Click Suggestion**:
````suggestion
<replacement code>
````

### [P2] Ponytail: Delete Redundant Helper
- **Location**: [`chem/utils.F90:15`](file:///path/to/repo/chem/utils.F90#L15)
- **Tag**: `[delete / deduplicate]` | Lines removable: ~12 lines
- **Problem**: <Explanation of dead code, duplication, or speculative complexity>
- **Recommendation**: <Eliminate unused wrapper or duplicate block in favor of native standard library call or shared helper>
- **1-Click Suggestion**:
````suggestion
<replacement code>
````

## 6. Machine-Applicable Unified Diff Patch
```diff
--- a/chem/rates.F90
+++ b/chem/rates.F90
@@ -42,3 +42,3 @@
-  rate = 1.0 * temp
+  rate = 1.0_rk * temp
```
```
