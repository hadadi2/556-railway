"""أقفال R4 — تقسية الواجهة البرمجية والخلفية (التدقيق الجنائي 2026-09-01، المرحلة ٤).

لماذا هذا الملف: بابان مدفوعان بلا خانق (`/products/{id}/classify-image` يصل
السقفَ المشترك مباشرةً، و`/images` يكتب على القرص بلا حدٍّ تجميعيّ لأي طبقة)،
وثلاثة `limit` غير محدودة تُفرِغ جداول كاملة بـ`?limit=-1`، وأربعة حقولٍ نصّية
تُقرأ بلا إكراه فتصير قائمةُ JSON خطأً داخلياً 500، وحارسُ إقلاعٍ لا يرى
`SILK_PLATFORM_EXPOSE_RESET_TOKEN` وهو مفتاحُ اختباراتٍ يُخرِج رمزَ إعادة
التعيين في الردّ، ورمزُ البند يصل المحرّكَ موسوماً «catalog» دائماً ولو كتبه
المصنعُ بيده أو حسمته الرؤية، واستشارةُ ما قبل التشغيل ترفض كلَّ دراسةٍ لها
شقيقُ تحذير بلا أيّ سبيلٍ للإقرار، وطبقةُ Basic تقبل «دراسات شهرية» تُنشَر
في التسعير ولا يقرؤها حاسبُ الحصّة أبداً.

هرمتي: قاعدة المنصّة والمحرّك معزولتان، والمحرّك يُحاكى (`mock_engine` أو
مغلقةُ بوّابةٍ وهمية). Hermetic only.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.platform_helpers import (client, hdr, login, make_factory,  # noqa: E402
                                    mock_engine, seed, setup_env)

pytest.importorskip("fastapi")

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PAGE = _ROOT / "web" / "platform.html"


# ── أدوات مشتركة · shared helpers ────────────────────────────────────────────
def _seed_throttle_rows(ident: str, n: int) -> None:
    """امْلأ عدّاد هويّة إلى السقف (صفوف طازجة داخل النافذة)."""
    import datetime
    from silk_platform import db as pdb
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    conn = pdb.connect()
    try:
        for _ in range(n):
            conn.execute(
                "INSERT INTO login_attempts (identity, created_at) VALUES (?,?)",
                (ident, now))
        conn.commit()
    finally:
        conn.close()


def _conn():
    from silk_platform import db as pdb
    return pdb.connect()


def _count(sql: str, args: tuple) -> int:
    conn = _conn()
    try:
        return int(conn.execute(sql, args).fetchone()[0])
    finally:
        conn.close()


def _upload(cl, tok, *, filename="a.png", content=b"\x89PNG\r\n\x1a\n-fake-bytes",
            mime="image/png"):
    return cl.post("/platform/images", headers=hdr(tok),
                   files={"file": (filename, content, mime)})


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")   # للأدمِن
    info = seed(monkeypatch)
    cl = client()
    fac = make_factory("gold", "r4@f.local")
    tok = login(cl, fac["email"], fac["password"])
    return {"cl": cl, "fac": fac, "tok": tok, "info": info}


def _mk_study(cl, tok, **over):
    body = {"product": "تمور سكري", "hs_code": "080410", "market_pref": "ARE",
            **over}
    r = cl.post("/platform/studies", json=body, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


def _study_row(sid: int) -> dict:
    conn = _conn()
    try:
        return dict(conn.execute("SELECT * FROM studies WHERE id = ?",
                                 (sid,)).fetchone())
    finally:
        conn.close()


# ══════════════ R4.1 — الرؤية على المنتج تحت الخانق نفسه ════════════════════
def test_classify_product_image_is_throttled_per_account(env, monkeypatch):
    """السطح الثاني للرؤية يشترك في عدّاد `vision|{account}` نفسه.

    كان `/products/{id}/classify-image` يصل السقفَ المدفوع المشترك بلا خانقٍ
    إطلاقاً بينما شقيقُه `/classify-image` مخنوق منذ الدرس ١٨٩ — فحلقةٌ على
    المسار غير المخنوق تستنزف ميزانية المستأجرين كلّهم كما لو لم يوجد الخانق.
    """
    seen = []
    import silk_usage
    monkeypatch.setattr(silk_usage, "try_reserve_paid_calls",
                        lambda n=1: seen.append(n) or True)
    _seed_throttle_rows(f"vision|{env['fac']['account_id']}", 20)
    r = env["cl"].post("/platform/products/1/classify-image", json={},
                       headers=hdr(env["tok"]))
    assert r.status_code == 429, r.text
    assert r.json()["detail"]["error"] == "vision_throttled"
    assert seen == []          # لا حجزَ من السقف المدفوع على نداءٍ مخنوق


def test_both_vision_surfaces_share_one_account_budget(env):
    """نداءٌ على سطح المنتج يُنقِص العدّادَ الذي يقرؤه السطحُ الآخر."""
    ident = f"vision|{env['fac']['account_id']}"
    _seed_throttle_rows(ident, 19)
    # منتجٌ غير موجود ⇒ 404، لكنّ العدّاد سُجِّل قبلها (كسطح `classify-image`).
    env["cl"].post("/platform/products/999/classify-image", json={},
                   headers=hdr(env["tok"]))
    assert _count("SELECT COUNT(*) FROM login_attempts WHERE identity = ?",
                  (ident,)) == 20
    r = env["cl"].post("/platform/classify-image", json={"image_id": 1},
                       headers=hdr(env["tok"]))
    assert r.status_code == 429, r.text
    assert r.json()["detail"]["error"] == "vision_throttled"


# ══════════════ R4.2 — الرفع: خانق + سقف تخزين لكل طبقة ═════════════════════
def test_upload_is_throttled_per_account_before_any_write(monkeypatch):
    """٣٠ رفعة في النافذة ⇒ الحادية والثلاثون 429 قبل قراءة الجسم وقبل الكتابة."""
    setup_env(monkeypatch)
    f = make_factory("gold", "up-thr@f.local")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    _seed_throttle_rows(f"upload|{f['account_id']}", 30)
    r = _upload(cl, tok)
    assert r.status_code == 429, r.text
    assert r.json()["detail"]["error"] == "upload_throttled"
    assert _count("SELECT COUNT(*) FROM images WHERE owner_id = ?",
                  (f["account_id"],)) == 0


def test_upload_prefix_is_registered_for_pruning():
    from silk_platform import throttle
    assert "UPLOAD" in throttle.NAMED_WINDOW_DEFAULTS


def test_every_tier_declares_a_storage_cap():
    """السقف التجميعي بيانٌ على الطبقة لا رقمٌ مبعثر — قرار المالك 2026-09-02."""
    from silk_platform.models import Tier, tier_limits
    assert tier_limits(Tier.BASIC).storage_bytes == 100 * 1024 * 1024
    assert tier_limits(Tier.SILVER).storage_bytes == 1024 * 1024 * 1024
    assert tier_limits(Tier.GOLD).storage_bytes == 5 * 1024 * 1024 * 1024


def test_upload_past_the_tier_cap_is_refused_before_the_disk(monkeypatch):
    """تجاوزُ السقف التجميعي ⇒ 413 معلَن بالعربية، بلا بايتٍ على القرص ولا صفّ.

    كان السقف الوحيد `10 MB` **لكل ملف** — فحسابٌ واحد يملأ الوحدة المركَّبة
    بألف ملفٍّ تحت السقف، وفوترةُ التخزين تُحرَّر بعد الحدوث لا قبله.
    """
    setup_env(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STORAGE_CAP_MB_GOLD", "1")
    f = make_factory("gold", "up-cap@f.local")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    conn = _conn()
    try:      # صفٌّ قائم يستهلك السقف كاملاً (لا بايتَ حقيقي — الحجم مقيسٌ سلفاً)
        from silk_platform.db import now_iso
        conn.execute(
            "INSERT INTO images (owner_id, filename, storage_key, mime_type, "
            "size_bytes, uploaded_at) VALUES (?,?,?,?,?,?)",
            (f["account_id"], "seed.png", f"{f['account_id']}/seed.png",
             "image/png", 1024 * 1024, now_iso()))
        conn.commit()
    finally:
        conn.close()
    from silk_platform import storage
    before = sorted(os.listdir(storage.storage_dir())) if os.path.isdir(
        storage.storage_dir()) else []
    r = _upload(cl, tok, content=b"\x89PNG\r\n\x1a\n" + b"x" * 100)
    assert r.status_code == 413, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "storage_quota_exceeded"
    assert any("ا" <= ch <= "ي" for ch in detail["message"]), detail
    assert _count("SELECT COUNT(*) FROM images WHERE owner_id = ?",
                  (f["account_id"],)) == 1        # الصفُّ المبذور وحده
    after = sorted(os.listdir(storage.storage_dir())) if os.path.isdir(
        storage.storage_dir()) else []
    assert after == before


def test_storage_cap_env_override_is_read_per_tier(monkeypatch):
    from silk_platform import quota
    monkeypatch.delenv("SILK_PLATFORM_STORAGE_CAP_MB_SILVER", raising=False)
    assert quota.storage_cap_bytes("silver") == 1024 * 1024 * 1024
    monkeypatch.setenv("SILK_PLATFORM_STORAGE_CAP_MB_SILVER", "7")
    assert quota.storage_cap_bytes("silver") == 7 * 1024 * 1024


# ══════════════ R4.3 — حارس الإقلاع يرى مفتاح الاختبارات ════════════════════
def test_boot_guard_refuses_exposed_reset_token_in_production(monkeypatch):
    """`SILK_PLATFORM_EXPOSE_RESET_TOKEN=1` مفتاحُ اختباراتٍ يُعيد رمزَ إعادة
    التعيين في الردّ — تسرّبُه إلى بيئةٍ إنتاجية يجعل «نسيت كلمة السر» سبيلَ
    استيلاءٍ على أيّ حساب بطلبٍ واحد. الحارس كان لا يقرؤه إطلاقاً."""
    from silk_platform.api import boot_config_guard
    monkeypatch.setenv("SILK_PLATFORM_SECRET", "a-real-secret")
    monkeypatch.setenv("SILK_PLATFORM_BCRYPT_ROUNDS", "12")
    monkeypatch.setenv("SILK_PLATFORM_EXPOSE_RESET_TOKEN", "1")
    monkeypatch.setenv("SILK_PLATFORM_SECURE_COOKIES", "1")
    with pytest.raises(RuntimeError):
        boot_config_guard()
    monkeypatch.delenv("SILK_PLATFORM_SECURE_COOKIES", raising=False)
    monkeypatch.setenv("SILK_PLATFORM_REQUIRE_SECRET", "1")   # الإشارة الأخرى
    with pytest.raises(RuntimeError):
        boot_config_guard()
    monkeypatch.delenv("SILK_PLATFORM_REQUIRE_SECRET", raising=False)
    boot_config_guard()          # تطويرياً يبقى المفتاح مسموحاً


# ══════════════ R4.4 — `limit` محدودٌ على الأسطح الثلاثة ════════════════════
@pytest.mark.parametrize("path", ["/platform/wallet/ledger", "/platform/audit"])
@pytest.mark.parametrize("bad", ["-1", "0", "501", "abc"])
def test_factory_list_limits_are_bounded(env, path, bad):
    """`?limit=-1` كان يصل SQLite بمعنى «بلا حدّ» فيُعيد الجدول كاملاً."""
    r = env["cl"].get(f"{path}?limit={bad}", headers=hdr(env["tok"]))
    assert r.status_code == 422, (path, bad, r.text)


@pytest.mark.parametrize("bad", ["-1", "0", "501", "abc"])
def test_admin_audit_limit_is_bounded(env, monkeypatch, bad):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    tok = login(env["cl"], "admin@silk.local", "AdminPass1")
    r = env["cl"].get(f"/platform/admin/audit?limit={bad}", headers=hdr(tok))
    assert r.status_code == 422, (bad, r.text)


def test_bounded_limit_still_serves_a_valid_value(env):
    r = env["cl"].get("/platform/audit?limit=5", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert len(r.json()["audit"]) <= 5


# ══════════════ R4.5 — حقولٌ نصّية مُكرَهة: عيبُ عميلٍ لا 500 ═══════════════
def test_login_with_shaped_json_is_a_client_fault(env):
    r = env["cl"].post("/platform/auth/login",
                       json={"email": ["a@b.c"], "password": {"x": 1}})
    assert 400 <= r.status_code < 500, r.text


def test_reset_request_with_shaped_email_is_not_a_500(env):
    r = env["cl"].post("/platform/auth/password-reset/request",
                       json={"email": ["a@b.c"]})
    assert r.status_code < 500, r.text


def test_reset_confirm_with_shaped_token_is_a_client_fault(env):
    r = env["cl"].post("/platform/auth/password-reset/confirm",
                       json={"token": ["x"], "new_password": {"y": 2}})
    assert 400 <= r.status_code < 500, r.text


# ══════════════ R4.6 — حدود رمز البند معلنة ═════════════════════════════════
@pytest.mark.parametrize("code", ["123", "1234567", ["080410"], "08041a"])
def test_hs_code_boundaries_are_refused(env, code):
    """٤–٦ خانات ASCII (قرار المالك: تُبقى كما هي) — والحدود مقفولة صراحةً."""
    r = env["cl"].post("/platform/studies",
                       json={"product": "تمور", "hs_code": code},
                       headers=hdr(env["tok"]))
    assert r.status_code == 422, (code, r.text)


@pytest.mark.parametrize("code", ["1234", "12345", "123456"])
def test_hs_code_accepts_heading_and_subheading(env, code):
    r = env["cl"].post("/platform/studies",
                       json={"product": "تمور", "hs_code": code},
                       headers=hdr(env["tok"]))
    assert r.status_code == 200, (code, r.text)


def test_page_label_says_heading_or_subheading():
    """«4–6 أرقام» وحدها لا تقول ما الرمز — الواجهة تسمّي البند والبند الفرعي."""
    src = _PAGE.read_text(encoding="utf-8")
    assert "بند أو بند فرعي" in src


# ══════════════ R4.7 — مصدرُ البند يُمرَّر كما سُجِّل ═══════════════════════
def _register_gateway(monkeypatch, run, ready=(True, "")):
    import silk_research_gateway as gw
    monkeypatch.setattr(gw, "_RUN", run)
    monkeypatch.setattr(gw, "_READINESS", lambda: ready)


def _deep_result(analysis_id=931, method=None):
    out = {"product": "تمور سكري", "hs_code": "080410",
           "markets": [],
           "deep_research": {"missions": {}, "analyst": {},
                             "verdict": {"decision": "ادرس بعمق"},
                             "report": {"report": "# تقرير\n\nمحتوى حقيقي.",
                                        "review_cycles": 1}},
           "analysis_id": analysis_id}
    if method:
        out["hs_classification"] = {"classification_method": method}
    return out


def _mk_product(cl, tok, **over):
    body = {"name": "تمور سكري", "hs_code": "080410", **over}
    r = cl.post("/platform/products", json=body, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


def _set_product_provenance(pid: int, source: str) -> None:
    conn = _conn()
    try:
        conn.execute("UPDATE products SET hs_source = ? WHERE id = ?",
                     (source, pid))
        conn.commit()
    finally:
        conn.close()


def _launch_with_product(env, monkeypatch, *, source: str,
                         product_code="080410", study_code="080410",
                         result=None):
    import silk_platform.engine_bridge as eb
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    calls = {}

    def run(**kw):
        calls.update(kw)
        return result or _deep_result()

    _register_gateway(monkeypatch, run)
    prod = _mk_product(env["cl"], env["tok"], hs_code=product_code)
    _set_product_provenance(prod["id"], source)
    s = _mk_study(env["cl"], env["tok"], hs_code=study_code,
                  product_id=prod["id"])
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    return calls, s


@pytest.mark.parametrize("source", ["manual", "image"])
def test_settled_product_provenance_reaches_the_engine(env, monkeypatch, source):
    """رمزٌ كتبه المصنعُ بيده أو حسمته الرؤيةُ من العبوة ليس رمزَ كتالوجٍ موروثاً.

    الترحيل ٠١٧ سجّل الواقعة على المنتج، لكنّ الجسر ظلّ يلصق `"catalog"` على
    كل رمز — فالإفصاحُ الذي وُجد العمودُ لحفظه لا يصل البوّابات أبداً.
    """
    calls, _ = _launch_with_product(env, monkeypatch, source=source)
    assert calls["hs_source"] == source


def test_a_different_code_than_the_products_stays_catalog(env, monkeypatch):
    """رمزُ الدراسة إن خالف رمزَ منتجها فمصدرُه ليس مصدرَ المنتج — «catalog»."""
    calls, _ = _launch_with_product(env, monkeypatch, source="manual",
                                    product_code="080410", study_code="090111")
    assert calls["hs_source"] == "catalog"


def test_pipeline_classification_method_is_persisted_on_the_study(env, monkeypatch):
    """«كيف حُسِم البند» يُكتَب من عقد التصنيف لا يُستنتَج بعد شهر."""
    _, s = _launch_with_product(
        env, monkeypatch, source="manual",
        result=_deep_result(method="deterministic_exact"))
    assert _study_row(s["id"])["hs_classification_method"] == "deterministic_exact"


# ══════════════ R4.8 — استشارةُ ما قبل التشغيل بموافقةٍ حقيقية ══════════════
def _force_advisory(monkeypatch, kinds=("export_to_origin",)):
    import silk_prerun
    monkeypatch.setattr(silk_prerun, "advisories_enabled", lambda: True)
    monkeypatch.setattr(
        silk_prerun, "sibling_advisories",
        lambda hs_code, iso3: [{"kind": k,
                                "message": "السوق المختارة بلدُ منشأ المنتج — "
                                           "راجع اتجاه الدراسة قبل الإطلاق"}
                               for k in kinds])


def test_launch_with_an_advisory_refuses_before_any_claim(env, monkeypatch):
    """422 `prerun_advisory` بلا حرقِ حصّة ولا صفّ تشغيلة — والإقرار مطلوب."""
    _force_advisory(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    _register_gateway(monkeypatch, lambda **kw: _deep_result())
    s = _mk_study(env["cl"], env["tok"])
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "prerun_advisory"
    assert detail["needs_ack"] is True
    assert detail["advisories"]
    row = _study_row(s["id"])
    assert row["state"] == "draft" and row["launched_at"] is None
    assert _count("SELECT COUNT(*) FROM study_runs WHERE study_id = ?",
                  (s["id"],)) == 0
    ent = env["cl"].get("/platform/entitlements", headers=hdr(env["tok"])).json()
    assert ent["studies_used"] == 0


def test_ack_then_launch_passes_consent_to_the_engine(env, monkeypatch):
    """الإقرارُ فعلُ المصنع لا افتراضُ النظام — يُختَم ثم يصل الجسمَ."""
    import silk_platform.engine_bridge as eb
    _force_advisory(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    calls = {}

    def run(**kw):
        calls.update(kw)
        return _deep_result()

    _register_gateway(monkeypatch, run)
    s = _mk_study(env["cl"], env["tok"])
    p = env["cl"].patch(f"/platform/studies/{s['id']}",
                        json={"advisories_ack": True}, headers=hdr(env["tok"]))
    assert p.status_code == 200, p.text
    assert _study_row(s["id"])["advisories_ack_at"]
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    assert calls.get("advisories_ack") is True


def test_ack_is_audited(env, monkeypatch):
    _force_advisory(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    s = _mk_study(env["cl"], env["tok"])
    env["cl"].patch(f"/platform/studies/{s['id']}",
                    json={"advisories_ack": True}, headers=hdr(env["tok"]))
    assert _count("SELECT COUNT(*) FROM audit_log WHERE action = ? "
                  "AND resource_id = ?",
                  ("study_advisories_acked", str(s["id"]))) == 1


def test_page_explains_the_advisory_and_offers_consent():
    src = _PAGE.read_text(encoding="utf-8")
    assert "prerun_advisory" in src
    assert "أقرّ بالتنبيه وأطلق" in src


def test_migration_019_is_additive_and_idempotent(tmp_path):
    """الترحيل ٠١٩ عمودٌ إضافيّ — يُطبَّق على قاعدةٍ جديدة ويُعاد بلا كسر."""
    from silk_platform import db as pdb
    sql = (_ROOT / "migrations" / "platform" /
           "019_study_advisories_ack.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE studies ADD COLUMN advisories_ack_at" in sql
    assert "DROP " not in sql.upper() and "DELETE " not in sql.upper()
    path = str(tmp_path / "p.db")
    first = pdb.apply_migrations(path)
    assert "019" in first
    assert pdb.apply_migrations(path) == []      # إعادةُ التطبيق لا تكسر شيئاً
    conn = pdb.connect(path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(studies)")}
    finally:
        conn.close()
    assert "advisories_ack_at" in cols


@pytest.mark.parametrize("change", [{"hs_code": "090111"}, {"market_pref": "JOR"}])
def test_changing_code_or_market_after_ack_withdraws_the_consent(env, monkeypatch,
                                                                  change):
    """الإقرارُ لزوجِ (رمز، سوق) بعينه — تغييرُ أيٍّ منهما يُسقِطه فيُطلَب من جديد.

    إبقاؤه كان يوافق نيابةً عن المصنع على تنبيهٍ لم يره (نفسُ العلّة التي رُفض
    لأجلها الإقرارُ الآليّ).
    """
    _force_advisory(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    s = _mk_study(env["cl"], env["tok"])
    env["cl"].patch(f"/platform/studies/{s['id']}",
                    json={"advisories_ack": True}, headers=hdr(env["tok"]))
    assert _study_row(s["id"])["advisories_ack_at"]
    r = env["cl"].patch(f"/platform/studies/{s['id']}", json=change,
                        headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert _study_row(s["id"])["advisories_ack_at"] is None
    assert _count("SELECT COUNT(*) FROM audit_log WHERE action = ? "
                  "AND resource_id = ?",
                  ("study_advisories_ack_withdrawn", str(s["id"]))) == 1


# ══════════════ R4.9 — رقمٌ لا يقرؤه أحد لا يُنشَر ═════════════════════════
def test_basic_monthly_studies_is_coerced_to_zero(env):
    """`quota` لا يقرأ `monthly_studies` لـBasic أبداً (قاعدةُ مدى الحياة) —
    فنشرُه في `/pricing` وعدٌ لا يفي به أحد."""
    from silk_platform import db as pdb, tier_config
    conn = pdb.connect()
    try:
        out = tier_config.set_tier(conn, "basic", price=0, price_annual=0,
                                   monthly_studies=9, actor_user_id=None)
        assert out["monthly_studies"] == 0
        row = conn.execute(
            "SELECT changes FROM audit_log WHERE action = 'tier_settings_changed' "
            "ORDER BY id DESC LIMIT 1").fetchone()
        assert "coerced" in str(row["changes"])
    finally:
        conn.close()
    pricing = env["cl"].get("/platform/pricing").json()
    basic = [t for t in pricing["tiers"] if t["key"] == "basic"][0]
    assert basic["monthly_studies"] == 0


def test_public_pricing_never_publishes_a_monthly_number_for_a_lifetime_tier(env):
    """حتى لو حملت القاعدةُ صفّاً قديماً — العرضُ يتبع القاعدة المنفَّذة."""
    from silk_platform import db as pdb
    from silk_platform.db import now_iso
    conn = pdb.connect()
    try:      # صفٌّ خام يتجاوز `set_tier` (تركةُ ما قبل الإكراه)
        conn.execute(
            "INSERT INTO tier_settings (tier, price, price_annual, "
            "monthly_studies, updated_at, updated_by) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(tier) DO UPDATE SET monthly_studies = 4",
            ("basic", 0, 0, 4, now_iso(), None))
        conn.commit()
    finally:
        conn.close()
    pricing = env["cl"].get("/platform/pricing").json()
    basic = [t for t in pricing["tiers"] if t["key"] == "basic"][0]
    assert basic["monthly_studies"] == 0


# ══════════════ AUTH-13 — رفضُ ما ليس لك بدلالةٍ واحدة (إغلاق R4) ════════════
def _two_factories(monkeypatch):
    """A وB من البذر القياسي — نفس نمط `tests/test_platform_isolation.py`."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    info = seed(monkeypatch)
    cl = client()
    ta = login(cl, info["factory_a"]["email"], info["factory_a"]["password"])
    tb = login(cl, info["factory_b"]["email"], info["factory_b"]["password"])
    return cl, ta, tb, info


def _denied_rows(action: str, resource_type: str, resource_id: int,
                 account_id: int) -> int:
    return _count(
        "SELECT COUNT(*) FROM audit_log WHERE action = ? AND resource_type = ? "
        "AND resource_id = ? AND account_id = ?",
        (action, resource_type, str(resource_id), account_id))


def test_classify_image_on_a_foreign_product_is_404_and_audited(monkeypatch):
    """سطحُ الرؤية على المنتج كان يرفع 404 خاماً بلا قيدِ عبورٍ — خلاف مواضع
    الكتابة الثمانية التي تمرّ بـ`_deny_write_404` (AUTH-13): تحسّسُ معرّفات
    مستأجرٍ آخر عبر هذا الباب لم يكن يترك أثراً."""
    cl, ta, tb, info = _two_factories(monkeypatch)
    prod = cl.post("/platform/products", json={"name": "تمور", "hs_code": "080410"},
                   headers=hdr(ta)).json()
    r = cl.post(f"/platform/products/{prod['id']}/classify-image", json={},
                headers=hdr(tb))
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "not_found"   # لا تسريبَ وجود (R6: رفضٌ منظَّم)
    assert _denied_rows("cross_tenant_write", "product", prod["id"],
                        info["factory_b"]["account_id"]) == 1


def test_classify_image_with_a_foreign_image_id_is_404_and_audited(monkeypatch):
    """صورةُ حسابٍ آخر عبر `image_id` في الجسم ⇒ 404 موحَّد + قيدُ قراءةٍ عابرة."""
    cl, ta, tb, info = _two_factories(monkeypatch)
    image = cl.post("/platform/images", headers=hdr(ta),
                    files={"file": ("a.png", b"\x89PNG\r\n\x1a\n-fake-bytes", "image/png")}
                    ).json()
    mine = cl.post("/platform/products", json={"name": "تمور"},
                   headers=hdr(tb)).json()
    r = cl.post(f"/platform/products/{mine['id']}/classify-image",
                json={"image_id": image["id"]}, headers=hdr(tb))
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "not_found"      # R6 (FE-6): رفضٌ منظَّم
    assert _denied_rows("cross_tenant_read", "image", image["id"],
                        info["factory_b"]["account_id"]) == 1


# ══════════════ مراجعة §58 على R4 (2026-09-05) — أقفال الملاحظات ═══════════
def _page_src() -> str:
    return _PAGE.read_text(encoding="utf-8")


def test_upload_and_storage_error_codes_have_arabic_messages():
    """(١ عالية) رمزان جديدان بلا ترجمة — المصنع كان سيقرأ الكود الإنجليزي الخام."""
    import re
    src = _page_src()
    for code in ("upload_throttled", "storage_quota_exceeded",
                 "advisory_ack_with_change", "advisory_ack_not_applicable",
                 "image_in_use"):
        assert re.search(rf"(?<![\w]){code}\s*:", src), code


def _engine_refuses_with_advisory(env, monkeypatch, *, seen: dict | None = None):
    """المحرّك (لا بوّابة المنصّة) يرفض 422 `prerun_advisory` — حالُ دراسةٍ بلا رمز
    يحسمه المحرّك من اسم المنتج فيجد شقيقَ تحذير لم تره بوّابة ما قبل المطالبة."""
    import silk_platform.engine_bridge as eb
    from fastapi import HTTPException
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    calls = {} if seen is None else seen

    def run(**kw):
        calls.update(kw)
        if not kw.get("advisories_ack"):
            raise HTTPException(status_code=422, detail={
                "error": "prerun_advisory",
                "message": "⚠ هذه السوق تحت حظر/عقوبات وفق مرجع القيود — أكمل؟",
                "advisories": [{"kind": "sanction",
                                "message": "⚠ هذه السوق تحت حظر/عقوبات وفق مرجع القيود — أكمل؟",
                                "detail": "reason"}],
                "needs_ack": True})
        return _deep_result()

    _register_gateway(monkeypatch, run)
    s = _mk_study(env["cl"], env["tok"], hs_code="")
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text          # بوّابة المنصّة لا ترى الرمز
    assert eb.wait_idle()
    return s, calls


def test_engine_side_advisory_refusal_is_actionable_on_the_draft_row(env, monkeypatch):
    """(٢ عالية) رفضُ المحرّك بعد المطالبة كان طريقاً مسدوداً: مسودّة بسببٍ لا زرَّ له.

    الآن نهايةُ التشغيلة تُسمّى `prerun_advisory` والصفّ يعرض «أقرّ بالتنبيه وأطلق».
    """
    s, _ = _engine_refuses_with_advisory(env, monkeypatch)
    row = _study_row(s["id"])
    assert row["state"] == "draft"
    assert "حظر/عقوبات" in (row["run_error"] or "")
    last = _conn().execute(
        "SELECT error_code FROM study_runs WHERE study_id = ? ORDER BY id DESC "
        "LIMIT 1", (s["id"],)).fetchone()
    assert last["error_code"] == "prerun_advisory"
    lst = env["cl"].get("/platform/studies", headers=hdr(env["tok"])).json()["studies"]
    mine = [x for x in lst if x["id"] == s["id"]][0]
    assert mine["last_run"]["error_code"] == "prerun_advisory"
    assert 'last_run.error_code === "prerun_advisory"' in _page_src()


def test_ack_is_accepted_after_an_engine_side_advisory_refusal(env, monkeypatch):
    """الإقرارُ يُقبَل حين آخرُ محاولةٍ رُفضت بتنبيهٍ من المحرّك — ثم يصل الجسمَ."""
    seen: dict = {}
    s, calls = _engine_refuses_with_advisory(env, monkeypatch, seen=seen)
    p = env["cl"].patch(f"/platform/studies/{s['id']}",
                        json={"advisories_ack": True}, headers=hdr(env["tok"]))
    assert p.status_code == 200, p.text
    assert _study_row(s["id"])["advisories_ack_at"]
    import silk_platform.engine_bridge as eb
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch",
                       headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    assert seen.get("advisories_ack") is True
    assert _study_row(s["id"])["state"] == "completed"


def test_ack_is_refused_when_nothing_is_pending(env):
    """(٤ عالية) ختمُ إقرارٍ بلا تنبيهٍ معلّق = موافقةٌ مسبقة على ما لم يُعرَض."""
    s = _mk_study(env["cl"], env["tok"])
    p = env["cl"].patch(f"/platform/studies/{s['id']}",
                        json={"advisories_ack": True}, headers=hdr(env["tok"]))
    assert p.status_code == 422, p.text
    assert p.json()["detail"]["error"] == "advisory_ack_not_applicable"
    assert _study_row(s["id"])["advisories_ack_at"] is None


def test_ack_in_the_same_body_as_a_pair_change_is_refused(env, monkeypatch):
    """(٤ عالية) إقرارٌ مع تغيير السوق في الطلب نفسه كان يُختَم للزوج الجديد الذي
    لم يُعرَض تنبيهُه قطّ — يُرفَض كاملاً قبل أيّ كتابة."""
    _force_advisory(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    s = _mk_study(env["cl"], env["tok"])
    p = env["cl"].patch(f"/platform/studies/{s['id']}",
                        json={"market_pref": "JOR", "advisories_ack": True},
                        headers=hdr(env["tok"]))
    assert p.status_code == 422, p.text
    assert p.json()["detail"]["error"] == "advisory_ack_with_change"
    row = _study_row(s["id"])
    assert row["advisories_ack_at"] is None and row["market_pref"] == "ARE"


def test_repeated_ack_is_idempotent_and_audited_once(env, monkeypatch):
    """(٨ متوسّطة) نقرةٌ ثانية على «أقرّ وأطلق» بعد فشل الإطلاق كانت تختم وتقيّد
    من جديد — موافقةٌ واحدة بثلاثة أوقات."""
    _force_advisory(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    s = _mk_study(env["cl"], env["tok"])
    for _ in range(2):
        p = env["cl"].patch(f"/platform/studies/{s['id']}",
                            json={"advisories_ack": True}, headers=hdr(env["tok"]))
        assert p.status_code == 200, p.text
    assert _count("SELECT COUNT(*) FROM audit_log WHERE action = ? "
                  "AND resource_id = ?",
                  ("study_advisories_acked", str(s["id"]))) == 1


def test_explicit_false_withdraws_the_ack(env, monkeypatch):
    """مخرجُ التراجع: `advisories_ack: false` يمسح الختم ويقيّد السحب."""
    _force_advisory(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    s = _mk_study(env["cl"], env["tok"])
    env["cl"].patch(f"/platform/studies/{s['id']}",
                    json={"advisories_ack": True}, headers=hdr(env["tok"]))
    p = env["cl"].patch(f"/platform/studies/{s['id']}",
                        json={"advisories_ack": False}, headers=hdr(env["tok"]))
    assert p.status_code == 200, p.text
    assert _study_row(s["id"])["advisories_ack_at"] is None
    assert _count("SELECT COUNT(*) FROM audit_log WHERE action = ? "
                  "AND resource_id = ?",
                  ("study_advisories_ack_withdrawn", str(s["id"]))) == 1


def test_product_change_withdraws_the_ack_when_the_study_has_no_code(env, monkeypatch):
    """(٦ متوسّطة) بلا رمزٍ صريح يحسم المحرّكُ البندَ من اسم المنتج — فتغييرُ
    المنتج يغيّر التنبيهَ الذي يسري، والإقرارُ القديم يسقط."""
    _force_advisory(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    s = _mk_study(env["cl"], env["tok"], hs_code="")
    env["cl"].patch(f"/platform/studies/{s['id']}",
                    json={"advisories_ack": True}, headers=hdr(env["tok"]))
    assert _study_row(s["id"])["advisories_ack_at"]
    p = env["cl"].patch(f"/platform/studies/{s['id']}",
                        json={"product": "ويسكي"}, headers=hdr(env["tok"]))
    assert p.status_code == 200, p.text
    assert _study_row(s["id"])["advisories_ack_at"] is None


def test_the_pre_claim_gate_is_skipped_in_quick_mode_and_on_resume(env, monkeypatch):
    """(٧ متوسّطة) بوّابةُ المنصّة كانت أشدَّ من المحرّك: المسار السريع لا يقيّم
    التنبيهات، والاستئناف يتخطّاها في الجسم — فلا رفضَ لما لن يُرفَض."""
    import silk_platform.engine_bridge as eb
    _force_advisory(monkeypatch)
    mock_engine(monkeypatch)                       # الوضع السريع (افتراض العُدّة)
    a = _mk_study(env["cl"], env["tok"])
    r = env["cl"].post(f"/platform/studies/{a['id']}/launch", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    _register_gateway(monkeypatch, lambda **kw: _deep_result())
    b = _mk_study(env["cl"], env["tok"], product="استئناف")
    conn = _conn()
    try:                                           # مؤشّرُ استئنافٍ محفوظ
        conn.execute("UPDATE studies SET analysis_id = 4242 WHERE id = ?", (b["id"],))
        conn.commit()
    finally:
        conn.close()
    r = env["cl"].post(f"/platform/studies/{b['id']}/launch", headers=hdr(env["tok"]))
    assert r.status_code == 200, r.text
    assert eb.wait_idle()


def test_concurrent_uploads_cannot_both_pass_the_storage_cap(monkeypatch):
    """(٣ عالية) المجموعُ كان يُقرأ على اتصالٍ يُغلَق قبل قراءة الجسم — رفعتان
    متزامنتان تمرّان معاً على المجموع القديم. الفحصُ الآن داخل معاملة الإدراج."""
    import threading
    import time as _t
    from silk_platform import storage
    setup_env(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STORAGE_CAP_MB_GOLD", "1")
    f = make_factory("gold", "up-race@f.local")
    body = b"\x89PNG\r\n\x1a\n" + b"x" * (700 * 1024)      # اثنتان > 1 MB، واحدة < 1 MB
    real_write = storage.write
    started = threading.Event()

    def slow_write(key, content):
        started.set()
        _t.sleep(0.4)                              # تُبقي الأولى داخل المعاملة
        real_write(key, content)

    monkeypatch.setattr(storage, "write", slow_write)
    codes: list[int] = []

    def upload():
        cl = client()
        tok = login(cl, f["email"], f["password"])
        codes.append(cl.post("/platform/images", headers=hdr(tok),
                             files={"file": ("a.png", body, "image/png")}).status_code)

    t1 = threading.Thread(target=upload)
    t1.start()
    assert started.wait(5)
    t2 = threading.Thread(target=upload)
    t2.start()
    t1.join(15)
    t2.join(15)
    assert sorted(codes) == [200, 413], codes
    assert _count("SELECT COUNT(*) FROM images WHERE owner_id = ?",
                  (f["account_id"],)) == 1


def test_delete_image_frees_storage_and_refuses_an_image_in_use(monkeypatch):
    """(٥ متوسّطة) السقف كان سقّاطةً باتجاهٍ واحد ورسالتُه تنصح بحذفٍ لا مسارَ له."""
    from silk_platform import quota, storage
    setup_env(monkeypatch)
    f = make_factory("gold", "img-del@f.local")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    img = _upload(cl, tok).json()
    conn = _conn()
    try:
        assert quota.storage_used_bytes(conn, f["account_id"]) > 0
    finally:
        conn.close()
    r = cl.delete(f"/platform/images/{img['id']}", headers=hdr(tok))
    assert r.status_code == 200, r.text
    assert not storage.exists(img["storage_key"])
    conn = _conn()
    try:
        assert quota.storage_used_bytes(conn, f["account_id"]) == 0
    finally:
        conn.close()
    used = _upload(cl, tok, filename="b.png").json()
    prod = cl.post("/platform/products",
                   json={"name": "تمور", "image_id": used["id"]},
                   headers=hdr(tok)).json()
    assert prod.get("image_id") == used["id"]
    r = cl.delete(f"/platform/images/{used['id']}", headers=hdr(tok))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "image_in_use"
    other = make_factory("gold", "img-del-b@f.local")
    tb = login(cl, other["email"], other["password"])
    r = cl.delete(f"/platform/images/{used['id']}", headers=hdr(tb))
    assert r.status_code == 404, r.text
    assert _count("SELECT COUNT(*) FROM audit_log WHERE action = ? AND "
                  "resource_type = 'image' AND resource_id = ? AND account_id = ?",
                  ("cross_tenant_delete", str(used["id"]), other["account_id"])) == 1


def test_boot_guard_refuses_fake_engine_in_production(monkeypatch):
    """(٩ متوسّطة) مقعدُ الرُتبتين ٢–٣ يقدّم عيّنةً مصطنعة بدل المحرّك — تحت إشارة
    إنتاج يُرفَض الإقلاع كما يُرفَض مفتاحُ كشف رمز إعادة التعيين."""
    from silk_platform.api import boot_config_guard
    monkeypatch.setenv("SILK_PLATFORM_SECRET", "a-real-secret")
    monkeypatch.setenv("SILK_PLATFORM_BCRYPT_ROUNDS", "12")
    monkeypatch.delenv("SILK_PLATFORM_EXPOSE_RESET_TOKEN", raising=False)
    monkeypatch.setenv("SILK_PLATFORM_FAKE_ENGINE", "deep")
    monkeypatch.setenv("SILK_PLATFORM_SECURE_COOKIES", "1")
    with pytest.raises(RuntimeError):
        boot_config_guard()
    monkeypatch.delenv("SILK_PLATFORM_SECURE_COOKIES", raising=False)
    boot_config_guard()                            # مسموحٌ تطويرياً


def test_shaped_json_on_study_titles_and_image_id_is_a_client_fault(env):
    """(١٠ منخفضة) قائمةٌ مكان نصّ العنوان كانت 500 عند الكتابة؛ وقائمةٌ مكان
    `image_id` في سطح الرؤية كانت TypeError بعد استهلاك خانة الرؤية."""
    r = env["cl"].post("/platform/studies",
                       json={"product": "تمور", "title_ar": ["x"],
                             "description_ar": {"y": 1}},
                       headers=hdr(env["tok"]))
    assert r.status_code < 500, r.text
    s = _mk_study(env["cl"], env["tok"])
    r = env["cl"].patch(f"/platform/studies/{s['id']}", json={"title_en": ["z"]},
                        headers=hdr(env["tok"]))
    assert r.status_code < 500, r.text
    prod = _mk_product(env["cl"], env["tok"])
    r = env["cl"].post(f"/platform/products/{prod['id']}/classify-image",
                       json={"image_id": [1]}, headers=hdr(env["tok"]))
    assert r.status_code == 422, r.text


def test_advisory_refusal_note_has_no_doubled_prefix(env, monkeypatch):
    """الواجهة تسبق السبب بـ«لم تنطلق آخر محاولة:» — فلا يحمل السببُ البادئة نفسها."""
    _force_advisory(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "deep")
    _register_gateway(monkeypatch, lambda **kw: _deep_result())
    s = _mk_study(env["cl"], env["tok"])
    r = env["cl"].post(f"/platform/studies/{s['id']}/launch", headers=hdr(env["tok"]))
    assert r.status_code == 422
    assert not (_study_row(s["id"])["run_error"] or "").startswith("لم تنطلق")
