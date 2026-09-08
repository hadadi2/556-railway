"""قفلا إصلاح الملاحظتين الأمنيتين من مراجعة §58 الموجة ٩ (قرار مالك 2026-08-26).

المالك أخرج ملاحظتين من قاعدة «لا صنف عيب جديد» (كانت عن توسيع النطاق لا عن
ترك خانق مكسور في الإنتاج):
1. خانق إعادة تعيين كلمة المرور: `record_failure` بلا `limits` يشذّب صفوف
   الهوية على نافذة الدخول (300ث) بينما `is_throttled` يعدّ على 3600ث —
   السقف المعلن «5/ساعة» فعلياً ~4 كل 5 دقائق (درس 187).
2. حارسا البوابة `min_pillars_scored` و`pillar_narrative_sync` يقرآن
   `markets[0]["decision"]` بينما `build_view` يبني `entry_decision`
   (silk_render.py:3170) — ميّتان على العرض الفعلي واختباراتهما تبني المفتاح
   يدوياً فتخضرّ (درس 186، عائلة الدرس 98).

الاختبارات كُتبت أولاً وفشلت على الشيفرة المعطوبة (test-first lock).
Hermetic: platform DB معزولة، لا شبكة، لا مفاتيح.
"""
from __future__ import annotations

import datetime
import pathlib
import re

from tests.platform_helpers import client, seed, setup_env

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _backdate_row(conn, ident: str, seconds: int) -> None:
    """صفّ محاولة مؤرّخ في الماضي — يحاكي مرور الوقت بلا تجميد ساعة."""
    ts = (datetime.datetime.now(datetime.timezone.utc)
          - datetime.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute("INSERT INTO login_attempts (identity, created_at) VALUES (?,?)",
                 (ident, ts))
    conn.commit()


# ── ١) خانق PWRESET — النافذة المعلنة ساعة تصمد ساعة فعلاً ────────────────

def test_pwreset_request_cap_holds_for_the_full_declared_hour(monkeypatch):
    """الحادثة: 4 طلبات كل >5 دقائق كانت تمحو التاريخ الأقدم من 300ث عند كل
    إدراج، فيتجدد السقف كل 5 دقائق. البذر = 4 طلبات عمرها 6 دقائق؛ الخامس
    يُسمح والسادس يُخنق 429 — على الشيفرة المعطوبة الخامس كان يمحو الأربعة
    فيمرّ السادس."""
    info = seed(monkeypatch)
    from silk_platform import db as pdb, throttle
    email = info["factory_a"]["email"]
    conn = pdb.connect()
    try:
        for _ in range(4):
            _backdate_row(conn, throttle.identity("pwreset", "testclient"), 360)
            _backdate_row(conn, throttle.identity(f"pwreset|{email}", None), 360)
    finally:
        conn.close()
    with client() as cl:
        r5 = cl.post("/platform/auth/password-reset/request",
                     json={"email": email})
        assert r5.status_code == 200, r5.text
        r6 = cl.post("/platform/auth/password-reset/request",
                     json={"email": email})
        assert r6.status_code == 429, (
            "سقف «5/ساعة» انكسر: الطلب السادس داخل الساعة مرّ — الإدراج "
            "الخامس محا صفوفاً ما تزال داخل نافذة PWRESET")


def test_pwreset_confirm_cap_holds_for_the_full_declared_hour(monkeypatch):
    """نفس العائلة على نقطة التأكيد (silk_platform/api.py — مسار الرمز):
    تخمين رموز بمعدل 4 كل 5 دقائق كان يبقى تحت السقف إلى الأبد."""
    seed(monkeypatch)
    from silk_platform import db as pdb, throttle
    conn = pdb.connect()
    try:
        for _ in range(4):
            _backdate_row(conn, throttle.identity("pwreset-confirm",
                                                  "testclient"), 360)
    finally:
        conn.close()
    with client() as cl:
        r5 = cl.post("/platform/auth/password-reset/confirm",
                     json={"token": "bogus", "new_password": "GoodPass123"})
        assert r5.status_code == 400, r5.text   # رمز باطل — والمحاولة تُعدّ
        r6 = cl.post("/platform/auth/password-reset/confirm",
                     json={"token": "bogus", "new_password": "GoodPass123"})
        assert r6.status_code == 429, (
            "سقف تخمين رموز إعادة التعيين انكسر داخل الساعة المعلنة")


def test_prune_respects_the_longest_named_window(monkeypatch):
    """مسار المحو الثاني: مهمة `session_cleanup` تكنس عبر `throttle.prune`
    الذي كان يحذف كل الصفوف الأقدم من نافذة الدخول أياً كانت هويتها —
    فيمحو صفوف PWRESET التي ما تزال داخل ساعتها."""
    setup_env(monkeypatch)
    from silk_platform import db as pdb, throttle
    conn = pdb.connect()
    try:
        keep = throttle.identity("pwreset", "10.0.0.9")
        drop = throttle.identity("user@x.example", "10.0.0.9")
        _backdate_row(conn, keep, 600)      # داخل نافذة PWRESET (3600ث)
        _backdate_row(conn, drop, 7200)     # خارج كل النوافذ المسجّلة
        throttle.prune(conn)
        idents = {r[0] for r in conn.execute(
            "SELECT identity FROM login_attempts").fetchall()}
        assert keep in idents, "الكنس محا صفّ pwreset داخل ساعته المعلنة"
        assert drop not in idents, "الكنس أبقى صفاً خارج أطول نافذة"
    finally:
        conn.close()


def test_every_named_counter_prefix_has_a_registered_window():
    """قفل انجراف (نمط قفل PILLAR_FEEDING): أي عدّاد مسمّى جديد في
    silk_platform/api.py يجب أن يسجّل نافذته في `NAMED_WINDOW_DEFAULTS`
    وإلا كنسه `prune` قبل أوانه صامتاً.

    درس 190 (F11): القفل كان يفحص **التسجيل** فقط، فعدّادٌ بنافذةٍ صريحة
    مخالفة (`named_limits("PDF", 10, 7200)`) كان يمرّ بينما `prune` يكنسه
    عند 300ث — نفس عيب 187 مُعاداً أخضر. الآن **كل** بادئة تمرّر وسيطاً
    ثالثاً تُطابَق نافذتُها بالمسجّلة."""
    from silk_platform import throttle
    src = (_ROOT / "silk_platform" / "api.py").read_text(encoding="utf-8")
    prefixes = set(re.findall(r'named_limits\("([A-Z]+)"', src))
    assert prefixes >= {"PWRESET", "CHECKOUT"}, "إبرة الاستخراج انكسرت"
    missing = prefixes - set(throttle.NAMED_WINDOW_DEFAULTS)
    assert not missing, f"عدّادات مسمّاة بلا نافذة مسجّلة للكنس: {sorted(missing)}"
    # اتفاق النافذة (F11): كل `named_limits("X", max, window)` بوسيطٍ ثالثٍ
    # صريح يجب أن يساوي `window` المسجَّل — وإلا انجرفت القراءة عن الكنس.
    for prefix, window in re.findall(
            r'named_limits\("([A-Z]+)",\s*\d+,\s*(\d+)\)', src):
        assert int(window) == throttle.NAMED_WINDOW_DEFAULTS[prefix], (
            f"نافذة {prefix} الصريحة {window} تخالف المسجَّلة "
            f"{throttle.NAMED_WINDOW_DEFAULTS[prefix]} — سينجرف الكنس")


def test_pwreset_record_failure_call_sites_pass_their_limits():
    """الإبرة النصية على مواضع الحادثة الثلاثة — الاختبار السلوكي أعلاه يغطي
    مسار IP، وهذه تضمن هوية البريد أيضاً (خنقها بالتدوير لا يلتقطه
    TestClient أحادي الهوية — حدّ معلن)."""
    src = (_ROOT / "silk_platform" / "api.py").read_text(encoding="utf-8")
    assert "throttle.record_failure(conn, ident_ip, limits)" in src
    # درس 190 (F2): عدّاد البريد صار بحدوده المستقلّة الأعلى (email_limits).
    assert "throttle.record_failure(conn, ident_email, email_limits)" in src


# ── ٢) حارسا البوابة يقرآن مفتاح العرض الحقيقي ───────────────────────────

def test_min_pillars_guard_fires_on_the_real_view_key():
    """`build_view` يبني `entry_decision` (silk_render.py:3170) — الحارس كان
    يقرأ «decision» فلا يطلق أبداً على أي عرض فعلي، واختباره كان يبني المفتاح
    يدوياً فيخضرّ زوراً (درس 186)."""
    import silk_quality_gate as QG
    view = {"deep_research": {"report": {"text": "نص"}, "missions": {}},
            "markets": [{"entry_decision": {
                "schema": "silk.decision/v1", "score": 0.84,
                "pillars": {"competition": {"value": 0.16},
                            "market": {"value": None},
                            "regulatory": {"value": None},
                            "profit": {"value": None},
                            "risk": {"value": None}}}}]}
    out = QG.run_quality_gate(view)
    assert any(f["check"] == "min_pillars_scored" for f in out["findings"])
    assert out["verdict"] == QG.FAIL


def test_pillar_narrative_sync_fires_on_the_real_view_key():
    import silk_quality_gate as QG
    view = {"deep_research": {"missions": {}, "report": {
        "text": "استقر سعر الصرف للدينار عند 0.71."}},
        "markets": [{"entry_decision": {
            "schema": "silk.decision/v1", "score": 0.5,
            "pillars": {"risk": {"value": 0.4,
                                 "missing": ["fx_stability"]}}}}]}
    assert any(f["check"] == "pillar_narrative_sync"
               for f in QG._check_pillar_narrative_sync(view))


def test_legacy_decision_key_stays_covered_as_fallback():
    """مستهلك قديم يمرّر صفوفاً خاماً بمفتاح «decision» يبقى مغطى — الاحتياط
    معلن في الدالتين لا سلوك عرضي."""
    import silk_quality_gate as QG
    legacy = {"deep_research": {"report": {"text": "نص"}, "missions": {}},
              "markets": [{"decision": {
                  "schema": "silk.decision/v1", "score": 0.84,
                  "pillars": {"competition": {"value": 0.16}}}}]}
    assert any(f["check"] == "min_pillars_scored"
               for f in QG._check_min_pillars_scored(legacy))
