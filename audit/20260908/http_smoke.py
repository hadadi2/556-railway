"""Audit-owned real-server read-only HTTP/asset smoke; no paid providers."""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
_candidates = [p for p in HERE.parents if (p / "silk_missions.py").is_file()]
ROOT = Path(os.environ.get("SILK_AUDIT_REPO", str(_candidates[0] if _candidates else HERE.parent / "silk-audit-8143125"))).resolve()
OUT = Path(os.environ.get("SILK_AUDIT_OUTPUT_DIR", str(HERE))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
for key in list(os.environ):
    if key.startswith(("SILK_", "ANTHROPIC_", "COMTRADE_", "SEARCH_API_")) or key == "DATABASE_URL":
        os.environ.pop(key, None)
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
os.chdir(ROOT)
from live_shape_server import LiveShapeServer

rows = []
with LiveShapeServer(platform=True) as server:
    paths = ["/", "/health", "/ready", "/config", "/markets", "/platform.html", "/pricing.html",
             "/checkout.html", "/silk-logo.png", "/fonts/fonts.css", "/research-motion.css", "/marketing.js"]
    paths += ["/fonts/" + p.name for p in sorted((ROOT / "web" / "fonts").glob("*.woff2"))]
    for path in paths:
        try:
            with urllib.request.urlopen(server.base_url + path, timeout=10) as response:
                rows.append({"path": path, "status": response.status, "bytes": len(response.read()),
                    "content_type": response.headers.get("Content-Type")})
        except urllib.error.HTTPError as exc:
            rows.append({"path": path, "status": exc.code})
    assert all(r["status"] == 200 for r in rows), rows
OUT.joinpath("http-smoke.json").write_text(json.dumps({"scope": "audit-owned real uvicorn; seeded temp databases; read-only HTTP",
    "checks": rows}, indent=2))
print(json.dumps({"http_checks": len(rows), "all_200": True, "server_stopped": True}))
