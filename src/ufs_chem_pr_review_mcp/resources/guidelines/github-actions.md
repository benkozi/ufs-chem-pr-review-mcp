# GitHub Actions CI/CD Review Guidelines

*Source: NOAA-EMC/omd-skills (`skills/github-actions-hardening`, `github-actions-efficiency`, `github-actions-runtime-upgrade-conventions`)*

## 1. Security Hardening & Threat Model

In GitHub Actions workflows (`.github/workflows/*.yml`), **`${{ <expr> }}` is expanded by the runner into the script before the shell executes it.**

### Script Injection Sinks
- Never interpolate attacker-controllable expressions directly inside `run:` or `actions/github-script`:
  - `github.event.pull_request.title`, `github.event.pull_request.body`, `github.head_ref`
  - `github.event.issue.title`, `github.event.issue.body`, `github.event.comment.body`
  - `github.event.commits.*.message`, `github.event.head_commit.*`
- **Safe Pattern**: Pass values through intermediate environment variables:
  ```yaml
  # ❌ BAD: Direct script injection sink
  - run: echo "Title: ${{ github.event.pull_request.title }}"

  # ✅ GOOD: Safe intermediate environment variable
  - env:
      PR_TITLE: ${{ github.event.pull_request.title }}
    run: printf 'Title: %s\n' "$PR_TITLE"
  ```

### Privileged Triggers & Untrusted Code Execution
- Classification of trigger trust:
  - `pull_request` (from fork): Runs with a **read-only token** and **no secrets access**.
  - `pull_request_target`, `workflow_run`, `issue_comment`: Run in the context of the **base repository with write tokens and full secrets access**.
- **Critical Violation**: Never check out and execute fork code (`ref: ${{ github.event.pull_request.head.sha }}`) under a privileged trigger (`pull_request_target` or `workflow_run`).

### Third-Party Action Pinning (Supply Chain Safety)
- Third-party actions (`uses:` not starting with `actions/*` or `github/*`) MUST be pinned to a full 40-character commit SHA, not a mutable tag (`@v1`) or branch (`@main`).
- Append a human-readable comment with the release version:
  ```yaml
  # ❌ BAD: Mutable tag
  - uses: softprops/action-gh-release@v1

  # ✅ GOOD: Pinned 40-character SHA
  - uses: softprops/action-gh-release@c062e08bd532815e2082a85e87e3ef29c3e6d191 # v2.0.8
  ```

### Least-Privilege Permissions
- Specify top-level `permissions: {}` (deny-all) or `contents: read`, then grant required scopes per job.
- Flag any `permissions: write-all` as over-scoped.

---

## 2. CI Efficiency & Cost Optimization

- **Concurrency Cancellation**: Cancel superseded in-flight runs on PR branches:
  ```yaml
  concurrency:
    group: ${{ github.workflow }}-${{ github.ref }}
    cancel-in-progress: ${{ github.event_name == 'pull_request' }}
  ```
- **Dependency Caching**: Cache dependencies using lockfile-keyed hashes:
  - Python: `actions/setup-python` with `cache: 'pip'` or `cache: 'uv'`.
  - CMake / Cpp: Cache build tools with hash keys derived from CMakeLists.txt or spack.lock.
- **5 Efficiency Guardrails**:
  1. Never hide required validation (release, schema, or integration tests).
  2. Do not reduce parallelism without justification.
  3. Preserve only documented matrix legs.
  4. Write-back jobs (formatters, bots) must use opt-in triggers.
  5. Keep repo changes separate from org-level settings.

---

## 3. Runtime Upgrades

- When updating actions to resolve runtime deprecation warnings (e.g. Node 16 -> Node 20):
  - Upgrade one action (or closely coupled group) at a time per commit.
  - Pin the updated action to its latest stable release commit SHA with trailing `# vX.Y.Z` comment.
  - Confirm workflow execution and outputs remain unchanged.
