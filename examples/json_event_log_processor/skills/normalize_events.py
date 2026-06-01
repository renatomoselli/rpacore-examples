from __future__ import annotations

from datetime import datetime, timezone

from rpacore import ProcessContext, Skill, SystemException, get_logger

from skills import SEVERITY_MAP

logger = get_logger(__name__)


class NormalizeEvents(Skill):
    """Normalize and enrich events: parse timestamps, map severity, add computed fields."""

    def execute(self, ctx: ProcessContext) -> None:
        # Check for validation failure from ValidateEvents  [Q12]
        if ctx.data.get("validation_failed"):
            raise SystemException(
                "Validation failed — NormalizeEvents cannot proceed",
                action=self.name,
            )

        events = ctx.data.get("events")
        if events is None:
            raise SystemException(
                "No events in context — load_json_file must run first",
                action=self.name,
            )

        normalized = []
        for event in events:
            normalized_event = self._normalize_event(event)
            normalized.append(normalized_event)

        ctx.data["normalized_events"] = normalized
        logger.info(
            "Normalized %d events from %s",
            len(normalized),
            ctx.data.get("current_file", "unknown"),
        )

    def _normalize_event(self, event: dict) -> dict:
        """Normalize a single event: parse timestamp, map severity, add computed fields."""
        # Parse ISO 8601 timestamp (handle both Z suffix and +00:00 offset)
        timestamp_str = event["timestamp"]
        try:
            normalized_ts_str = timestamp_str.replace("Z", "+00:00")
            parsed_ts = datetime.fromisoformat(normalized_ts_str)
            # Naive timestamps are assumed to already be in UTC.
            # This is the expected format for ISO 8601 timestamps from
            # systems that emit UTC without an explicit offset.  [Q4]
            if parsed_ts.tzinfo is None:
                parsed_ts = parsed_ts.replace(tzinfo=timezone.utc)
            else:
                parsed_ts = parsed_ts.astimezone(timezone.utc)
            normalized_ts = parsed_ts.isoformat()
        except (ValueError, AttributeError) as exc:
            raise SystemException(
                f"Failed to parse timestamp '{timestamp_str}': {exc}",
                action=self.name,
            ) from exc

        # Map event_type to severity code (ValidateEvents guarantees valid value)
        # Uses the shared SEVERITY_MAP constant [Q9].
        event_type = event["event_type"]
        severity = SEVERITY_MAP[event_type]

        # Flatten payload (copy top-level keys)
        payload = event.get("payload")
        flattened_payload = {}
        if isinstance(payload, dict):
            flattened_payload = dict(payload)
        elif payload is not None:
            # Log warning when payload is present but not a dict  [Q10]
            logger.warning(
                "Event %s has non-dict payload (%s) — treating as empty",
                event.get("event_id", "unknown"),
                type(payload).__name__,
            )

        # Build normalized event
        normalized = {
            "event_id": event["event_id"],
            "event_type": event_type,
            "severity": severity,
            "timestamp": normalized_ts,
            "source": event["source"],
            "payload": flattened_payload,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }

        return normalized
