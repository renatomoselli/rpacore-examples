from __future__ import annotations

from oref import ProcessContext, Skill


class EnrichRecord(Skill):
    """Merge post and user data into one enriched output record."""

    def execute(self, ctx: ProcessContext) -> None:
        post = ctx.data.get("current_post")
        user = ctx.data.get("current_user")

        if post is None:
            raise RuntimeError(
                "No current_post in context — fetch_posts must run first"
            )
        if user is None:
            raise RuntimeError(
                "No current_user in context — fetch_user must run first"
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

        ctx.data["enriched_record"] = enriched
