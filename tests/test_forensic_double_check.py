"""إعادة التدقيق: أدلة غير مسندة وإعادة الطلب بعد رفض مؤقت."""
import os
import sys
import json
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from silk_data_layer import DataPoint
from silk_llm_runtime import _parse_output
from conftest import block_network


def parse(claim, point, **fields):
    finding = {"claim": claim, "datapoint_ids": ["dp1"], **fields}
    return _parse_output(json.dumps({"findings": [finding]}), {"dp1": point})


def test_currency_cannot_be_invented_when_source_unit_is_unknown():
    with block_network():
        out = parse("Imports 100 USD", DataPoint(100, "Source", .9))
    assert out["findings"] == []
    assert out["gaps"]


def test_magnitude_word_cannot_inflate_a_source_number():
    with block_network():
        for text in ("Imports 10 million USD", "الواردات ١٠ مليون USD"):
            assert not parse(text, DataPoint(10, "Source", .9, unit="USD"))["findings"]
            assert parse(text, DataPoint(10000000, "Source", .9, unit="USD"))["findings"]


@pytest.mark.parametrize("payload", [
    {"findings": 7},
    {"findings": [{"claim": "Observed", "datapoint_ids": 7}]},
    {"findings": [], "gaps": 7},
])
def test_malformed_provider_collections_become_declared_gaps(payload):
    with block_network():
        result = _parse_output(json.dumps(payload), {"dp1": DataPoint(100, "Source", .9)})
    assert result["findings"] == []
    assert result["gaps"]


def test_nonfinite_model_confidence_cannot_become_high_confidence():
    with block_network():
        out = parse("Observed 100", DataPoint(100, "Source", .9), confidence="NaN")
    assert out["findings"] == []
    assert out["gaps"]


def test_transient_admission_rejection_does_not_poison_idempotency_key(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import api
    import silk_research_runtime
    monkeypatch.setenv("SILK_DB", str(tmp_path / "retry.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-test-key")
    monkeypatch.setenv("SILK_API_KEY", "offline-test-key")
    body = {"product": "Dates", "hs_code": "080410", "hs_confirmed": True, "market": "Netherlands", "allow_degraded": True}
    headers = {"X-API-Key": "offline-test-key", "Idempotency-Key": "retry-admission"}
    with patch("requests.get", side_effect=OSError("net blocked")), patch("requests.post", side_effect=OSError("net blocked")), patch("requests.sessions.Session.request", side_effect=OSError("net blocked")), patch.object(silk_research_runtime, "try_acquire", return_value=False) as admission:
        client = TestClient(api.app)
        first = client.post("/research", headers=headers, json=body)
        second = client.post("/research", headers=headers, json=body)
    assert first.status_code == second.status_code == 503
    assert first.headers["retry-after"] == second.headers["retry-after"] == "60"
    assert admission.call_count == 2


def test_retry_release_never_removes_an_allocated_study(tmp_path, monkeypatch):
    import silk_request_identity as identity
    import silk_storage
    monkeypatch.setenv("SILK_DB", str(tmp_path / "fence.db"))
    key, _, _ = identity.claim("once", "owner", {"product": "Dates"})
    with identity.bind(key):
        aid = silk_storage.create_research_run("Dates", "NLD", "080410", {})
    assert identity.release_unallocated(key) is False
    assert identity.claim("once", "owner", {"product": "Dates"})[1]["analysis_id"] == aid


def test_explicit_source_magnitude_is_preserved():
    with block_network():
        source = DataPoint(10, "Source", .9, unit="million USD")
        assert parse("Imports 10 million USD", source)["findings"]
        assert parse("Imports 10000000 USD", source)["findings"]
        assert not parse("Imports 10 USD", source)["findings"]
