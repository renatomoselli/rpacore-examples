from __future__ import annotations

from rpacore import BusinessException, ProcessContext, Skill, SystemException
from skills import KEY_CURRENT_POST, KEY_CURRENT_USER, KEY_ENRICHED_RECORD


class EnrichRecord(Skill):
    """Merge post and user data into one enriched output record."""

    def execute(self, ctx: ProcessContext) -> None:
        post = ctx.data.get(KEY_CURRENT_POST)
        user = ctx.data.get(KEY_CURRENT_USER)

        if post is None:
            raise SystemException(
                "No current_post in context — fetch_posts must run first",
                action=self.name,
            )
        if user is None:
            raise SystemException(
                "No current_user in context — fetch_user must run first",
                action=self.name,
            )

        # Validate required user fields
        for field in ("name", "email"):
            if not user.get(field):
                raise BusinessException(
                    f"User {user.get('id', 'unknown')} missing required field: {field}",
                    action=self.name,
                )
        if user.get("id") is None:
            raise BusinessException(
                f"User missing required field: id",
                action=self.name,
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

        ctx.data[KEY_ENRICHED_RECORD] = enriched
