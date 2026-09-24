"""طلب المالك (2026-09-24): رابطُ الخدمة المجرّد يفتح المنصّة `/platform`.

The bare service URL redirects to the platform; the operator dashboard stays
reachable as the same static file at `/index.html`. Hermetic.
"""
from fastapi.testclient import TestClient


def test_root_redirects_to_platform_and_dashboard_stays_reachable():
    import api
    c = TestClient(api.app)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/platform"
    h = c.head("/", follow_redirects=False)      # مراقباتُ الجاهزية تسأل بـHEAD
    assert h.status_code == 307 and h.headers["location"] == "/platform"
    page = c.get("/platform")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    dash = c.get("/index.html")
    assert dash.status_code == 200 and "<html" in dash.text.lower()
