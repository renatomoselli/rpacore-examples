from __future__ import annotations

from rpacore import BusinessException, ProcessContext, Skill, SystemException


class EnrichRecord(Skill):
    """Merge post and user data into one enriched output record."""

    def execute(self, ctx: ProcessContext) -> None:
        post = ctx.require_state("current_post", dict, action=self.name)
        user = ctx.require_state("current_user", dict, action=self.name)

        if type(user.get("id")) is not int or user["id"] <= 0:
            raise BusinessException(
                f"User has invalid or missing required field: id ({user.get('id')!r})",
                action=self.name, stop=True,
            )

        # Validate required user fields
        for field in ("name", "email"):
            value = user.get(field)
            if not isinstance(value, str) or not value.strip():
                raise BusinessException(
                    f"User {user.get('id', 'unknown')} missing required field: {field}",
                    action=self.name, stop=True,
                )

        address = user.get("address")
        if address is not None and not isinstance(address, dict):
            raise SystemException(
                f"User {user['id']} has invalid address data: expected an object",
                action=self.name,
            )

        enriched = {
            "postId": post.get("id"),
            "title": post.get("title"),
            "body": post.get("body"),
            "userId": user.get("id"),
            "userName": user.get("name"),
            "userEmail": user.get("email"),
            "userCity": (address or {}).get("city", ""),
        }

        ctx.state["enriched_record"] = enriched
