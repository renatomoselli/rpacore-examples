from __future__ import annotations

from oref import BusinessException, ProcessContext, Skill

ALLOWED_EVENT_TYPES = ("info", "warning", "error")
REQUIRED_FIELDS = ("event_id", "event_type", "timestamp", "source")


class ValidateEvents(Skill):
    """Validate that all events in the loaded data conform to the expected schema.

    Sets ctx.data["validation_failed"] = True before raising BusinessException
    so that NormalizeEvents can check the flag and raise SystemException to stop
    execution (the engine only breaks on SystemException).
    """

    def execute(self, ctx: ProcessContext) -> None:
        events = ctx.data.get("events")
        if events is None:
            ctx.data["validation_failed"] = True
            raise BusinessException(
                "No events in context — load_json_file must run first",
                action=self.name,
            )

        if not isinstance(events, list):
            ctx.data["validation_failed"] = True
            raise BusinessException(
                f"Expected a list of events, got {type(events).__name__}",
                action=self.name,
            )

        if not events:
            ctx.data["validation_failed"] = True
            raise BusinessException(
                "Event list is empty",
                action=self.name,
            )

        for i, event in enumerate(events):
            if not isinstance(event, dict):
                ctx.data["validation_failed"] = True
                raise BusinessException(
                    f"Event at index {i} is not an object (got {type(event).__name__})",
                    action=self.name,
                )

            for field in REQUIRED_FIELDS:
                if field not in event or not event[field]:
                    ctx.data["validation_failed"] = True
                    raise BusinessException(
                        f"Event at index {i} (id={event.get('event_id', 'unknown')}) missing required field: {field}",
                        action=self.name,
                    )

            if event["event_type"] not in ALLOWED_EVENT_TYPES:
                ctx.data["validation_failed"] = True
                raise BusinessException(
                    f"Event at index {i} (id={event.get('event_id', 'unknown')}) has invalid event_type: {event['event_type']!r} (expected one of {ALLOWED_EVENT_TYPES})",
                    action=self.name,
                )

        # All validations passed
        ctx.data["validation_failed"] = False
