"""مفتاح إعادة الشبكة لا يخصّص دراسة ثانية — durable replay tests."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_parallel_claim_one_winner_and_atomic_analysis_binding(tmp_path, monkeypatch):
    import silk_request_identity as identity
    import silk_storage
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setenv("SILK_DB", str(tmp_path / "runs.db"))
    silk_storage.init_db()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: identity.claim("request1", "owner", {"product": "Dates"}), range(20)))
    assert sum(old is None for _, old, _ in results) == 1
    key = results[0][0]
    with identity.bind(key):
        aid = silk_storage.create_research_run("Dates", "NLD", "080410", {})
    assert identity.claim("request1", "owner", {"product": "Dates"})[1]["analysis_id"] == aid
    assert identity.claim("request1", "owner", {"product": "Milk"})[2]
    assert identity.claim("request1", "other", {"product": "Dates"})[1] is None


def test_resume_identity_cannot_change_product_or_hs():
    from silk_request_identity import resume_mismatches
    old = {"product": "Milk", "hs_code": "040120"}
    assert resume_mismatches({"product": "Dates", "hs_code": "080410"}, old) == ["product", "hs_code"]
    assert resume_mismatches({"product": " milk "}, old) == []
    assert resume_mismatches({"product_card": {"cost_per_unit": 1, "unit": "kg"}},
                             {"product_card": {"cost_per_unit": 1, "unit": "kg", "own_price": 20}}) == []
    assert resume_mismatches({"lang": "ar"}, old) == []  # language is not an inferred product identity


def test_http_retry_after_engine_failure_does_not_start_second_study(tmp_path, monkeypatch):
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    import api
    import silk_missions
    import silk_storage
    monkeypatch.setenv("SILK_DB", str(tmp_path / "http.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-test-key")
    monkeypatch.setenv("SILK_API_KEY", "offline-test-key")
    body = {"product": "Dates", "hs_code": "080410", "hs_confirmed": True, "market": "Netherlands", "persist": True, "allow_degraded": True}
    headers = {"X-API-Key": "offline-test-key", "Idempotency-Key": "same-request"}
    with patch("requests.get", side_effect=OSError("net blocked")), patch("requests.post", side_effect=OSError("net blocked")), patch("requests.sessions.Session.request", side_effect=OSError("net blocked")), patch.object(silk_missions, "deep_research", side_effect=RuntimeError("engine boundary")) as engine:
        client = TestClient(api.app, raise_server_exceptions=False)
        first = client.post("/research", headers=headers, json=body)
        second = client.post("/research", headers=headers, json=body)
    assert first.status_code == 500
    assert second.status_code in {202, 500}
    assert engine.call_count == 1
    with silk_storage._open(silk_storage._db_path()) as conn:
        assert conn.execute("SELECT count(*) FROM analyses").fetchone()[0] == 1
