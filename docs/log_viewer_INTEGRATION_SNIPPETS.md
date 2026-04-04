# Small integration snippets

These are intentionally tiny because the exact target files vary across TAKS revisions.

## 1) API registration

Example pattern:

```python
from fastapi import FastAPI
from takctl.web.api.logs import router as logs_router

app = FastAPI()
app.include_router(logs_router)
```

## 2) Index / component loading

```html
<script src="components/LogsViewer.js?v=20260404a"></script>
```

## 3) Menu entry

```javascript
{
  key: 'logs',
  label: 'Logs',
  onClick: function () {
    renderLogsPage(document.getElementById('app-main'));
  }
}
```

## 4) Page mount

```javascript
function renderLogsPage(mainEl) {
  mainEl.innerHTML = '';
  window.TaksLogsViewer.mount(mainEl);
}
```

## 5) Optional route wiring

If your shell has a page switch/router:

```javascript
if (route === 'logs') {
  renderLogsPage(mainEl);
  return;
}
```
