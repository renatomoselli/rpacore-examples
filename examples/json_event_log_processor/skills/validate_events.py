from __future__ import annotations

from rpacore import BusinessException, ProcessContext, Skill

from skills import ALLOWED_EVENT_TYPES

REQUIRED_FIELDS = ("event_id", "event_type", "timestamp", "source")


class ValidateEvents(Skill):
    """Validate that all events in the loaded data conform to the expected schema."""

    def execute(self, ctx: ProcessContext) -> None:
        events = ctx.optional_state("events", list, None, action=self.name)

        if events is None:
            raise BusinessException(
                "No events in context — load_json_file must run first",
                action=self.name, stop=True,
            )
        if not isinstance(events, list):
            raise BusinessException(
                f"Expected a list of events, got {type(events).__name__}",
                action=self.name, stop=True,
            )
        if not events:
            raise BusinessException(
                "Event list is empty", action=self.name, stop=True,
            )

        for i, event in enumerate(events):
            if not isinstance(event, dict):
                raise BusinessException(
                    f"Event at index {i} is not an object (got {type(event).__name__})",
                    action=self.name, stop=True,
                )
            for field in REQUIRED_FIELDS:
                if field not in event or not event[field]:
                    raise BusinessException(
                        f"Event at index {i} (id={event.get('event_id', 'unknown')}) "
                        f"missing required field: {field}",
                        action=self.name, stop=True,
                    )
            if event["event_type"] not in ALLOWED_EVENT_TYPES:
                raise BusinessException(
                    f"Event at index {i} (id={event.get('event_id', 'unknown')}) "
                    f"has invalid event_type: {event['event_type']!r} "
                    f"(expected one of {ALLOWED_EVENT_TYPES})",
                    action=self.name, stop=True,
                )
