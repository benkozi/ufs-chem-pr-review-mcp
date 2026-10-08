"""Machine-applicable patch schemas and unified diff assembly."""

from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field


class CodePatch(BaseModel):
    """Machine-applicable code patch hunk for a specific target file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file_path: str = Field(
        description="Relative repository path of the target file to patch"
    )
    start_line: int = Field(
        ge=1,
        description="1-indexed starting line number of original code in target file",
    )
    end_line: int = Field(
        ge=1,
        description="1-indexed ending line number of original code in target file (inclusive)",
    )
    original_code: str = Field(
        description="Exact original code block to be replaced or deleted"
    )
    replacement_code: str = Field(
        description="Exact replacement code block (empty string for pure deletion)"
    )
    unified_hunk: str = Field(
        description="RFC-compliant unified diff hunk (e.g. @@ -start,len +start,len @@) ready for git apply"
    )


class PatchResult(BaseModel):
    """Result of assembling multiple CodePatch items into a consolidated git patch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    patch_text: str = Field(
        description="Full unified diff patch string compatible with git apply"
    )
    files_changed: list[str] = Field(
        description="List of file paths modified by this patch"
    )
    total_additions: int = Field(ge=0, description="Total count of added lines")
    total_deletions: int = Field(ge=0, description="Total count of deleted lines")


def build_unified_diff_patch(patches: list[CodePatch]) -> PatchResult:
    """Consolidate a list of CodePatch objects into a single git apply-compatible patch string.

    Hunks within the same file are sorted by start_line in DESCENDING order to prevent
    downstream line offsets from being displaced during sequential patch application.
    """
    if not patches:
        return PatchResult(
            patch_text="",
            files_changed=[],
            total_additions=0,
            total_deletions=0,
        )

    # Group patches by file_path
    by_file: dict[str, list[CodePatch]] = defaultdict(list)
    for p in patches:
        by_file[p.file_path].append(p)

    total_add = 0
    total_del = 0
    patch_lines: list[str] = []

    # Sort files deterministically
    for file_path in sorted(by_file.keys()):
        file_patches = by_file[file_path]
        # Sort hunks descending by line number to prevent offset drift
        file_patches.sort(key=lambda x: x.start_line, reverse=True)

        patch_lines.append(f"diff --git a/{file_path} b/{file_path}")
        patch_lines.append(f"--- a/{file_path}")
        patch_lines.append(f"+++ b/{file_path}")

        for fp in file_patches:
            hunk = fp.unified_hunk.strip()
            if hunk:
                patch_lines.append(hunk)
                # Count additions and deletions from hunk lines
                for line in hunk.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        total_add += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        total_del += 1

    patch_text = "\n".join(patch_lines) + "\n" if patch_lines else ""
    return PatchResult(
        patch_text=patch_text,
        files_changed=sorted(by_file.keys()),
        total_additions=total_add,
        total_deletions=total_del,
    )
