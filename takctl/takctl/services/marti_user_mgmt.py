from __future__ import annotations

from typing import Any

import requests

from takctl.services.marti_api import marti_request
from takctl.services.backing_user_store import build_backing_user_store, selected_backing_user_store


def _json_or_text(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return r.text


def _request(method: str, path: str, *, json_body: dict | None = None, timeout: int = 20) -> Any:
    r = marti_request(method, path, json_body=json_body, timeout=timeout)

    data = _json_or_text(r)
    if not r.ok:
        raise RuntimeError(f"Marti {method.upper()} request failed: HTTP {r.status_code}")
    return data


def create_or_update_user(
    *,
    username: str,
    password: str,
    group_list: list[str] | None = None,
    group_list_in: list[str] | None = None,
    group_list_out: list[str] | None = None,
) -> Any:
    if selected_backing_user_store() == "ldap":
        build_backing_user_store("ldap").ensure_user(username, password=password,
            groups=group_list, in_groups=group_list_in, out_groups=group_list_out)
        return {"ok": True, "username": username, "backing_user_store": "ldap"}
    return _request(
        "POST",
        "/user-management/api/new-user",
        json_body={
            "username": username,
            "password": password,
            "groupList": list(group_list or []),
            "groupListIN": list(group_list_in or []),
            "groupListOUT": list(group_list_out or []),
        },
    )


def change_user_password(*, username: str, password: str) -> Any:
    if selected_backing_user_store() == "ldap":
        build_backing_user_store("ldap").ensure_user(username, password=password, append=True)
        return {"ok": True, "username": username, "backing_user_store": "ldap"}
    return _request(
        "PUT",
        "/user-management/api/change-user-password",
        json_body={
            "username": username,
            "password": password,
        },
    )


def update_groups(
    *,
    username: str,
    group_list: list[str] | None = None,
    group_list_in: list[str] | None = None,
    group_list_out: list[str] | None = None,
) -> Any:
    if selected_backing_user_store() == "ldap":
        build_backing_user_store("ldap").ensure_user(username,
            groups=group_list, in_groups=group_list_in, out_groups=group_list_out)
        return {"ok": True, "username": username, "backing_user_store": "ldap"}
    return _request(
        "PUT",
        "/user-management/api/update-groups",
        json_body={
            "username": username,
            "groupList": list(group_list or []),
            "groupListIN": list(group_list_in or []),
            "groupListOUT": list(group_list_out or []),
        },
    )


def delete_user(*, username: str) -> Any:
    if selected_backing_user_store() == "ldap":
        build_backing_user_store("ldap").delete_user(username)
        return {"ok": True, "username": username, "backing_user_store": "ldap"}
    return _request(
        "DELETE",
        f"/user-management/api/delete-user/{username}",
    )
