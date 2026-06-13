from __future__ import annotations

from rpacore import BusinessException, ProcessContext, Skill, SystemException


class EnrichRecord(Skill):
    """Merge post and user data into one enriched output record."""

    def execute(self, ctx: ProcessContext) -> None:
        post = ctx.require_state("current_post", dict, action=self.name)
        user = ctx.require_state("current_user", dict, action=self.name)

        # Validate required user fields
        for field in ("name", "email"):
            if not user.get(field):
                raise BusinessException(
                    f"User {user.get('id', 'unknown')} missing required field: {field}",
                    action=self.name, stop=True,
                )
        if user.get("id") is None:
            raise BusinessException(
                f"User missing required field: id",
                action=self.name, stop=True,
            )

        enriched = {
            "postId": post.get("id"),
            "title": post.get("title"),
            "body": post.get("body"),
            "userId": user.get("id"),
            "userName": user.get("name"),
            "userEmail": user.get("email"),
            "userCity": (user.get("address") or {}).get("city", ""),
        }

        ctx.state["enriched_record"] = enriched
