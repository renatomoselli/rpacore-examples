from __future__ import annotations

from rpacore import BusinessException, ProcessContext, Skill, SystemException


class ValidatePost(Skill):
    """Validate that a post has non-empty title and body."""

    def execute(self, ctx: ProcessContext) -> None:
        post = ctx.require_state("current_post", dict, action=self.name)

        title = post.get("title")
        if not title or not str(title).strip():
            raise BusinessException(
                f"Post {post.get('id', 'unknown')} has empty or missing title: {title!r}",
                action=self.name, stop=True,
            )

        body = post.get("body")
        if not body or not str(body).strip():
            raise BusinessException(
                f"Post {post.get('id', 'unknown')} has empty or missing body: {body!r}",
                action=self.name, stop=True,
            )

        user_id = post.get("userId")
        if user_id is None:
            raise BusinessException(
                f"Post {post.get('id', 'unknown')} has missing userId",
                action=self.name, stop=True,
            )
