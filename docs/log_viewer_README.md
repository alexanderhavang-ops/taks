# TAKS log viewer v1

This drop-in adds a read-only log browser for `takctl-web`.

## What it does

- Browses `/var/log` recursively, one directory at a time
- Hides `*.gz`
- Clicking a directory opens that directory
- Clicking a file shows the last 1000 lines by default
- Button to load the full file
- Strict path jail: everything resolves under `/var/log`

## Files in this bundle

- `takctl/takctl/web/api/logs.py`
- `takctl/web/components/LogsViewer.js`

## Backend integration

Wherever the FastAPI app currently includes the other takctl web routers, add this import and include:

```python
from takctl.web.api.logs import router as logs_router

app.include_router(logs_router)
```

If your import style is relative inside the package, adjust to match your existing patterns.

## Frontend integration

Add the component script to the main takctl web page, alongside the other components:

```html
<script src="components/LogsViewer.js?v=20260404a"></script>
```

Then add a nav entry in the existing shell/menu. The exact file depends on your current app shell, but the page mount can stay very small:

```javascript
function renderLogsPage(mainEl) {
  window.TaksLogsViewer.mount(mainEl);
}
```

Bind that to a menu item such as `Logs`.

## Permissions

The web service must be able to read `/var/log`. The clean approach is usually to add the service to `adm` via the source-owned systemd unit definition:

```ini
[Service]
SupplementaryGroups=adm
```

Then redeploy the unit through the installer and restart `takctl-web`.

Why this is better than sudo:

- still read-only from the app side
- no command execution path
- simpler auditing

## Suggested smoke tests

### List root

```bash
curl -fsS http://127.0.0.1:8080/api/logs/list?path=/ | python3 -m json.tool | sed -n '1,120p'
```

### Read tail of syslog

```bash
curl -fsS 'http://127.0.0.1:8080/api/logs/read?path=/syslog&mode=tail&lines=20' \
  | python3 -c 'import json,sys;o=json.load(sys.stdin); print(o["path"]); print(o["content"][:2000])'
```

### Directory traversal should fail

```bash
curl -i 'http://127.0.0.1:8080/api/logs/list?path=/../../etc'
```

Expected: HTTP 400.

## Notes

- The backend currently includes symlinks only when the resolved target remains under `/var/log`.
- Non-regular files and special devices are skipped.
- `mode=full` intentionally returns plain text only. No highlighting or parsing.
- If you want, the next obvious v2 is server-side pagination by byte offset for very large files, but this v1 matches the behavior you asked for.
