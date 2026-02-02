const __apiCache = new Map();

/**
 * useApi(url, opts?)
 * opts:
 *   - pollMs: number | 0   (re-fetch every pollMs; 0 disables)
 *   - cacheMs: number | 0  (serve cached data if younger than cacheMs)
 */
function useApi(url, opts) {
  opts = opts || {};
  const pollMs  = Number(opts.pollMs || 0);
  const cacheMs = Number(opts.cacheMs || 0);

  const [state, setState] = React.useState({ loading: true, data: null, error: null });

  React.useEffect(() => {
    if (!url) {
      setState({ loading: false, data: null, error: "Missing URL" });
      return;
    }

    let alive = true;
    const ac = new AbortController();

    async function run() {
      // Cache hit?
      if (cacheMs > 0 && __apiCache.has(url)) {
        const hit = __apiCache.get(url);
        if (hit && (Date.now() - hit.t) <= cacheMs) {
          alive && setState({ loading: false, data: hit.data, error: null });
          return;
        }
      }

      alive && setState(s => ({ loading: true, data: s.data, error: null }));

      try {
        const r = await fetch(url, {
          signal: ac.signal,
          headers: { "Accept": "application/json" }
        });

        const t = await r.text();
        let j = null;
        try { j = t ? JSON.parse(t) : null; } catch (e) {}

        if (!r.ok) {
          throw new Error((j && (j.detail || j.error)) || t || (r.status + " " + r.statusText));
        }

        __apiCache.set(url, { t: Date.now(), data: j });
        alive && setState({ loading: false, data: j, error: null });
      } catch (err) {
        if (String(err && err.name) === "AbortError") return;
        alive && setState({ loading: false, data: null, error: String(err.message || err) });
      }
    }

    run();

    let timer = null;
    if (pollMs > 0) {
      timer = setInterval(run, pollMs);
    }

    return () => {
      alive = false;
      if (timer) clearInterval(timer);
      ac.abort();
    };
  }, [url, pollMs, cacheMs]);

  return state;
}
