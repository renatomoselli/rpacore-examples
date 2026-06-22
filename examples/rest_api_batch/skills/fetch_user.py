from __future__ import annotations

from copy import deepcopy

import requests

from rpacore import BusinessException, ProcessContext, Skill, SystemException
from skills import API_MODE_FIXTURE, API_MODES, fetch_json

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
        if type(user_id) is not int or user_id <= 0:
            raise BusinessException(
                f"Post has invalid or no userId: {user_id!r}",
                action=self.name, stop=True,
            )

        api_mode = ctx.require_config("api_mode", str, action=self.name)
        if api_mode not in API_MODES:
            raise SystemException(
                f"Config key 'api_mode' must be one of {sorted(API_MODES)}, got {api_mode!r}",
                action=self.name,
            )
        if api_mode == API_MODE_FIXTURE:
            user = FIXTURE_USERS.get(user_id)
            if user is None:
                raise BusinessException(
                    f"Post {post.get('id', 'unknown')} references unknown userId: {user_id!r}",
                    action=self.name, stop=True,
                )
            ctx.state["current_user"] = deepcopy(user)
            return

        user = fetch_json(
            f"{USERS_URL}/{user_id}",
            action=self.name,
            resource=f"user {user_id}",
            request_get=requests.get,
        )
        if not isinstance(user, dict) or any(
            field not in user for field in ("id", "name", "email")
        ):
            raise SystemException(
                f"Invalid user {user_id} response: expected an object with id, name, and email",
                action=self.name,
            )
        returned_user_id = user["id"]
        if (
            type(returned_user_id) is not int
            or returned_user_id <= 0
            or returned_user_id != user_id
        ):
            raise SystemException(
                f"Invalid user {user_id} response: mismatched id {returned_user_id!r}",
                action=self.name,
            )
        address = user.get("address")
        if address is not None and not isinstance(address, dict):
            raise SystemException(
                f"Invalid user {user_id} response: address must be an object",
                action=self.name,
            )
        ctx.state["current_user"] = user
