---
name: review-pr
description: >-
  Conduct an in-depth, rigorous code review of a GitHub Pull Request given its URL,
  always pulling down existing and pending review comments and threads on the PR,
  critically evaluating the validity of existing comments against domain physics and rules,
  refreshing the review knowledge base, and synthesizing Ponytail over-engineering analysis,
  NOAA OMD standards, and atmospheric chemistry physics rules, writing the complete prioritized
  review report to a specified file path. Use this skill whenever the user provides a
  PR URL and asks for a review written to a file.
---

# `review-pr` Runbook

Execute an autonomous, multi-lens code review of a GitHub Pull Request across UFS-Chem repositories.

## Required Inputs
1. **GitHub PR URL**: e.g., `https://github.com/ufs-community/CATChem/pull/123`
2. **Target Output File Path**: e.g., `reviews/catch-123.md` or `pr-123-review.md`

---

## 7-Phase Autonomous Review Pipeline

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

### Phase 2: Ingestion & Live/Pending Comment Pulling
Call the MCP tool `evaluate_pr` on the `ufs-chem-pr-review` MCP server (via `call_mcp_tool` or directly):
- Arguments: `pr_url="<pr_url>"`, `output_format="json"`, `review_mode="summary_and_inline"`.
- Under the hood, the MCP server automatically:
  1. Retrieves the live PR unified diff and changed files from GitHub.
  2. Ingests all submitted inline review comments (`/pulls/{pr}/comments`).
  3. Ingests conversation thread and issue discussions (`/issues/{pr}/comments`).
  4. Ingests unsubmitted pending review draft comments (`/pulls/{pr}/reviews` -> `state == "PENDING"`).
  5. Queries `data/ufs_chem_reviews.sqlite3` using FTS5 for ranked historical review precedents.
  6. Executes automated Ponytail and UFS-Chem domain rules, returning the structured `ReviewContextResponse` payload.

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

### Phase 5: Severity Prioritization
Categorize every finding into standard severity tiers:
- **P0 — Blocker / Crash / Invalid Physics**: Numerical instability, incorrect molecular weight ratio, memory corruption, uninitialized variable in compute loop, ESMF deadlock.
- **P1 — Major / Architectural Bug**: Missing allocation status checks, resource leaks, OpenMP race conditions, breaking interface changes, violation of EE2 operational standards.
- **P2 — Moderate / Over-Engineering**: Ponytail violations (dead code, reinvented standard library routines, excessive abstractions), non-standard Fortran kinds, non-vectorized scalar loops.
- **P3 — Minor / Nit**: Formatting, documentation typos, comment clarifications.

### Phase 6: Machine-Applicable Patches & Suggestions
For every finding:
- Identify exact file path and line numbers in the target repository.
- Provide a GitHub 1-click suggestion block (````suggestion\n<replacement>\n````).
- Include unified diff hunks ready for `git apply`.

### Phase 7: Output File Generation & User Presentation
1. Write the complete, formatted report directly to the target file path using `write_to_file`.
2. Present a concise confirmation response to the user:
   - Executive verdict (APPROVE / REQUEST CHANGES / COMMENT).
   - Validity breakdown of existing peer comments (valid, invalid, resolved).
   - Status of pending review drafts (incorporated items).
   - Prioritized finding counts ($N_{P0}, N_{P1}, N_{P2}, N_{P3}$).
   - Ponytail metric summary (Net lines removable).
   - Clickable file link to the generated review artifact.

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

## 3. Prioritized Action Items
- [ ] **[P0]** <Summary of blocker> — [chem/rates.F90:42](file:///path/to/repo/chem/rates.F90#L42)
- [ ] **[P1]** <Summary of major bug> — [chem/driver.F90:110](file:///path/to/repo/chem/driver.F90#L110)
- [ ] **[P2]** <Ponytail over-engineering reduction> — [chem/utils.F90:15](file:///path/to/repo/chem/utils.F90#L15)

## 4. Detailed Findings & Machine-Applicable Suggestions

### [P0] Numerical Instability / Physics Error
- **Location**: [chem/rates.F90:42](file:///path/to/repo/chem/rates.F90#L42)
- **Problem**: <Clear explanation of defect>
- **Rationale**: <Atmospheric chemistry and NOAA OMD reasoning>
- **1-Click Suggestion**:
````suggestion
<replacement code>
````

### [P2] Ponytail Over-Engineering: Delete Redundant Helper
- **Location**: [chem/utils.F90:15](file:///path/to/repo/chem/utils.F90#L15)
- **Tag**: `[delete]` | Lines removable: ~12 lines
- **Recommendation**: <Eliminate unused wrapper in favor of native standard library call>

## 5. Machine-Applicable Unified Diff Patch
```diff
--- a/chem/rates.F90
+++ b/chem/rates.F90
@@ -42,3 +42,3 @@
-  rate = 1.0 * temp
+  rate = 1.0_rk * temp
```
```
