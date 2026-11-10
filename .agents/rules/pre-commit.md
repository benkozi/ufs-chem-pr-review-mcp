---
description: Mandatory post-implementation pre-commit and test coverage gate execution
applyTo: "**/*"
---

# Post-Implementation Pre-Commit & Coverage Gate Rule

After completing any code, configuration, skill, rule, or documentation implementation in this repository, you MUST execute the repository's pre-commit hooks and test coverage gate before concluding your turn or committing changes:

1. **Run Pre-Commit Hooks Across All Files**:
   ```bash
   uv run pre-commit run --all-files
   ```
   - If any hook (`trailing-whitespace`, `end-of-file-fixer`, `ruff-check`, `ruff-format`, `mypy`, `yamlfix`, `yamllint`) modifies files or fails, resolve all issues and re-run `uv run pre-commit run --all-files` until every hook passes cleanly.

2. **Run the Unit Test Suite & 100% Coverage Gate**:
   ```bash
   uv run pytest --cov=ufs_chem_pr_review_mcp --cov-report=term-missing --cov-fail-under=100
   ```
   - Ensure all tests pass and total statement coverage across `src/ufs_chem_pr_review_mcp` remains at `100%`.
