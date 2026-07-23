from __future__ import annotations

from copy import deepcopy

import requests

from rpacore import ProcessContext, Skill, SystemException
from skills import API_MODE_FIXTURE, API_MODES, fetch_json

POSTS_URL = "https://jsonplaceholder.typicode.com/posts"
FIXTURE_POSTS = [
    {
        "id": 1,
        "title": "Deterministic API batch example",
        "body": "A valid post processed entirely from local fixture data.",
        "userId": 1,
    },
    {
        "id": 2,
        "title": "",
        "body": "Invalid fixture record skipped by BusinessException(stop=True).",
        "userId": 2,
    },
    {
        "id": 3,
        "title": "Second valid fixture post",
        "body": "Another valid post to show the batch continues after bad input.",
        "userId": 1,
    },
]


class FetchPosts(Skill):
    """Fetch all posts from JSONPlaceholder /posts endpoint."""

    def execute(self, ctx: ProcessContext) -> None:
        api_mode = ctx.require_config("api_mode", str, action=self.name)
        if api_mode not in API_MODES:
            raise SystemException(
                f"Config key 'api_mode' must be one of {sorted(API_MODES)}, got {api_mode!r}",
                action=self.name,
            )
        if api_mode == API_MODE_FIXTURE:
            ctx.state["posts"] = deepcopy(FIXTURE_POSTS)
            return

        posts = fetch_json(
            POSTS_URL,
            action=self.name,
            resource="posts",
            request_get=requests.get,
        )
        if not isinstance(posts, list) or any(
            not isinstance(post, dict) for post in posts
        ):
            raise SystemException(
                "Posts response must be a JSON array of objects",
                action=self.name,
                code="rest_api_batch.http.invalid_response",
            )
        ctx.state["posts"] = posts
