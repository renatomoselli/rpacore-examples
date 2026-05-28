from __future__ import annotations

import json

import requests

from oref import ProcessContext, Skill, SystemException
from skills import KEY_CURRENT_POST, KEY_CURRENT_USER

USERS_URL = "https://jsonplaceholder.typicode.com/users"


class FetchUser(Skill):
    """Fetch a single user record from JSONPlaceholder /users/{userId} endpoint."""

    def execute(self, ctx: ProcessContext) -> None:
        post = ctx.data.get(KEY_CURRENT_POST)
        if post is None:
            raise SystemException(
                "No current_post in context — fetch_posts must run first",
                action=self.name,
            )

        user_id = post.get("userId")
        if user_id is None:
            raise SystemException(
                f"Post has no userId: {post}",
                action=self.name,
            )

        try:
            resp = requests.get(f"{USERS_URL}/{user_id}", timeout=30)
            resp.raise_for_status()
            ctx.data[KEY_CURRENT_USER] = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise SystemException(
                f"Invalid JSON in user {user_id} response: {exc}",
                action=self.name,
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise SystemException(
                f"HTTP error fetching user {user_id}: {exc.response.status_code} — {exc.response.reason}",
                action=self.name,
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise SystemException(
                f"Connection error fetching user {user_id}: {exc}",
                action=self.name,
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise SystemException(
                f"Timeout fetching user {user_id}: {exc}",
                action=self.name,
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise SystemException(
                f"Error fetching user {user_id}: {exc}",
                action=self.name,
            ) from exc
