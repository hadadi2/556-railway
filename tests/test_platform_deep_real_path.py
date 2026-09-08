"""المسار العميق الحقيقي لدراسة منصّة — الرُتبة التي كانت غائبة كلياً.

لماذا هذا الملف (بلاغ المالك 2026-08-19 «المحرّك لا يعمل»): كل اختبار منصّة
سابق يستبدل المحرّك بمقعدٍ وهمي (`platform_helpers.mock_engine`) أو يستبدل
مغلقةَ البوّابة نفسها (`test_platform_deep_mode`)، ورُتبة ٣ تنزع المفاتيح وتضبط
`SILK_PLATFORM_FAKE_ENGINE=deep`. فكان **كل شيء أخضر** بينما الإطلاق الحقيقي
يرتدّ عند بوّابة البند الجمركي خلال ثانية: «اختر البند المطابق أدناه» —
ولا «أدناه» في أي شاشة، لأن المرشّحين كانوا يُفقَدون عند حدّ الجسر.

هنا يُقلَع تطبيق `api` الجذري فعلاً (فتُسجَّل بوّابة البحث العميق كما في
الإنتاج)، ويمرّ الطلب بكل بوّابات `_research_impl` الحقيقية (حسم HS، التأكيد،
التغطية، الجهوزية، حجز الميزانية) — والمُحاكى **طبقة مزوّد كلود وحدها**
(`silk_llm_provider`) لأن المفتاح لا يوجد في اختبار، وطبقةُ الشبكة (requests)
كي تبقى العملية هرمتية. Only the LLM provider and the network are mocked.
"""
import json
import os
import sqlite3
import tempfile

import pytest
import requests

pytest.importorskip("fastapi")


def _fake_provider(monkeypatch):
    """مزوّد كلود وهمي — الطبقة الوحيدة المُحاكاة من المحرّك."""
    import silk_llm_provider as prov

    report = ("# تقرير اختباري\n\n## الخلاصة\nنصّ غير فارغ يمثّل مخرج الكاتب.\n"
              "\n## الأسواق\n- سوق واحد بعمق\n")

    class _Fake(prov.LLMProvider):
        def complete(self, system, user, max_tokens, model, timeout):
            return report

        def complete_tools(self, system, messages, tools, max_tokens, model,
                           timeout):
            return {"content": [{"type": "text", "text": json.dumps(
                        {"findings": [], "summary": "بلا نتائج (محاكاة)"},
                        ensure_ascii=False)}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 5, "output_tokens": 5}}

    monkeypatch.setitem(prov._PROVIDERS, "fake", _Fake)
    monkeypatch.setenv("SILK_LLM_PROVIDER", "fake")
    prov.reset_provider()
    monkeypatch.setattr(prov, "reset_provider", prov.reset_provider)


def _no_network(monkeypatch):
    """كل مصدر بيانات يفشل صراحةً — فجوات معلنة، وسرعةٌ في التنفيذ."""
    def _boom(*a, **k):
        raise OSError("network disabled for offline test")

    monkeypatch.setattr(requests, "get", _boom)
    monkeypatch.setattr(requests, "post", _boom)
    monkeypatch.setattr(requests.Session, "request", _boom)


@pytest.fixture()
def deep_env(monkeypatch):
    """بيئة منصّة معزولة بالوضع العميق + تطبيق `api` الجذري + مصنع مبذور."""
    d = tempfile.mkdtemp()
    for key, val in {
        "SILK_PLATFORM_DB": os.path.join(d, "platform.db"),
        "SILK_PLATFORM_SECRET": "deep-real-path-test-secret-0123456789",
        "SILK_PLATFORM_STORAGE_DIR": os.path.join(d, "files"),
        "SILK_DB": os.path.join(d, "engine.db"),
        "SILK_STORE_DB": os.path.join(d, "store.db"),
        "SILK_USAGE_DB": os.path.join(d, "usage.db"),
        "SILK_CACHE_DIR": os.path.join(d, "cache"),
        # الجهوزية تفحص متغيّرات البيئة لا الشبكة — مفتاحان صوريّان يمرّانها،
        # والنداء نفسه يذهب إلى المزوّد الوهمي أعلاه (لا إنفاق، لا شبكة).
        "ANTHROPIC_API_KEY": "sk-ant-test-not-a-real-key",
        "SILK_API_KEY": "platform-deep-test-key",
        "SILK_PAID_DAILY_CAP": "50",
        "SILK_PAID_DAILY_USD_CAP": "100",
        "SILK_SEED_ADMIN_PASSWORD": "AdminPass1234",
        "SILK_SEED_FACTORY_A_PASSWORD": "FactoryPass1234",
        "SILK_SEED_FACTORY_B_PASSWORD": "FactoryPass1234",
        "SILK_SEED_ANALYST_PASSWORD": "AnalystPass1234",
        "SILK_MISSION_TIMEOUT_S": "5",
        "SILK_SWR": "0",
        # المقعد أعلاه يعيد نتائج فارغة. اختبار ذيل الكاتب يحتاج هذا الشرط
        # صراحةً، لا يرثه من conftest. اختبار الكفاية أدناه يفعّل الحارس.
        "SILK_EARLY_HALT": "0",
    }.items():
        monkeypatch.setenv(key, val)
    # الوضع العميق هو الافتراضي الإنتاجي — العُدّة المشتركة تفرض `quick`.
    monkeypatch.delenv("SILK_PLATFORM_STUDY_MODE", raising=False)
    monkeypatch.delenv("SILK_PLATFORM_FAKE_ENGINE", raising=False)

    _fake_provider(monkeypatch)
    _no_network(monkeypatch)

    from fastapi.testclient import TestClient
    import api as root_api
    from silk_platform import db as pdb, seed as pseed

    pdb.init_db(os.environ["SILK_PLATFORM_DB"], force=True)
    conn = pdb.connect()
    try:
        # خاملُ التكرار: قد يكون تأسيسُ الإقلاع بذرَ سلفاً (بوّابة البذر
        # مضبوطة أعلاه) — الهويّات ثابتة في `seed._EMAILS` وكلماتها من البيئة،
        # فلا نعتمد على قيمة العودة. Identities are fixed; don't rely on the
        # return value of an idempotent seed.
        pseed.seed(conn)
    finally:
        conn.close()

    cl = TestClient(root_api.create_app())
    r = cl.post("/platform/auth/login",
                json={"email": pseed._EMAILS["factory_a"],
                      "password": os.environ["SILK_SEED_FACTORY_A_PASSWORD"]})
    assert r.status_code == 200, r.text
    yield {"cl": cl, "hdr": {"Authorization": "Bearer " + r.json()["token"]},
           "db": os.environ["SILK_PLATFORM_DB"]}
    import silk_platform.engine_bridge as eb
    eb.wait_idle(30)


def test_empty_evidence_halts_with_production_guard_and_refunds_quota(deep_env, monkeypatch):
    """حارس الإنتاج يبقى نافذاً: لا كاتب ولا تقرير على أدلة فارغة."""
    import silk_llm_provider as prov
    from unittest.mock import patch

    monkeypatch.setenv("SILK_EARLY_HALT", "1")
    sid = _mk(deep_env, product="تمور", market_pref="OMN", hs_code="080410")
    with patch.object(prov._PROVIDERS["fake"], "complete",
                      side_effect=AssertionError("writer must not run")) as writer:
        row = _launch_and_settle(deep_env, sid)
    assert row["state"] == "draft", row
    assert "أوقفنا الدراسة مبكراً" in row["run_error"]
    assert row["analysis_id"]
    writer.assert_not_called()
    ent = deep_env["cl"].get("/platform/entitlements", headers=deep_env["hdr"]).json()
    assert ent["studies_used"] == 0, ent


def _row(db_path: str, study_id: int) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM studies WHERE id = ?",
                                 (study_id,)).fetchone())
    finally:
        conn.close()


def _launch_and_settle(env, study_id: int, timeout: float = 90.0) -> dict:
    """أطلق وانتظر خمود خيط الجسر ثم أعد صفّ الدراسة."""
    import silk_platform.engine_bridge as eb
    r = env["cl"].post(f"/platform/studies/{study_id}/launch", headers=env["hdr"])
    assert r.status_code == 200, r.text
    assert eb.wait_idle(timeout), "خيط الجسر لم يخمد ضمن المهلة"
    return _row(env["db"], study_id)


def _mk(env, **body) -> int:
    r = env["cl"].post("/platform/studies", headers=env["hdr"], json=body)
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


# ═══════════ ١ — البوّابة ترفض، لكنها تسلّم مخرجاً لا طريقاً مسدوداً ═══════════
def test_ambiguous_heading_refuses_and_hands_back_the_candidates(deep_env):
    """«حليب» ⇒ ترويسة تتمايز بنسبة الدهن: رفضٌ معلَن **مع** المرشّحين محفوظين.

    قبل الإصلاح: الرسالة تقول «اختر البند المطابق أدناه» والمرشّحون يُفقَدون
    عند حدّ الجسر — فلا شيء «أدناه» في أي شاشة.
    """
    sid = _mk(deep_env, product="حليب", market_pref="OMN")
    row = _launch_and_settle(deep_env, sid)

    assert row["state"] == "draft", row            # لا «مكتملة» كاذبة
    assert row["analysis_id"] is None
    # قرار المالك 2026-08-31 (تأكيدُ قرار 2026-08-29): لا سؤالَ اختيارٍ على
    # سطح المصنع — الرفضُ يشرح سببَه ويُرشِد لتحسين اسم/وصف المنتج أو إدخال
    # الرمز، بينما المرشّحون يبقون محفوظين لعقد الـAPI (اختيارُ PATCH أدناه).
    run_error = row["run_error"] or ""
    assert "اختر" not in run_error, run_error
    assert "عدِّل اسمَ المنتج أو وصفَه" in run_error, run_error
    cands = json.loads(row["hs_candidates"] or "[]")
    assert len(cands) >= 2, cands
    assert all(str(c.get("hs6") or "").isdigit() for c in cands), cands
    # حدُّ كلٍّ بلغةٍ مفهومة — بلا هذا لا معنى للاختيار.
    assert any(c.get("band_ar") for c in cands), cands
    # الحصّة أُرجعت: الرفض لا يُحرِق دراسةً من باقة المصنع.
    ent = deep_env["cl"].get("/platform/entitlements", headers=deep_env["hdr"]).json()
    assert ent["studies_used"] == 0, ent


# ═══════════ ٢ — الاختيار يُغلق الحلقة: تشغيلة عميقة حقيقية تكتمل ════════════
def test_picking_a_candidate_lets_the_real_deep_run_complete(deep_env):
    """اختيارُ المصنع من القائمة تأكيدٌ صريح ⇒ التشغيلة تمرّ وتكتمل.

    بلا تمرير `hs_confirmed` كانت البوّابة تعيد رفضَ الاختيار الذي عرضتْه —
    حلقةٌ مغلقة على المصنع. هذا الاختبار يمرّ ببوّابات `_research_impl` كلها.
    """
    sid = _mk(deep_env, product="حليب", market_pref="OMN")
    row = _launch_and_settle(deep_env, sid)
    pick = json.loads(row["hs_candidates"])[0]["hs6"]

    r = deep_env["cl"].patch(f"/platform/studies/{sid}", headers=deep_env["hdr"],
                             json={"hs_code": pick})
    assert r.status_code == 200, r.text
    assert r.json()["hs_confirmed"] == 1

    row = _launch_and_settle(deep_env, sid, timeout=180)
    assert row["state"] == "completed", row["run_error"]
    assert row["analysis_id"], row
    assert json.loads(row["run_stats"])["mode"] == "deep", row["run_stats"]
    # أثرُ المحاولة السابقة يُمسَح عند المطالبة — لا حوارُ اختيارٍ بعد حلّه.
    assert row["hs_candidates"] is None
    assert row["run_error"] is None


def _runs(db_path: str, study_id: int) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM study_runs WHERE study_id = ? ORDER BY id",
            (study_id,)).fetchall()]
    finally:
        conn.close()


# ═══════ ٢ج — R2: سجلّ التشغيلة يتبع المسار العميق الحقيقي ويُلغى عند مرحلة ═══
def test_r2_run_record_follows_the_real_deep_path_and_cancels_at_a_stage(
        deep_env, monkeypatch):
    """R2: صفّ `study_runs` يُنشأ ويُربَط بمعرّف المحرّك **لحظة تخصيصه**
    (`on_allocated`) ويُغلَق مكتملاً — عبر الجسر الحقيقي و`_research_impl`
    الحقيقي (المحاكى مزوّد كلود والشبكة فقط). ثم إلغاءٌ أثناء البعثات يمرّ
    بنقطة تفتيش `_stage_mark` الحقيقية فينتهي «أُلغيت» وصفُّ المحرّك `failed`
    وحجزُه مُصالَح — لا رطانةَ استثناء على سطح المصنع."""
    import silk_llm_provider as prov
    import silk_storage
    from silk_platform import db as pdb, study_runtime

    # (١) الدورة الكاملة: رفضٌ ← اختيار ← تشغيلة عميقة حقيقية تكتمل.
    sid = _mk(deep_env, product="حليب", market_pref="OMN")
    row = _launch_and_settle(deep_env, sid)
    pick = json.loads(row["hs_candidates"])[0]["hs6"]
    r = deep_env["cl"].patch(f"/platform/studies/{sid}", headers=deep_env["hdr"],
                             json={"hs_code": pick})
    assert r.status_code == 200, r.text
    row = _launch_and_settle(deep_env, sid, timeout=180)
    assert row["state"] == "completed", row["run_error"]
    runs = _runs(deep_env["db"], sid)
    assert [x["state"] for x in runs] == ["failed", "completed"], runs
    assert runs[0]["error_code"] == "refused"
    done = runs[-1]
    assert done["analysis_id"] == row["analysis_id"]      # رُبط لحظة التخصيص
    assert done["boot_id"] == study_runtime.boot_id() and done["finished_at"]

    # (٢) إلغاءٌ من داخل أول نداء كلود (بعثة) — عبر `request_cancel` الحقيقي.
    sid2 = _mk(deep_env, product="حليب", market_pref="OMN")
    row2 = _launch_and_settle(deep_env, sid2)
    pick2 = json.loads(row2["hs_candidates"])[0]["hs6"]
    r = deep_env["cl"].patch(f"/platform/studies/{sid2}", headers=deep_env["hdr"],
                             json={"hs_code": pick2})
    assert r.status_code == 200, r.text
    fake_cls = prov._PROVIDERS["fake"]
    orig_tools = fake_cls.complete_tools
    fired = {"n": 0}

    def hooked(self, *a, **k):
        if fired["n"] == 0:
            fired["n"] += 1
            conn = pdb.connect()
            try:
                st = study_runtime.request_cancel(
                    conn, study_id=sid2, account_id=int(row2["owner_id"]),
                    actor_user_id=None)
                assert st["run_state"] == "cancelling", st
            finally:
                conn.close()
        return orig_tools(self, *a, **k)

    monkeypatch.setattr(fake_cls, "complete_tools", hooked)
    row2 = _launch_and_settle(deep_env, sid2, timeout=180)
    assert fired["n"] == 1
    assert row2["state"] == "draft", row2
    assert "أُلغيت" in (row2["run_error"] or ""), row2["run_error"]
    assert "RunCancelled" not in (row2["run_error"] or "")
    last = _runs(deep_env["db"], sid2)[-1]
    assert last["state"] == "cancelled" and last["error_code"] == "cancelled", last
    assert last["analysis_id"], last                       # مؤشّر الاستئناف موجود
    eng = silk_storage.get_research_run(int(last["analysis_id"]))
    assert eng and eng["status"] == "failed", eng          # صفّ المحرّك حُسم لا «running»
    ent = deep_env["cl"].get("/platform/entitlements", headers=deep_env["hdr"]).json()
    assert ent["studies_used"] == 1, ent                   # حصّة الدراسة الأولى فقط
    # §58 #6: بعثةٌ أُلغيت في منتصفها لا تُحفَظ «مكتملة» بفجوة تتّهم المهلة —
    # تُوسَم فاشلةً فيُعاد تشغيلها عند الاستئناف لا يُبنى عليها مبتورة.
    mconn = sqlite3.connect(os.environ["SILK_DB"])
    try:
        statuses = [r[0] for r in mconn.execute(
            "SELECT status FROM research_missions WHERE analysis_id = ?",
            (int(last["analysis_id"]),)).fetchall()]
    finally:
        mconn.close()
    assert statuses and set(statuses) == {"failed"}, statuses

    # (٣) §58 #2: إلغاءٌ يصل أثناء الكاتب (آخر مرحلةٍ مدفوعة) لا يُتلف تقريراً
    # اكتمل — العلامة الختامية «end» ليست نقطة تفتيش؛ النجاح المحفوظ يبقى نجاحاً.
    monkeypatch.setattr(fake_cls, "complete_tools", orig_tools)
    sid3 = _mk(deep_env, product="حليب", market_pref="OMN")
    row3 = _launch_and_settle(deep_env, sid3)
    pick3 = json.loads(row3["hs_candidates"])[0]["hs6"]
    r = deep_env["cl"].patch(f"/platform/studies/{sid3}", headers=deep_env["hdr"],
                             json={"hs_code": pick3})
    assert r.status_code == 200, r.text
    orig_complete = fake_cls.complete
    writer_fired = {"n": 0}

    # التوقيع **حرفياً** كتوقيع المزوّد الوهمي: الكاتب يفحص إن كان `complete`
    # يقبل `stream` — غلافُ `*args/**kwargs` يوهمه بذلك فيمرّر `stream=True`
    # إلى الأصل الذي لا يقبله (TypeError يُقرأ كفشل محرّك لا كإلغاء).
    def hooked_writer(self, system, user, max_tokens, model, timeout):
        # الكاتب وحده يطلب سقفَ إخراجٍ بالآلاف؛ حكمُ التوليف والمراجع بالمئات —
        # فالإلغاء يُطلَب **أثناء الكاتب** لا قبله (وإلا أوقفته حدودُ المراحل السابقة).
        if writer_fired["n"] == 0 and int(max_tokens or 0) >= 4000:
            writer_fired["n"] += 1
            conn = pdb.connect()
            try:
                study_runtime.request_cancel(
                    conn, study_id=sid3, account_id=int(row3["owner_id"]),
                    actor_user_id=None)
            finally:
                conn.close()
        return orig_complete(self, system, user, max_tokens, model, timeout)

    monkeypatch.setattr(fake_cls, "complete", hooked_writer)
    row3 = _launch_and_settle(deep_env, sid3, timeout=180)
    assert writer_fired["n"] == 1
    # الإلغاء المقبول قبل معاملة الاكتمال يفوز؛ النتيجة المدفوعة لا تُحذف.
    assert row3["state"] == "draft", row3["run_error"]
    cancelled = _runs(deep_env["db"], sid3)[-1]
    assert cancelled["state"] == "cancelled"
    assert cancelled["analysis_id"]
    assert silk_storage.get_research_run(cancelled["analysis_id"])["status"] == "completed"


# ═══════ ٢ب — قبولُ الحادثة المُبلَّغة: «حلاوة طحينية» من الكتالوج ══════════
def test_the_reported_incident_now_launches_and_completes(deep_env):
    """البند ٢٥ (اختبارُ القبول): المنتجُ المُبلَّغ يمرّ من الكتالوج إلى نتيجة.

    قبل الموجة: رمزُ الكتالوج 170490 — وهو **الصحيح** — كان يصل الجسمَ بثقة
    `None` (لأن مصدرَه «كتالوج» لا لأن أحداً قاسه)، فتحجبه بوّابةُ الثقة
    بـ«ثقةُ تصنيف «حلاوة طحينية» … غير معلومة»، والشاشةُ بلا زرِّ اختيار:
    طريقٌ مسدود. الآن يُقاس الرمزُ على اسم المنتج، فيوافقه المُحلِّلُ بدليلٍ
    تامّ وتنطلق الدراسةُ حتى الاكتمال — بلا خفضِ عتبةٍ ولا تعطيلِ بوّابة.
    """
    r = deep_env["cl"].post("/platform/products", headers=deep_env["hdr"],
                            json={"name": "حلاوة طحينية",
                                  "description": "حلاوة طحينية سادة",
                                  "hs_code": "170490"})
    assert r.status_code == 200, r.text
    pid = int(r.json()["id"])

    sid = _mk(deep_env, product="حلاوة طحينية", market_pref="OMN",
              product_id=pid, hs_code="170490")
    row = _launch_and_settle(deep_env, sid, timeout=180)

    assert row["state"] == "completed", row["run_error"]
    assert row["analysis_id"], row
    assert json.loads(row["run_stats"])["mode"] == "deep", row["run_stats"]
    assert row["run_error"] is None
    # ولم يُطلَب تأكيدٌ بشريّ أصلاً: الدليلُ حسم، لا نقرةٌ عبرت بوّابة.
    assert not row["hs_confirmed"], row
    assert row["hs_candidates"] is None


def test_a_catalog_code_that_contradicts_the_product_still_refuses(deep_env):
    """الوجهُ الآخر لنفس القاعدة: كتالوجٌ مخالفٌ يُوقَف قبل أيّ إنفاق.

    الموجةُ لم تفتح البابَ للكتالوج — بل جعلت القرارَ قياساً. رمزُ دقيق
    القمح لمنتج حلاوةٍ يُرفَض ويُسلَّم للمصنع مخرجٌ فعليّ (مرشّحون محفوظون).
    """
    sid = _mk(deep_env, product="حلاوة طحينية", market_pref="OMN",
              hs_code="110100")
    row = _launch_and_settle(deep_env, sid)
    assert row["state"] == "draft", row
    assert row["analysis_id"] is None
    cands = json.loads(row["hs_candidates"] or "[]")
    assert cands and cands[0]["hs6"] == "170490", cands
    # الحصّة أُرجعت — الرفضُ لا يُحرِق دراسةً من باقة المصنع.
    ent = deep_env["cl"].get("/platform/entitlements",
                             headers=deep_env["hdr"]).json()
    assert ent["studies_used"] == 0, ent


# ═══════════ ٣ — رمزٌ يدويّ خارج القائمة لا يُمنَح تأكيداً مجّانياً ═══════════
def test_a_hand_typed_code_outside_the_list_is_not_auto_confirmed(deep_env):
    """التأكيد للاختيار من القائمة وحده — الكتابة العمياء تبقى محكومة بالبوّابة."""
    sid = _mk(deep_env, product="حليب", market_pref="OMN")
    _launch_and_settle(deep_env, sid)
    r = deep_env["cl"].patch(f"/platform/studies/{sid}", headers=deep_env["hdr"],
                             json={"hs_code": "999999"})
    assert r.status_code == 200, r.text
    assert r.json()["hs_confirmed"] == 0
    assert _row(deep_env["db"], sid)["hs_confirmed"] == 0


# ═══════════ ٤ — اسمُ علامةٍ تجارية: وصفُ الكتالوج يُنتِج المخرج ═════════════
def test_a_brand_named_catalog_product_still_gets_candidates(deep_env):
    """بلاغ «الطاحونة» (2026-08-29): طريقٌ مسدود بنصٍّ يعِد بما لا يوجد.

    منتجُ الكتالوج اسمُه علامةٌ تجارية («الطاحونة») ورمزُه مخزَّن — فتحجبه
    بوّابةُ الثقة (رمزُ كتالوجٍ مُعادٌ ثقتُه «غير معلومة») ثمّ تعود بقائمةٍ
    **فارغة** لأن اسم العلامة لا يطابق أيّ صفٍّ في مرجع HS: لا زرَّ «اختر
    البند الجمركي» في شاشة المصنع ولا مخرج إلا رمزٌ جمركيّ بيد المالك.
    الوصفُ المكتوب في الكتالوج («حلاوة طحينية سادة») يعرف المنتجَ الحقيقي.
    """
    r = deep_env["cl"].post("/platform/products", headers=deep_env["hdr"],
                            json={"name": "الطاحونة",
                                  "description": "حلاوة طحينية سادة",
                                  "hs_code": "170490"})
    assert r.status_code == 200, r.text
    pid = int(r.json()["id"])

    sid = _mk(deep_env, product="الطاحونة", market_pref="OMN",
              product_id=pid, hs_code="170490")
    row = _launch_and_settle(deep_env, sid)

    assert row["state"] == "draft", row
    assert row["analysis_id"] is None
    cands = json.loads(row["hs_candidates"] or "[]")
    assert cands, row["run_error"]           # المخرج موجود لا موعودٌ به
    assert cands[0]["hs6"] == "170490", cands
    # ومن الوصف جاء لا من قائمةٍ عامّة مبنيةٍ على اسم العلامة (تلك تُصدِّر
    # «شرائح تونة مجمّدة» و«قبّعات» لعلبة حلاوة) — الفرق أن هذه محسومة.
    assert len(cands) == 1, cands
    # الحصّة أُرجعت: الرفض لا يُحرِق دراسةً من باقة المصنع.
    ent = deep_env["cl"].get("/platform/entitlements",
                             headers=deep_env["hdr"]).json()
    assert ent["studies_used"] == 0, ent
