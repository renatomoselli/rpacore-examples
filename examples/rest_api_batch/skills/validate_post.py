from __future__ import annotations

from oref import BusinessException, ProcessContext, Skill, SystemException
from skills import KEY_CURRENT_POST


class ValidatePost(Skill):
    """Validate that a post has non-empty title and body."""

    def execute(self, ctx: ProcessContext) -> None:
        post = ctx.data.get(KEY_CURRENT_POST)
        if post is None:
            raise SystemException(
                "No current_post in context — fetch_posts must run first",
                action=self.name,
            )

        title = post.get("title")
        if not title or not str(title).strip():
            raise BusinessException(
                f"Post {post.get('id', 'unknown')} has empty or missing title: {title!r}",
                action=self.name,
            )

        body = post.get("body")
        if not body or not str(body).strip():
            raise BusinessException(
                f"Post {post.get('id', 'unknown')} has empty or missing body: {body!r}",
                action=self.name,
            )
