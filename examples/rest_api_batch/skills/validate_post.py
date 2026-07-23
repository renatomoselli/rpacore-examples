from __future__ import annotations

from rpacore import BusinessException, ProcessContext, Skill, SystemException


class ValidatePost(Skill):
    """Validate that a post has non-empty title and body."""

    def execute(self, ctx: ProcessContext) -> None:
        post = ctx.require_state("current_post", dict, action=self.name)

        title = post.get("title")
        if not isinstance(title, str) or not title.strip():
            raise BusinessException(
                f"Post {post.get('id', 'unknown')} has empty or missing title: {title!r}",
                action=self.name, stop=True, code="rest_api_batch.post.invalid",
            )

        body = post.get("body")
        if not isinstance(body, str) or not body.strip():
            raise BusinessException(
                f"Post {post.get('id', 'unknown')} has empty or missing body: {body!r}",
                action=self.name, stop=True, code="rest_api_batch.post.invalid",
            )

        user_id = post.get("userId")
        if type(user_id) is not int or user_id <= 0:
            raise BusinessException(
                f"Post {post.get('id', 'unknown')} has invalid or missing userId: {user_id!r}",
                action=self.name, stop=True, code="rest_api_batch.post.invalid",
            )
