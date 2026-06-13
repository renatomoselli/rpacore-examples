from __future__ import annotations

from copy import deepcopy
import json

import requests

from rpacore import BusinessException, ProcessContext, Skill, SystemException
from skills import API_MODE_FIXTURE

USERS_URL = "https://jsonplaceholder.typicode.com/users"
FIXTURE_USERS = {
    1: {
        "id": 1,
        "name": "Leanne Graham",
        "email": "leanne@example.test",
        "address": {"city": "Gwenborough"},
    },
    2: {
        "id": 2,
        "name": "Clementine Bauch",
        "email": "clementine@example.test",
        "address": {"city": "South Elvis"},
    },
}


class FetchUser(Skill):
    """Fetch a single user record from JSONPlaceholder /users/{userId} endpoint."""

    def execute(self, ctx: ProcessContext) -> None:
        post = ctx.require_state("current_post", dict, action=self.name)

        user_id = post.get("userId")
        if user_id is None:
            raise BusinessException(
                f"Post has no userId: {post}",
                action=self.name, stop=True,
            )

        if ctx.config.get("api_mode") == API_MODE_FIXTURE:
            user = FIXTURE_USERS.get(user_id)
            if user is None:
                raise BusinessException(
                    f"Post {post.get('id', 'unknown')} references unknown userId: {user_id!r}",
                    action=self.name, stop=True,
                )
            ctx.state["current_user"] = deepcopy(user)
            return

        try:
            resp = requests.get(f"{USERS_URL}/{user_id}", timeout=30)
            resp.raise_for_status()
            ctx.state["current_user"] = resp.json()
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
