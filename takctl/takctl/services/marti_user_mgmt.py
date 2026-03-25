from __future__ import annotations

from typing import Any

import requests

from takctl.services.marti_api import _base_url, get_auth_header


def _json_or_text(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return r.text


def _request(method: str, path: str, *, json_body: dict | None = None, timeout: int = 20) -> Any:
    base = _base_url()
    url = f"{base}/" + str(path or "").lstrip("/")
    hdr = dict(get_auth_header())
    hdr["Accept"] = "application/json"

    r = requests.request(
        method=method.upper(),
        url=url,
        headers=hdr,
        json=json_body,
        timeout=timeout,
        verify=False,
    )

    if r.status_code in (401, 403):
        hdr = dict(get_auth_header(force_refresh=True))
        hdr["Accept"] = "application/json"
        r = requests.request(
            method=method.upper(),
            url=url,
            headers=hdr,
            json=json_body,
            timeout=timeout,
            verify=False,
        )

    data = _json_or_text(r)
    if not r.ok:
        raise RuntimeError(f"Marti {method.upper()} {path} failed: HTTP {r.status_code}: {data}")
    return data


def create_or_update_user(
    *,
    username: str,
    password: str,
    group_list: list[str] | None = None,
    group_list_in: list[str] | None = None,
    group_list_out: list[str] | None = None,
) -> Any:
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
    return _request(
        "DELETE",
        f"/user-management/api/delete-user/{username}",
    )
