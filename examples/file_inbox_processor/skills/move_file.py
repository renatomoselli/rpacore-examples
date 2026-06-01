from __future__ import annotations

import shutil
from pathlib import Path

from rpacore import ProcessContext, Skill, Status, SystemException

from skills._path_utils import validate_contained_path


class MoveFile(Skill):
    """Move successfully processed files to the done folder."""

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.data.get("validation_failed"):
            self.status = Status.SKIPPED
            return

        source = ctx.data.get("report_file") or ctx.data.get("file_path")
        done_dir = ctx.config.get("done_dir")
        if not isinstance(source, str) or not source:
            raise SystemException("No source file available to move", action=self.name)
        if not isinstance(done_dir, str) or not done_dir:
            raise SystemException("Config key 'done_dir' must be a non-empty string", action=self.name)

        # Skip validation when inbox_dir is absent (unit tests); production always provides it.
        inbox_dir = ctx.config.get("inbox_dir")
        if isinstance(inbox_dir, str) and inbox_dir:
            src = validate_contained_path(source, inbox_dir, action=self.name)
        else:
            src = Path(source)
        dst_dir = Path(done_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name

        try:
            shutil.move(str(src), str(dst))
        except OSError as exc:
            raise SystemException(f"Unable to move {src} to {dst}: {exc}", action=self.name) from exc

        ctx.data["moved_file"] = str(dst)
