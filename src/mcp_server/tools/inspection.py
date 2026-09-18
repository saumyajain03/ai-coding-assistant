"""
MCP Tool: Repository Inspection
Safely inspects the repository directory tree, file metadata, and workspace status
while strictly enforcing the workspace jail invariant against traversal and symlink escapes.
"""

import os
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.config import get_settings


class FileInfo(BaseModel):
    name: str
    relative_path: str
    size_bytes: int
    is_dir: bool
    extension: str


class InspectionResult(BaseModel):
    workspace_root: str
    subpath: str
    total_files: int
    total_directories: int
    total_size_bytes: int
    files: list[FileInfo]
    tree_view: str


def inspect_repository_tool(
    subpath: str = "",
    depth: int = 2,
    file_pattern: str | None = None,
) -> dict[str, Any]:
    """
    Safely inspect the structure and files of the workspace repository.

    Args:
        subpath: Optional subdirectory path within the workspace to inspect.
        depth: Maximum folder depth to traverse (1 to 5, default 2).
        file_pattern: Optional glob pattern (e.g. '*.py', '*.ts') to filter files.

    Returns:
        Structured dictionary containing workspace tree, file metadata, and statistics.
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    target_dir = (workspace / subpath).resolve()

    # Enforce path jail invariant
    if not settings.is_path_in_workspace(target_dir):
        return {
            "error": "SECURITY_VIOLATION: Path traversal or escape outside workspace root is blocked.",
            "target_path": str(target_dir),
            "workspace_root": str(workspace),
            "status": "failed",
        }

    if not target_dir.exists():
        return {
            "error": f"Target path '{subpath}' does not exist in workspace.",
            "status": "not_found",
        }

    if not target_dir.is_dir():
        # Single file inspection
        stat = target_dir.stat()
        file_info = FileInfo(
            name=target_dir.name,
            relative_path=str(target_dir.relative_to(workspace)),
            size_bytes=stat.st_size,
            is_dir=False,
            extension=target_dir.suffix,
        )
        return InspectionResult(
            workspace_root=str(workspace),
            subpath=subpath,
            total_files=1,
            total_directories=0,
            total_size_bytes=stat.st_size,
            files=[file_info],
            tree_view=f"- {target_dir.name} ({stat.st_size} bytes)",
        ).model_dump()

    # Directory traversal with bounded depth
    depth = max(1, min(depth, 5))
    files_list: list[FileInfo] = []
    tree_lines: list[str] = [f"Workspace: {workspace.name}/{subpath if subpath else ''}"]
    total_size = 0
    total_dirs = 0

    target_depth = len(target_dir.parts)

    for root, dirs, filenames in os.walk(target_dir, followlinks=False):
        current_path = Path(root)
        current_depth = len(current_path.parts) - target_depth

        # Skip hidden directories like .git
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        if current_depth >= depth:
            dirs.clear()
            continue

        indent = "  " * (current_depth + 1)

        for d in dirs:
            dir_path = current_path / d
            # Symlink check
            if dir_path.is_symlink():
                resolved = dir_path.resolve()
                if not settings.is_path_in_workspace(resolved):
                    continue  # Skip dangerous symlink
            total_dirs += 1
            tree_lines.append(f"{indent}📁 {d}/")

        for f in filenames:
            if f.startswith("."):
                continue
            if file_pattern and not fnmatch(f, file_pattern):
                continue

            file_path = current_path / f
            if file_path.is_symlink():
                resolved = file_path.resolve()
                if not settings.is_path_in_workspace(resolved):
                    continue

            try:
                stat = file_path.stat()
                size = stat.st_size
                total_size += size
                rel_path = str(file_path.relative_to(workspace))

                files_list.append(
                    FileInfo(
                        name=f,
                        relative_path=rel_path,
                        size_bytes=size,
                        is_dir=False,
                        extension=file_path.suffix,
                    )
                )
                tree_lines.append(f"{indent}📄 {f} ({size} bytes)")
            except Exception:
                continue

    return InspectionResult(
        workspace_root=str(workspace),
        subpath=subpath,
        total_files=len(files_list),
        total_directories=total_dirs,
        total_size_bytes=total_size,
        files=files_list,
        tree_view="\n".join(tree_lines),
    ).model_dump()
