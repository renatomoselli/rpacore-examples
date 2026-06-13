from __future__ import annotations

from copy import deepcopy
import json

import requests

from rpacore import ProcessContext, Skill, SystemException
from skills import API_MODE_FIXTURE

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
        if ctx.config.get("api_mode") == API_MODE_FIXTURE:
            ctx.state["posts"] = deepcopy(FIXTURE_POSTS)
            return

        try:
            resp = requests.get(POSTS_URL, timeout=30)
            resp.raise_for_status()
            ctx.state["posts"] = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise SystemException(
                f"Invalid JSON in posts response: {exc}",
                action=self.name,
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise SystemException(
                f"HTTP error fetching posts: {exc.response.status_code} — {exc.response.reason}",
                action=self.name,
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise SystemException(
                f"Connection error fetching posts: {exc}",
                action=self.name,
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise SystemException(
                f"Timeout fetching posts: {exc}",
                action=self.name,
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise SystemException(
                f"Error fetching posts: {exc}",
                action=self.name,
            ) from exc
