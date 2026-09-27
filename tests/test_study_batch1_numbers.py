"""الدفعة ١ — P1-5 (القرار الرباعي وحياد البرومبت)، P1-6 (لا حساب في النموذج، الكسور
اللفظية مسندة)، P1-8 (وسم «أولي»)، P1-6…9 (أرقام الدراسة مخزَّنة مع النتيجة)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import tempfile
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── P1-5 ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("verdict,expected", [
    ("GO", "entry"), ({"verdict": "CONDITIONAL-GO"}, "conditional"), ("WATCH", "defer"),
    ("NO-GO", "no_entry"), ("NO-GO (insufficient data) — قرار مؤجّل", "no_entry"), ("", "defer"), (None, "defer"),
])
def test_study_decision_four_way_map(verdict, expected):
    from silk_synthesis import study_decision
    assert study_decision(verdict) == expected


def test_writer_prompt_carries_no_calculation_imperative_and_no_leaning_verdict():
    """كل «احسب» في برومبت الكاتب إمّا منفي («لا تحسب») أو خارج تعليمات الأرقام."""
    src = open(os.path.join(_ROOT, "silk_ai_judge.py"), encoding="utf-8").read()
    body = src[src.index("def deep_report("):src.index("def rephrase_client_sections(") if "def rephrase_client_sections(" in src[src.index("def deep_report("):] else len(src)]
    body = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))   # التعليقات ليست برومبت
    imperatives = [m.start() for m in re.finditer(r"(?<!لا ت)(?<!لا )احسب", body)]
    # الاستثناء الوحيد: عدّ تكرار سطر عنوان (لا رقم قرار) — "احسب كم مرة"
    offenders = [body[i - 40:i + 30] for i in imperatives if "كم مرة" not in body[i:i + 15]]
    assert not offenders, offenders
    assert "تميل نحو الدخول المشروط" not in src
    assert "فيجب أن يعكسه الحكم" not in src


def test_requirements_derive_from_gaps():
    from silk_study_case import _requirements_from_gaps
    r = _requirements_from_gaps(["أسعار الرف"], [], [])
    assert [q["id"] for q in r] == [1, 2, 3] and "تكلفة إنتاج" in r[0]["text"]
    r2 = _requirements_from_gaps([], [{"usd_kg": 20}], [{"name": "a"}, {"name": "b"}])
    assert len(r2) == 1


# ── P1-6 ──────────────────────────────────────────────────────────────────
def test_verbal_fraction_must_be_grounded_in_known_numbers():
    from silk_evals import citation_correctness_score
    missions = {"trade_flow": {"findings": [
        {"value": 43, "source": "UN Comtrade", "note": "نمو القيمة 43% بين 2019 و2023", "data_year": 2023},
        {"value": 24, "source": "UN Comtrade", "note": "نمو الكمية 24%", "data_year": 2023}]}}
    ok = citation_correctness_score("ارتفعت القيمة بنسبة 43% وتفسّر الكمية نحو ثلاثة أخماس النمو.", missions)
    assert ok["score"] == 100 and not ok["fraction_violations"]
    bad = citation_correctness_score("وتستحوذ ثلاث دول على ثلاثة أرباع الواردات.", missions)
    assert bad["score"] == 0 and bad["fraction_violations"] == ["ثلاثة أرباع"]


def test_verbal_fraction_extraction():
    from silk_study_arabic import verbal_fractions
    words = [w for w, _ in verbal_fractions("يمرر سدس السوق، ويستحوذان على ثلث السوق، ونصف الواردات تقريباً")]
    assert words == ["سدس", "ثلث", "نصف"]


# ── P1-8 ──────────────────────────────────────────────────────────────────
def test_previous_year_is_provisional_until_mid_year():
    from silk_deep_pillars import is_provisional_year
    assert is_provisional_year(2025, today=dt.date(2026, 3, 1))
    assert not is_provisional_year(2025, today=dt.date(2026, 9, 26))
    assert not is_provisional_year(2024, today=dt.date(2026, 3, 1))


def test_provisional_rows_are_marked_and_excluded_from_growth():
    from silk_study_numbers import series_shape
    from silk_study_render import Renderer
    fx = json.load(open(os.path.join(_ROOT, "evals", "golden_set", "malaysia_coffee_fixture.json"), encoding="utf-8"))
    fx["imports"]["series"].append({"year": 2025, "value_musd": 95.0, "kg": None, "complete": False})
    shape = series_shape(fx["imports"]["series"])
    assert shape["y_last"] == 2024                     # الأولية لا تدخل النمو
    out = Renderer(fx, {}).render()
    assert "| 2025 | 95.0 (أولي) |" in out
    assert "**أحدث سنة بيانات تجارية مكتملة:** 2024" in out


# ── P1-6…9 التخزين مع النتيجة ────────────────────────────────────────────
def _fake_tools(system, messages, tools=None, max_tokens=None, model=None, timeout=None, **kw):
    return {"text": json.dumps({"findings": []}), "tool_calls": [], "stop_reason": "end_turn",
            "usage": {"input_tokens": 50, "output_tokens": 20}}


def test_study_numbers_are_stored_with_the_research_result():
    from fastapi.testclient import TestClient
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "t", "SILK_API_KEY": "s", "SILK_RATE_LIMIT": "100000",
                                 "SILK_DATA_DIR": tempfile.mkdtemp(), "SILK_PREFLIGHT": "0"}), \
            patch("silk_llm_runtime._call_tools", side_effect=_fake_tools), \
            patch("silk_synthesis._call", return_value=json.dumps({"verdict": "WATCH", "confidence": 0.5, "reasoning": "ok"})), \
            patch("silk_ai_judge._call", return_value="## 1. الخلاصة التنفيذية\nتقرير."), \
            patch("silk_data_layer._cached_get", return_value=None), \
            patch("silk_data_layer._http_get", side_effect=OSError("no net")), \
            patch("silk_storage._db_path", return_value=db):
        import api
        client = TestClient(api.create_app())
        hdr = {"X-API-Key": "s"}
        r = client.post("/research", headers=hdr, json={"product": "تمور", "market": "Nigeria", "hs_code": "080410",
                                                         "persist": True, "async_run": True, "hs_confirmed": True})
        aid = r.json()["analysis_id"]
        for _ in range(3000):
            st = client.get(f"/research/{aid}/status", headers=hdr).json()
            if st.get("status") and st["status"] != "running":
                break
            time.sleep(0.01)
        res = client.get(f"/analyses/{aid}", headers=hdr).json()
        sn = (res.get("deep_research") or {}).get("study_numbers")
        assert isinstance(sn, dict) and sn.get("decision") in ("entry", "conditional", "defer", "no_entry")
        assert sn.get("hhi_band") == "not_computed"
