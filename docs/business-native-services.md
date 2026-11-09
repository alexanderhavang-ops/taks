# Native service administration through Business MCP

Business MCP provides `taks_node_service_read(node_id, service, operation, arguments)` and `taks_node_service_write(..., confirm_write=True)`. Node-side operations use the authenticated TAKS Business domain and the services' existing local credentials. DevOps remains responsible for host services, logs and sockets.

| Service | Read operations | Write operations | Interface |
|---|---|---|---|
| LDAP | `users` (`limit`), `user`/`groups` (`username`) | `group_create`, `group_delete` (`group`); `user_groups_set` (`username`, `groups`) | Existing LDAP reader/writer with escaped DNs and filters |
| Mumble | `snapshot` | `channel_create` (`name`, `parent`); `channel_rename` (`channel_id`, `name`); `channel_delete` (`channel_id`) | Installed Mumble Ice API on loopback 6502, optional `server_id` default 1 |
| Openfire | `sessions`, `rooms`, `room`, `occupants` | `room_create`, `room_delete` (`room`); `room_subject_set` (`room`, `subject`) | Official REST API plugin on loopback admin console 9090; optional `chat_service` default `conference` |

LDAP account/password creation and reset use the canonical directory, including when initiated by the TAKS administrative user-management service. Openfire REST is used for Openfire-owned state, not for creating duplicate local accounts. Native writes require explicit confirmation, validate resource names, and are logged without credentials or payload contents. The LDAP administrator group and Mumble root channel cannot be deleted through these tools.

Mumble uses its single existing Ice secret; the installer grants the TAK service group read access to that file. The worker uses system Python's already installed Ice bindings, keeping the web venv independent of native Ice packaging.

Openfire REST API plugin 1.12.0 is pinned to SHA-256 `a1cd5b71437e5d6cd0bbf6a298537baa78f19a50f2104f4c1bb94595a350ccf6`, requires Openfire 5+, and is restricted to loopback clients. REST authenticates the existing LDAP administrator using the canonical TAK admin credential. No new Openfire API password is introduced. Room subject updates preserve other existing room settings.

Offline tests cover dispatch, read/write separation, confirmation, names, redaction, LDAP routing and native Mumble calls. Post-install live gates create/read/update/delete disposable LDAP groups, Mumble channels and Openfire rooms, cleaning up in `finally` blocks. They send no chat messages, invitations or user notifications. A failing gate prevents a successful installation result.
