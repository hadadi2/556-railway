"""هدف الدراسة الاحترافية — الموجة ٨: سقف التكلفة (البند ٨).

المقفول: الإيقاف المبكر المعلن (أعمدة دون الحد الأدنى ⇒ لا محلل ولا كاتب
ولا حَكَم مرحلة-٢ مدفوع — والحكم الحتمي **لا يتغير** بين التفعيل والتعطيل)؛
افتراض العلم مفعّل ومخرج تعطيله يعمل؛ كاش بادئة الكاتب (بادئة المسوّدة
والتنقيح متطابقة بايتاً والمزوّد يقسم الرسالة كتلتين معلَّمة أولاهما)؛
ملاحظات المراجع تصل نصاً رغم نقلها آخر الموجّه؛ خريطة البعثات المغذّية
للأعمدة مقفولة ضد مصدرها بمسح AST (القاعدة الصلبة: لا قطع لأي منها).
"""
import contextlib
import json
import os
import re
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── علم SILK_EARLY_HALT ────────────────────────────────────────────────────

def test_early_halt_default_is_on(monkeypatch):
    import api
    monkeypatch.delenv("SILK_EARLY_HALT", raising=False)
    assert api._early_halt_enabled() is True
    monkeypatch.setenv("SILK_EARLY_HALT", "0")
    assert api._early_halt_enabled() is False
    monkeypatch.setenv("SILK_EARLY_HALT", "1")
    assert api._early_halt_enabled() is True


# ── الإيقاف المبكر على مسار /research الكامل (موكات نمط p6 القانوني) ───────

class _CompletedMission:
    """بعثة مكتملة مموّهة — نتيجة واحدة لا تكوّن أعمدة (2/3 دون الحد)."""
    def __init__(self, spec):
        self._key = spec["key"]

    def run(self, task):
        from silk_agents import AgentReport
        from silk_data_layer import DataPoint
        return AgentReport(
            f"LLMMissionAgent:{self._key}",
            [DataPoint("قيمة مموّهة", "UN Comtrade", 0.8,
                       f"{self._key}: بند مموّه", "2026-01-01")],
            False, "ok")


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _client():
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


def _run_research(early_halt: str, db: str, counters: dict) -> dict:
    """شغّل /research بموكات p6 القانونية وعلم الإيقاف المطلوب — يعيد
    المدوّنة المخزّنة ويملأ عدّادات النداءات المدفوعة."""
    counters.update({"analyst_tools": 0, "judge_call": 0, "synth_stage2": 0})

    def fake_tools(system, messages, tools=None, max_tokens=1600,
                   model=None, timeout=None, **kw):
        counters["analyst_tools"] += 1
        return {"stop_reason": "end_turn", "content": [{"type": "text",
                "text": json.dumps({"findings": [], "gaps": [],
                                    "summary": "تحليل مموّه"})}]}

    def fake_judge(system, user, max_tokens=1600, model=None, timeout=None,
                   **kw):
        counters["judge_call"] += 1
        return "## 1. الخلاصة التنفيذية\nالتوصية: نص مموّه.\n"

    def fake_synth(system, user, max_tokens=1600, model=None, timeout=None,
                   **kw):
        counters["synth_stage2"] += 1
        return json.dumps({"verdict": "WATCH", "confidence": 0.5,
                           "reasoning": "ok"})

    with contextlib.ExitStack() as st:
        st.enter_context(patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "test", "SILK_API_KEY": "secret",
            "SILK_EARLY_HALT": early_halt}))
        st.enter_context(patch("silk_llm_runtime._call_tools",
                               side_effect=fake_tools))
        st.enter_context(patch("silk_ai_judge._call",
                               side_effect=fake_judge))
        st.enter_context(patch("silk_synthesis._call",
                               side_effect=fake_synth))
        st.enter_context(patch("silk_storage._db_path", return_value=db))
        st.enter_context(patch("silk_missions.LLMMissionAgent",
                               _CompletedMission))
        # قطعُ الجلب الخارجي صراحةً (أوّل CI حيّ، 2026-08-27): هذان
        # الاختباران كانا يفترضان «لا شبكة» **من البيئة** لا بحجبٍ مكتوب —
        # فعلى عاملٍ متّصل تُجلب أعمدةٌ إضافية فلا يقع الإيقاف المبكر أصلاً
        # (`analyst_tools == 1` بدل صفر). حجبُ socket ممنوع هنا لأنه يكسر
        # ناقل TestClient (قاعدة CLAUDE.md)، فتُقطَع طبقةُ الجلب نفسها.
        # Cut the fetch layer explicitly: these tests silently relied on the
        # ambient absence of network (TestClient forbids socket blocking).
        import requests as _rq
        import silk_data_layer as _dl
        _dead = _rq.exceptions.ConnectionError("network disabled for test")
        st.enter_context(patch.object(_dl._session, "request",
                                      side_effect=_dead))
        st.enter_context(patch.object(_rq, "get", side_effect=_dead))
        st.enter_context(patch.object(_rq, "post", side_effect=_dead))
        client = _client()
        r = client.post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text
    from silk_storage import get_analysis
    return get_analysis(r.json()["analysis_id"], path=db)


def test_early_halt_skips_paid_tail_and_declares_it():
    counters: dict = {}
    blob = _run_research("1", _tmp_db(), counters)
    # لا نداء محلل ولا كاتب ولا حَكَم مرحلة-٢ — الذيل المدفوع صفر:
    assert counters["analyst_tools"] == 0
    assert counters["judge_call"] == 0
    assert counters["synth_stage2"] == 0
    dr = blob["deep_research"]
    assert dr["report"]["report"] is None
    assert dr["report"]["skip_reason"] == "early_halt"
    fr = dr["report"]["failure_reason"]
    assert "أوقفنا الدراسة مبكراً" in fr and "محفوظ" in fr
    assert blob["data_economics"]["early_halt"] is True
    # المحلل موسوم متخطّى معلَناً (لا نتائج مختلَقة):
    diag = (dr.get("analyst") or {}).get("diagnostics") or {}
    assert diag.get("all_missing_cause") == "early_halt"


def test_early_halt_off_runs_the_full_tail():
    counters: dict = {}
    blob = _run_research("0", _tmp_db(), counters)
    assert counters["analyst_tools"] >= 1     # المحلل نودي
    assert counters["judge_call"] >= 1        # الكاتب نودي
    assert blob["deep_research"]["report"]["report"]
    assert blob["data_economics"]["early_halt"] is False


def test_early_halt_does_not_change_the_engine_decision():
    """قيد المالك: لا تغيير حكم — قرار المحرك الحتمي (silk_decision عبر
    decide_for_deep) متطابق بين التفعيل والتعطيل على نفس البعثات."""
    on = _run_research("1", _tmp_db(), {})
    off = _run_research("0", _tmp_db(), {})

    def _decision(blob):
        rows = blob.get("markets") or []
        d = dict((rows[0].get("decision") or {})) if rows else {}
        d.pop("decision_rule", None)   # نص عرض لا حكم
        return d

    d_on, d_off = _decision(on), _decision(off)
    assert d_on and d_on.get("insufficient_pillars") is True
    for key in ("verdict", "score", "confidence", "computed_pillars",
                "min_scored_pillars", "insufficient_pillars"):
        assert d_on.get(key) == d_off.get(key), key


# ── كاش بادئة الكاتب ───────────────────────────────────────────────────────

def _deep_report_users(**extra) -> "tuple[list, list]":
    from tools.canonical_kuwait_peanut_butter import kuwait_research_blob
    import silk_ai_judge
    b = kuwait_research_blob()
    dr = b["deep_research"]
    users, prefixes = [], []

    def fake(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        users.append(user)
        prefixes.append(len(silk_ai_judge._cache_prefix_text.get() or ""))
        return "## 1. الخلاصة التنفيذية\nالتوصية: قياس.\n"

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
            patch("silk_ai_judge._call", side_effect=fake):
        silk_ai_judge.deep_report(dr["missions"], "ملخص",
                                  dr.get("verdict") or {}, b["product"],
                                  "Kuwait", hs_code=b["hs_code"])
        silk_ai_judge.deep_report(dr["missions"], "ملخص",
                                  dr.get("verdict") or {}, b["product"],
                                  "Kuwait", hs_code=b["hs_code"],
                                  review_notes=["أصلح الرقم س"], **extra)
    return users, prefixes


def test_draft_and_revision_share_a_byte_identical_prefix():
    users, prefixes = _deep_report_users()
    draft, revision = users[0], users[1]
    assert revision.startswith(draft)                  # بادئة مطابقة بايتاً
    assert prefixes[0] == prefixes[1] == len(draft)    # الحد على البادئة
    # ملاحظات المراجع لم تسقط بالنقل — تصل نصاً في ذيل التنقيح:
    tail = revision[len(draft):]
    assert "ملاحظات المراجع من دورة سابقة" in tail
    assert "أصلح الرقم س" in tail


def test_call_forwards_the_boundary_only_on_matching_prefix():
    """`_call` بلا تغيير توقيع (موكات الاختبارات القائمة): البادئة تصل
    المزوّد عبر contextvar وحارس startswith — رسالة لا تبدأ بها لا تُمسّ."""
    import silk_ai_judge
    import silk_llm_provider as P
    got = []

    def fake_complete(system, user, max_tokens, model, timeout,
                      stream=False, cache_prefix_chars=None):
        got.append(cache_prefix_chars)
        return "ok"

    prov = P.get_provider()
    tok = silk_ai_judge._cache_prefix_text.set("بادئة مستقرة")
    try:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
                patch.object(type(prov), "complete",
                             side_effect=fake_complete):
            silk_ai_judge._call("نظام", "بادئة مستقرة + ذيل ملاحظات")
            silk_ai_judge._call("نظام", "رسالة مراجع مختلفة تماماً")
    finally:
        silk_ai_judge._cache_prefix_text.reset(tok)
    assert got == [len("بادئة مستقرة"), None]


def test_provider_splits_user_at_the_cache_boundary():
    import silk_llm_provider as P
    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "ok"}], "usage": {}}

        def raise_for_status(self):
            pass

    prov = P.get_provider()

    def fake_post(key, payload, timeout, stream=False):
        captured["payload"] = payload
        return _Resp()

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
            patch.object(type(prov), "_post", side_effect=fake_post):
        prov.complete("نظام", "أ" * 80 + "ب" * 20, 100, "claude-opus-4-8",
                      30, cache_prefix_chars=80)
    blocks = captured["payload"]["messages"][0]["content"]
    assert isinstance(blocks, list) and len(blocks) == 2
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[0]["text"] == "أ" * 80 and blocks[1]["text"] == "ب" * 20
    assert "cache_control" not in blocks[1]
    # حدّ يساوي الطول كله (نداء المسوّدة): كتلة واحدة مكاشة —
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
            patch.object(type(prov), "_post", side_effect=fake_post):
        prov.complete("نظام", "نص", 100, "claude-opus-4-8", 30,
                      cache_prefix_chars=2)
    blocks = captured["payload"]["messages"][0]["content"]
    assert len(blocks) == 1 and "cache_control" in blocks[0]
    # بلا حدّ: الحمولة القديمة حرفياً (سلسلة لا قائمة) —
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
            patch.object(type(prov), "_post", side_effect=fake_post):
        prov.complete("نظام", "نص", 100, "claude-opus-4-8", 30)
    assert isinstance(captured["payload"]["messages"][0]["content"], str)


# ── خريطة البعثات المغذّية للأعمدة — قفل ضد المصدر ─────────────────────────

def test_pillar_feeding_missions_map_matches_the_source():
    """`tools/prompt_size_report.PILLAR_FEEDING_MISSIONS` منسوخة من قراءات
    `build_pillar_inputs` — مسح نصي للمصدر يمنع انجرافها صامتة."""
    import inspect
    import silk_deep_pillars
    from tools.prompt_size_report import PILLAR_FEEDING_MISSIONS
    src = inspect.getsource(silk_deep_pillars.build_pillar_inputs)
    read = set(re.findall(r'_findings\(missions,\s*"([a-z_]+)"\)', src))
    assert read == set(PILLAR_FEEDING_MISSIONS), (read,
                                                  PILLAR_FEEDING_MISSIONS)


def test_prompt_size_tool_measures_both_stages():
    from tools.prompt_size_report import measure_prompts
    r = measure_prompts("kuwait")
    assert not r["errors"], r["errors"]
    stages = {c["stage"] for c in r["calls"]}
    assert {"analyst/_call_tools", "writer/_call"} <= stages
    assert r["totals"]["approx_tokens"] > 1000
    assert r["totals"]["cacheable_prefix_share_pct"] > 50


def test_cost_map_tags_pillar_missions_and_the_hard_rule():
    from tools.prompt_size_report import cost_map
    eco = {"cost_usd_estimate": 2.0,
           "cost_usd_by_mission": {"trade_flow": 0.3, "opportunity_gaps": 0.1},
           "early_halt": False}
    out = "\n".join(cost_map(eco))
    assert "trade_flow" in out and "لا تُقطع" in out
    assert "opportunity_gaps" in out and "لا تغذي عموداً" in out
    assert "أرخص رقم آمن" in out
    empty = "\n".join(cost_map({"cost_usd_by_mission": {}}))
    assert "فجوة معلنة" in empty


def test_writer_dedup_not_applied_without_measured_excess():
    """قاعدة الموجة ٨ «قياس قبل قطع»: صفر تكرار مقيس على المدونة القياسية ⇒
    لا طبقة dedup على مدخل الكاتب (تُوثَّق pending على دراسة حية)."""
    from tools.canonical_kuwait_peanut_butter import kuwait_research_blob
    notes = []
    for m in kuwait_research_blob()["deep_research"]["missions"].values():
        for f in (m.get("findings") or []):
            notes.append(f"{f.get('value')}|{f.get('note')}")
    assert len(notes) == len(set(notes))
