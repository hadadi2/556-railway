"""Fresh-database, HS, source-asset and JavaScript checks, without external APIs.

Use SILK_AUDIT_REPO to select the checkout. SILK_AUDIT_LOCAL_URL is optional
and must be an audit-owned loopback server. Output stays beside this script.
"""
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import urljoin, urlparse
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
_candidates = [p for p in HERE.parents if (p / "silk_missions.py").is_file()]
ROOT = Path(os.environ.get("SILK_AUDIT_REPO", str(_candidates[0] if _candidates else HERE.parent / "silk-audit-8143125"))).resolve()
OUT = Path(os.environ.get("SILK_AUDIT_OUTPUT_DIR", str(HERE))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
LOCAL_URL = os.environ.get("SILK_AUDIT_LOCAL_URL", "")
for key in list(os.environ):
    if key.startswith(("SILK_", "ANTHROPIC_", "COMTRADE_", "SEARCH_API_")) or key == "DATABASE_URL":
        os.environ.pop(key, None)
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
result = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()}

def schema(conn):
    objects = [dict(zip(("type", "name", "table", "sql"), row)) for row in conn.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
    tables = {}
    for obj in objects:
        if obj["type"] != "table" or obj["name"].startswith("sqlite_"):
            continue
        name = obj["name"]
        assert re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name)
        tables[name] = {"columns": [list(r) for r in conn.execute(f"PRAGMA table_info({name})")],
                        "foreign_keys": [list(r) for r in conn.execute(f"PRAGMA foreign_key_list({name})")],
                        "indexes": [list(r) for r in conn.execute(f"PRAGMA index_list({name})")]}
    return {"objects": objects, "tables": tables,
            "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
            "busy_timeout_ms": conn.execute("PRAGMA busy_timeout").fetchone()[0],
            "foreign_keys_enabled": conn.execute("PRAGMA foreign_keys").fetchone()[0],
            "synchronous": conn.execute("PRAGMA synchronous").fetchone()[0],
            "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_check": [list(r) for r in conn.execute("PRAGMA foreign_key_check")]}

with tempfile.TemporaryDirectory(prefix="silk-forensic-check-") as tmp:
    os.environ.update({"SILK_DATA_DIR": tmp, "SILK_TRACE_DIR": tmp + "/traces",
        "SILK_PLATFORM_RUN_SUPERVISOR": "0", "SILK_PLATFORM_ORPHAN_SWEEP": "0",
        "SILK_RESEARCH_RUN_SUPERVISOR": "0"})
    from silk_platform import db
    import silk_store as store
    import silk_storage as storage
    import silk_usage as usage
    result["migrations"] = {"platform_first": db.apply_migrations(), "platform_second": db.apply_migrations(),
                            "store_first": store.migrate(), "store_second": store.migrate()}
    result["migration_files"] = [{"file": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted((ROOT / "migrations").rglob("*.sql"))]
    storage.init_db(force=True)
    result["databases"] = {}
    for name, factory in [("platform", db.connect), ("store", store.connect),
                          ("analysis", lambda: storage._connect(storage._db_path())),
                          ("usage", lambda: usage._connect(usage._db_path()))]:
        conn = factory()
        result["databases"][name] = schema(conn)
        conn.close()
    assert len(result["migrations"]["platform_first"]) == 21
    assert len(result["migrations"]["store_first"]) == 5
    assert not result["migrations"]["platform_second"] and not result["migrations"]["store_second"]
    assert all(d["integrity"] == "ok" and not d["foreign_key_check"] for d in result["databases"].values())
    import silk_hs_pipeline as hs
    cases = [("تمر", None, False), ("Dates", None, False), ("حليب", None, False),
             ("Milk", None, False), ("", None, False), ("Fixture", "12A456", True),
             ("Dates", "000000", False), ("Dates", "000000", True),
             ("Dates", "080410", True), ("Dates", "٠٨٠٤١٠", True)]
    result["hs_cases"] = []
    with patch("requests.sessions.Session.request", side_effect=OSError("offline audit")):
        for product, catalog, confirmed in cases:
            out = hs.classify(product, catalog, hs_confirmed=confirmed, allow_web=False, allow_claude=False)
            result["hs_cases"].append({"input": {"product": product, "catalog": catalog, "confirmed": confirmed},
                "output": {k: out.get(k) for k in ("final_hs_code", "classification_status", "classification_method",
                    "confidence", "contradictions", "official_hs_description", "reason")}})

class SourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.refs, self.assets, self.scripts, self.agents = [], [], [], [], []
        self._script = None
    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        for a in ("aria-describedby", "aria-labelledby"):
            self.refs.extend(attrs.get(a, "").split())
        if attrs.get("data-agent"):
            self.agents.append(attrs["data-agent"])
        if tag == "script":
            self._script = [] if not attrs.get("src") and attrs.get("type", "") not in ("application/ld+json", "application/json") else None
        if tag in ("img", "script") and attrs.get("src"):
            self.assets.append(attrs["src"])
        if tag == "link" and attrs.get("rel") in ("stylesheet", "icon") and attrs.get("href"):
            self.assets.append(attrs["href"])
    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append("".join(self._script))
            self._script = None

result["frontend_sources"], scripts, assets = [], [], set()
for path in sorted((ROOT / "web").glob("*.html")):
    parser = SourceParser()
    body = path.read_text()
    parser.feed(body)
    scripts.extend((str(path.relative_to(ROOT)) + f":inline-{i+1}", js) for i, js in enumerate(parser.scripts))
    assets.update(parser.assets)
    result["frontend_sources"].append({"file": str(path.relative_to(ROOT)),
        "duplicate_ids": sorted({x for x in parser.ids if parser.ids.count(x) > 1}),
        "missing_aria_targets_static": sorted(set(parser.refs) - set(parser.ids)),
        "researchCaption_occurrences": body.count("researchCaption"), "data_agents": parser.agents,
        "inline_scripts": len(parser.scripts)})
scripts.extend((str(p.relative_to(ROOT)), p.read_text()) for p in (ROOT / "web").glob("*.js"))
result["javascript_syntax"] = []
for label, script in scripts:
    proc = subprocess.run(["node", "--check", "-"], input=script, text=True, capture_output=True)
    result["javascript_syntax"].append({"source": label, "returncode": proc.returncode, "stderr": proc.stderr})
result["local_assets"] = []
for asset in sorted(assets):
    if urlparse(asset).scheme or asset.startswith("data:"):
        continue
    target = ROOT / "web" / asset.lstrip("/").split("?")[0]
    result["local_assets"].append({"url": asset, "exists": target.is_file()})
result["researchCaption_all_web"] = [str(p.relative_to(ROOT)) for p in (ROOT / "web").rglob("*")
    if p.suffix in (".html", ".css", ".js", ".json") and "researchCaption" in p.read_text(errors="replace")]
if LOCAL_URL:
    assert urlparse(LOCAL_URL).hostname in ("127.0.0.1", "localhost", "::1")
    import requests
    result["local_http"] = []
    paths = ["/", "/health", "/config", "/markets", "/platform.html", "/pricing.html", "/checkout.html",
             "/silk-logo.png", "/fonts/fonts.css", "/research-motion.css", "/marketing.js"]
    paths += ["/fonts/" + p.name for p in (ROOT / "web" / "fonts").glob("*.woff2")]
    for path in paths:
        try:
            response = requests.get(urljoin(LOCAL_URL, path), timeout=5)
            result["local_http"].append({"path": path, "status": response.status_code,
                "content_type": response.headers.get("Content-Type"), "bytes": len(response.content)})
        except requests.RequestException as exc:
            result["local_http"].append({"path": path, "error": type(exc).__name__})
OUT.joinpath("forensic-checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({"migrations": result["migrations"],
    "db_tables": {k: len(v["tables"]) for k, v in result["databases"].items()},
    "hs": result["hs_cases"], "frontend": result["frontend_sources"],
    "js_checked": len(result["javascript_syntax"]), "js_errors": sum(x["returncode"] != 0 for x in result["javascript_syntax"]),
    "missing_assets": [x for x in result["local_assets"] if not x["exists"]],
    "http": result.get("local_http", [])}, ensure_ascii=False, indent=2))
