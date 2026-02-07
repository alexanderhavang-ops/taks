set -euo pipefail
U="enrolltest"   # or whatever you know exists
read -r -s -p "password: " P; echo

python3 - <<PY
import base64, ssl, urllib.request
u = "$U"
p = "$P"
auth = base64.b64encode(f"{u}:{p}".encode()).decode()
req = urllib.request.Request("https://127.0.0.1:8447/Marti/api/version", method="GET")
req.add_header("Authorization", f"Basic {auth}")
ctx = ssl._create_unverified_context()
try:
    with urllib.request.urlopen(req, context=ctx, timeout=4) as r:
        print("OK:", getattr(r, "status", None))
        print(r.read(300))
except Exception as e:
    print("FAIL:", type(e).__name__, e)
PY

