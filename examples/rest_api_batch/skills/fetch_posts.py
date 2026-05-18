from __future__ import annotations

import requests

from oref import ProcessContext, Skill, SystemException

POSTS_URL = "https://jsonplaceholder.typicode.com/posts"


class FetchPosts(Skill):
    """Fetch all posts from JSONPlaceholder /posts endpoint."""

    def execute(self, ctx: ProcessContext) -> None:
        try:
            resp = requests.get(POSTS_URL, timeout=30)
            resp.raise_for_status()
            ctx.data["posts"] = resp.json()
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
