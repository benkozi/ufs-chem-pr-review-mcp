# NCO EE2 Review Gate & Portability Routing

*Source: NOAA-EMC/omd-skills (`skills/omd-standards/ee2-standards/` vendored from `ee-docs 11.0.0`)*

## Portability Routing

- **Target is WCOSS or an NCO operational delivery:** apply everything (`[portable]` + `[WCOSS]`).
- **Target is RDHPCS, a workstation, or research-only (`CATChem`, `CECE`, `HELM`, `ufs-chem-container`, `ufs-chem-assay`):**
  - Apply the **[portable]** subset and state that you did.
  - Do NOT present research-environment advice as full EE2 compliance.
  - Do NOT block a research script for a missing `$SENDDBN`, `prep_step`, `dbn_alert`, `JAAAAA` J-job naming, or PBS directive.

### Rule Tags
- **[portable]**: Environment-independent rules: message prefixes (`FATAL ERROR:` / `WARNING:`), restart, cleanup, ASCII output, DOCBLOCK, dead-code removal, fail-early, descriptive errors, and file-naming conventions.
- **[WCOSS]**: PBS, ecFlow, and COM mechanics (`$COMOUT`, `prep_step`, `dbn_alert`, `FORTn` units, J-Job naming).

---

## 20-Item EE2 Review Gate

Triage list of the highest-severity EE2 violations:

1. **Silent failure** [portable] — a command's nonzero exit is unchecked; no `err_chk` wrapper. (`standards.md`, `production-utilities.md`)
2. **Wrong message prefix** [portable] — fatal errors do not start with `FATAL ERROR:`; warnings not with `WARNING:`. (`standards.md`)
3. **Vague error** [portable] — "Missing GFS data" instead of naming the specific missing file and directory. (`standards.md`)
4. **No restart on a long job** [portable] — a job over 15 minutes lacks restart capability. (`standards.md`)
5. **Background processing** [portable] — anything is backgrounded (`&`); workload managers (PBS Pro/Slurm) lose control of it. (`standards.md`)
6. **Working directory not cleaned up** [portable] — not removed on success, or durable output not copied to `$COMOUT`. (`standards.md`)
7. **External symlink** [portable] — a symlink points outside the package. (`standards.md`)
8. **Non-ASCII output** [portable] — carriage returns or stylized quotes in files or stdout. (`standards.md`)
9. **No DOCBLOCK** [portable] — a source file or script lacks a documentation header. (`standards.md`)
10. **Dead code** [portable] — commented-out executable statements left in. (`standards.md`)
11. **Suppressed warnings** [portable] — compiler warnings silenced or the `-W` level lowered. (`standards.md`)
12. **Unwrapped `dbn_alert`** [WCOSS] — not guarded by a `$SENDDBN`/`$SENDDBN_NTC` check. (`dataflow.md`)
13. **Missing `prep_step`** [WCOSS] — no `prep_step` before an executable using `FORTn` units. (`production-utilities.md`)
14. **Absolute paths** [portable] — hardcoded paths to executables, libraries, or products in source, makefiles, or scripts. (`standards.md`)
15. **Hidden modules** [WCOSS] — a build uses a hidden module or a library not in `module avail`. (`standards.md`)
16. **`$job`/`$envir`/`$model_ver` in file names** [portable] — output names not stable across environments. (`file-naming.md`)
17. **Inline date math** [WCOSS] — date arithmetic not using `finddate.sh`, `ndate`, or `setpdy.sh`. (`date-and-grib-utilities.md`)
18. **No shebang or indirect invoke** [portable] — a script lacks `#!`, or is run as `sh script` instead of directly. (`standards.md`)
19. **Dev work areas present** [portable] — benchmarking tools or developer paths remain before IDSB submission. (`standards.md`)
20. **Wrong delivery branch or tag name** [portable] — not `release/vX.Y`, `bugfix/…`, `hotfix/…`, or `vX.Y-rc<#>` starting at 0. (`code-delivery.md`)
