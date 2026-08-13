"""RPA Core step: move processed CSV file to done directory."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from rpacore import BusinessException, ProcessContext, Step, Status, SystemException

from steps._path_utils import unique_destination, validate_contained_path

logger = logging.getLogger(__name__)


class MoveFile(Step):
    """Move processed CSV to done/ directory."""

    def execute(self, ctx: ProcessContext) -> None:
        if ctx.optional_state("validation_failed", bool, False, action=self.name):
            self.status = Status.SKIPPED
            return
        if ctx.optional_state("has_failures", bool, False, action=self.name):
            raise BusinessException("Calculator expression check failed", action=self.name)

        file_path = ctx.require_state("file_path", str, action=self.name)
        if not file_path:
            raise SystemException("No source file available to move", action=self.name)

        done_dir = ctx.require_config("done_dir", str, action=self.name)
        if not done_dir:
            raise SystemException("Config key 'done_dir' must be a non-empty string", action=self.name)

        input_dir = ctx.require_config("input_dir", str, action=self.name)
        src = validate_contained_path(file_path, input_dir, action=self.name)
        if not src.exists():
            raise SystemException(f"Source file does not exist: {src}", action=self.name)

        dst_dir = Path(done_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = unique_destination(dst_dir, src.name, action=self.name)

        try:
            shutil.move(str(src), str(dst))
            logger.info("Moved %s to %s", src, dst)
        except OSError as exc:
            raise SystemException(
                f"Unable to move {src} to {dst}: {exc}",
                action=self.name,
            ) from exc

        ctx.state["moved_file"] = str(dst)
