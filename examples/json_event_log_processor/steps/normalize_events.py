from __future__ import annotations
from datetime import datetime, timezone

from rpacore import ProcessContext, Step, SystemException, get_logger
from steps import SEVERITY_MAP

logger = get_logger(__name__)


class NormalizeEvents(Step):
    """Normalize and enrich events: parse timestamps, map severity, add computed fields."""

    def execute(self, ctx: ProcessContext) -> None:
        events = ctx.require_state("events", list, action=self.name)

        normalized = []
        for event in events:
            normalized_event = self._normalize_event(event)
            normalized.append(normalized_event)

        ctx.state["normalized_events"] = normalized
        current_file = ctx.optional_state("current_file", str, "unknown", action=self.name)
        logger.info("Normalized %d events from %s", len(normalized), current_file)

    def _normalize_event(self, event: dict) -> dict:
        """Normalize a single event: parse timestamp, map severity, add computed fields."""
        if not isinstance(event, dict):
            raise SystemException(
                f"Expected event object, got {type(event).__name__}",
                action=self.name,
            )

        timestamp_str = event["timestamp"]
        try:
            normalized_ts_str = timestamp_str.replace("Z", "+00:00")
            parsed_ts = datetime.fromisoformat(normalized_ts_str)
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

        event_type = event["event_type"]
        severity = SEVERITY_MAP.get(event_type)
        if severity is None:
            raise SystemException(
                f"Unsupported event_type for severity mapping: {event_type!r}",
                action=self.name,
            )

        payload = event.get("payload")
        flattened_payload = {}
        if isinstance(payload, dict):
            flattened_payload = dict(payload)
        elif payload is not None:
            logger.warning(
                "Event %s has non-dict payload (%s) — treating as empty",
                event.get("event_id", "unknown"),
                type(payload).__name__,
            )

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
