from __future__ import annotations

from typing import Any, Dict, List


def _norm_token(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def _copy_match(match: Dict[str, Any], *, match_mode: str, match_rank: int) -> Dict[str, Any]:
    out = dict(match or {})
    out["match_mode"] = match_mode
    out["match_rank"] = int(match_rank)
    return out


def _device_out(device: Dict[str, Any], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    out = {
        "client_uid": device.get("client_uid"),
        "observed_callsign": device.get("observed_callsign"),
        "state": device.get("state"),
        "last_cot_time": device.get("last_cot_time"),
        "voice": {
            "connected_now": any(bool(m.get("connected_now")) for m in matches),
            "matched_n": len(matches),
            "channel_names": sorted(
                {
                    str(m.get("channel_name") or "").strip()
                    for m in matches
                    if str(m.get("channel_name") or "").strip()
                }
            ),
            "best_match_mode": (matches[0].get("match_mode") if matches else None),
            "matches": matches,
        },
    }
    return out


def _ranked_device_matches_for_voice_user(
    *,
    voice_user: Dict[str, Any],
    devices: List[Dict[str, Any]],
) -> List[tuple[int, Dict[str, Any]]]:
    ranked: List[tuple[int, Dict[str, Any]]] = []

    voice_callsign_norm = _norm_token(voice_user.get("callsign"))
    voice_suffix_norm = _norm_token(voice_user.get("suffix_candidate"))

    exact_callsign_devices = []
    exact_callsign_current_devices = []

    for d in devices:
        client_uid_norm = _norm_token(d.get("client_uid"))
        observed_callsign_norm = _norm_token(d.get("observed_callsign"))
        state = str(d.get("state") or "").strip().lower()

        if voice_suffix_norm and client_uid_norm and voice_suffix_norm == client_uid_norm:
            ranked.append((400, dict(d)))
            continue

        if voice_callsign_norm and observed_callsign_norm and voice_callsign_norm == observed_callsign_norm:
            exact_callsign_devices.append(dict(d))
            if state == "current":
                exact_callsign_current_devices.append(dict(d))

    if len(exact_callsign_current_devices) == 1:
        ranked.append((250, exact_callsign_current_devices[0]))
    elif len(exact_callsign_devices) == 1:
        ranked.append((200, exact_callsign_devices[0]))

    if not ranked and len(devices) == 1 and voice_callsign_norm:
        only = dict(devices[0])
        observed_callsign_norm = _norm_token(only.get("observed_callsign"))
        if observed_callsign_norm and observed_callsign_norm == voice_callsign_norm:
            ranked.append((100, only))

    dedup: Dict[str, tuple[int, Dict[str, Any]]] = {}
    for rank, d in ranked:
        key = str(d.get("client_uid") or "").strip() + "\x1f" + str(d.get("observed_callsign") or "").strip()
        prev = dedup.get(key)
        if prev is None or rank > prev[0]:
            dedup[key] = (rank, d)

    out = list(dedup.values())
    out.sort(
        key=lambda x: (
            -int(x[0]),
            str((x[1] or {}).get("state") or ""),
            str((x[1] or {}).get("last_cot_time") or ""),
            str((x[1] or {}).get("client_uid") or ""),
        )
    )
    return out


def build_voice_assignment(
    *,
    username: str,
    header_callsign: str,
    devices: List[Dict[str, Any]],
    mumble_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    snap = dict(mumble_snapshot or {})
    server = dict(snap.get("server") or {})
    live_users = list(snap.get("users") or [])

    configured_callsign_norm = _norm_token(header_callsign)
    username_norm = _norm_token(username)

    configured_matches: List[Dict[str, Any]] = []
    username_matches: List[Dict[str, Any]] = []
    device_matches_by_key: Dict[str, List[Dict[str, Any]]] = {}

    for vu in live_users:
        voice_callsign_norm = _norm_token(vu.get("callsign"))
        voice_name_norm = _norm_token(vu.get("name"))

        if configured_callsign_norm and voice_callsign_norm == configured_callsign_norm:
            configured_matches.append(_copy_match(vu, match_mode="configured_callsign", match_rank=120))

        if username_norm and (voice_name_norm == username_norm or voice_callsign_norm == username_norm):
            username_matches.append(_copy_match(vu, match_mode="username", match_rank=300))

        # Important: always try device matching.
        #
        # Mumble/Vx names are usually callsign-based:
        #   EAPQ2---<vx-local-uuid>
        #
        # The suffix is not necessarily the TAK/CoT client_uid, so the most useful
        # signal is often observed CoT callsign. Do not gate this behind the
        # configured/header callsign, because configured callsign can differ from
        # what the TAK client is actually emitting.
        ranked_devices = _ranked_device_matches_for_voice_user(
            voice_user=vu,
            devices=devices,
        )

        for rank, device in ranked_devices:
            key = str(device.get("client_uid") or "").strip() + "\x1f" + str(device.get("observed_callsign") or "").strip()
            if rank >= 400:
                mode = "client_uid_suffix"
            elif rank >= 250:
                mode = "observed_callsign_unique_current"
            elif rank >= 200:
                mode = "observed_callsign_unique_device"
            else:
                mode = "single_device_callsign"

            device_matches_by_key.setdefault(key, []).append(
                _copy_match(vu, match_mode=mode, match_rank=rank)
            )

    configured_matches.sort(
        key=lambda m: (
            -int(m.get("match_rank") or 0),
            str(m.get("channel_name") or ""),
            str(m.get("name") or ""),
        )
    )
    username_matches.sort(
        key=lambda m: (
            -int(m.get("match_rank") or 0),
            str(m.get("channel_name") or ""),
            str(m.get("name") or ""),
        )
    )

    devices_out: List[Dict[str, Any]] = []
    device_user_matches: List[Dict[str, Any]] = []

    for d in devices:
        key = str(d.get("client_uid") or "").strip() + "\x1f" + str(d.get("observed_callsign") or "").strip()
        matches = list(device_matches_by_key.get(key) or [])
        matches.sort(
            key=lambda m: (
                -int(m.get("match_rank") or 0),
                str(m.get("channel_name") or ""),
                str(m.get("name") or ""),
            )
        )
        device_user_matches.extend(matches)
        devices_out.append(_device_out(d, matches))

    all_matches: List[Dict[str, Any]] = []
    seen_match_keys = set()
    for m in username_matches + configured_matches + device_user_matches:
        k = (
            str(m.get("name") or ""),
            str(m.get("session") or ""),
            str(m.get("channel_name") or ""),
            str(m.get("match_mode") or ""),
        )
        if k in seen_match_keys:
            continue
        seen_match_keys.add(k)
        all_matches.append(m)

    all_matches.sort(
        key=lambda m: (
            -int(m.get("match_rank") or 0),
            str(m.get("channel_name") or ""),
            str(m.get("name") or ""),
        )
    )

    user_channel_names = sorted(
        {
            str(m.get("channel_name") or "").strip()
            for m in all_matches
            if str(m.get("channel_name") or "").strip()
        }
    )

    connected_now = any(bool(m.get("connected_now")) for m in all_matches)

    out = {
        "ok": True,
        "username": str(username or "").strip(),
        "server": {
            "host": server.get("host"),
            "port": server.get("port"),
            "connected": bool(server.get("connected")),
        },
        "snapshot_meta": {
            "source": str((snap.get("meta") or {}).get("source") or "takctl.services.mumble_live"),
            "generated_at": (snap.get("meta") or {}).get("generated_at"),
        },
        "error": snap.get("error"),
        "user": {
            "callsign": str(header_callsign or "").strip(),
            "configured_callsign": str(header_callsign or "").strip(),
            "connected_now": connected_now,
            "channel_names": user_channel_names,
            "matched_user_names": [str(m.get("name") or "") for m in all_matches],
            "header_matches": configured_matches,
            "configured_matches": configured_matches,
            "username_matches": username_matches,
            "matches": all_matches,
        },
        "devices": devices_out,
        "raw_counts": {
            "channels": len(list(snap.get("channels") or [])),
            "users": len(live_users),
            "devices": len(devices_out),
        },
    }

    return out
