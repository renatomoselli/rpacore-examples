"""RPA Core skill: move processed CSV file to done directory."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from rpacore import BusinessException, ProcessContext, Skill, Status, SystemException

logger = logging.getLogger(__name__)


class MoveFile(Skill):
    """Move processed CSV to done/ directory."""

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.data.get("validation_failed"):
            self.status = Status.SKIPPED
            return
        if ctx.data.get("has_failures"):
            raise BusinessException("Calculator expression check failed", action=self.name)

        file_path = ctx.data.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            raise SystemException("No source file available to move", action=self.name)

        done_dir = ctx.config.get("done_dir")
        if not isinstance(done_dir, str) or not done_dir:
            raise SystemException("Config key 'done_dir' must be a non-empty string", action=self.name)

        src = Path(file_path)
        if not src.exists():
            raise SystemException(f"Source file does not exist: {src}", action=self.name)

        dst_dir = Path(done_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = _unique_destination(dst_dir, src.name)

        try:
            shutil.move(str(src), str(dst))
            logger.info("Moved %s to %s", src, dst)
        except OSError as exc:
            raise SystemException(
                f"Unable to move {src} to {dst}: {exc}",
                action=self.name,
            ) from exc

        ctx.data["moved_file"] = str(dst)


def _unique_destination(directory: Path, filename: str) -> Path:
    dst = directory / filename
    if not dst.exists():
        return dst

    stem = dst.stem
    suffix = dst.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate

    raise SystemException(f"Unable to find available destination for {filename}", action="move_file")
