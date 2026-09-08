"""التكلفة الداخلية أدمِن حصراً — internal research cost is admin-only.

قرار المالك (2026-08-17) حرفياً: «إخفاء التكلفة من داشبورد العميل وتخليها في
داشبورد الأدمِن عشان أشوف». التدقيق أثبت أن تكلفة البحث لا تصل أي سطح مصنع
اليوم (دراسات المنصّة حملات بريد؛ التكلفة في واجهة المشغّل المحمية بمفتاح API)
— لكن **بلا حارس يمنع تسريبها مستقبلاً**، خاصة عند بناء جسر المنصّة⇄المحرّك
لاحقاً. هذه الأقفال تجعل القرار بنيوياً:

1. ردود كل نقطة يراها دور factory لا تحمل أي مفتاح تكلفة داخلية.
2. `GET /platform/admin/metrics` (أدمِن حصراً) يحمل `research_costs` — فجوة
   معلنة عند غياب قاعدة المحرّك، وأرقام حقيقية عند حضورها (لا صفر مختلَق).
3. صفحة المنصّة: قسم التكاليف مربوط بدور `silk_admin` في جدول الأقسام حصراً.
4. هوية سِلك: ألوان الصفحتين تطابق `config/branding.yaml` ميكانيكياً.
5. حلقة «نسيت كلمة المرور» مكتملة: الرابط المُرسَل بالبريد يقود لصفحة موجودة.

محتوى مصنع لا يبلغه هذا الملف؛ كله هرمتي (قاعدة معزولة، لا شبكة، لا مفاتيح).
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.platform_helpers import (client, hdr, login, make_factory,
                                    make_product_study, mock_engine, seed)

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PAGE = (_ROOT / "web" / "platform.html").read_text(encoding="utf-8")
_RESET = (_ROOT / "web" / "reset-password.html").read_text(encoding="utf-8")
_LANDING = (_ROOT / "web" / "platform-landing.html").read_text(encoding="utf-8")

# المفاتيح الممنوعة على أي سطح مصنع — المصدر الواحد في جسر المحرّك نفسه
# (`engine_bridge._COST_KEYS` هي التي يجرّدها `strip_cost_keys` بنيوياً) —
# استيرادها هنا يضمن أن الكنس والحارس لا ينحرفان أبداً.
from silk_platform.engine_bridge import _COST_KEYS  # noqa: E402


def _keys_deep(obj) -> set:
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            out |= _keys_deep(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _keys_deep(v)
    return out


# ═══════════ ١ — ردود المصنع بلا أي مفتاح تكلفة داخلية ═══════════════════════
def test_every_factory_facing_response_carries_no_internal_cost_key(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "cost-факtory@example.com")
    eb = mock_engine(monkeypatch, analysis_id=4242)
    cl = client()
    tok = login(cl, f["email"], f["password"])
    sid = make_product_study(f["account_id"], f["user_id"])
    assert cl.post(f"/platform/studies/{sid}/launch",
                   headers=hdr(tok)).status_code == 200
    assert eb.wait_idle(15)
    paths = ["/me", "/entitlements", "/wallet", "/wallet/ledger?limit=50",
             "/studies", f"/studies/{sid}", "/images",
             "/audit?limit=50"]
    for p in paths:
        r = cl.get(f"/platform{p}", headers=hdr(tok))
        assert r.status_code == 200, f"{p}: {r.status_code}"
        leaked = _keys_deep(r.json()) & _COST_KEYS
        assert not leaked, f"{p}: مفاتيح تكلفة داخلية على سطح مصنع: {leaked}"
    # تقرير الدراسة — أهم مُسلَّم يراه المصنع (جسر المحرّك). نُطعم عرضاً
    # ملوَّثاً بكل مفاتيح التكلفة عمداً ونؤكد التجريد البنيوي.
    import silk_render
    import silk_storage
    monkeypatch.setattr(silk_storage, "get_analysis",
                        lambda i, path=None: {"id": i, "product": "تمور"})
    monkeypatch.setattr(
        silk_render, "build_view",
        lambda found, lang="ar": {"brief": "خلاصة",
                       **{k: 1.0 for k in _COST_KEYS},
                       "markets": [{"name": "قطر",
                                    **{k: 2.0 for k in _COST_KEYS}}]})
    rep = cl.get(f"/platform/studies/{sid}/report", headers=hdr(tok))
    assert rep.status_code == 200, rep.text
    leaked = _keys_deep(rep.json()) & _COST_KEYS
    assert not leaked, f"تقرير الدراسة يحمل مفاتيح تكلفة داخلية: {leaked}"


def test_factory_cannot_reach_the_admin_metrics_surface(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "cost-403@example.com")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    assert cl.get("/platform/admin/metrics", headers=hdr(tok)).status_code == 403


# ═══════════ ٢ — سطح الأدمِن يحمل التكاليف (فجوة معلنة أو أرقام حقيقية) ═══════
def test_admin_metrics_declare_the_gap_when_the_engine_db_is_absent(monkeypatch):
    info = seed(monkeypatch)
    monkeypatch.setenv("SILK_DB", "/nonexistent-dir/nope.db")
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    rc = cl.get("/platform/admin/metrics", headers=hdr(tok)).json()["research_costs"]
    # قاعدة محرّك غائبة ⇒ فجوة معلنة أو قائمة فارغة — **لا رقم مختلَق أبداً**.
    if rc["available"]:
        assert rc["recent"] == [] and rc["recent_total_usd"] == 0.0
        assert rc["recent_priced_runs"] == 0
    else:
        assert rc.get("note"), "الفجوة بلا ملاحظة تشرحها"


def test_admin_metrics_surface_real_engine_costs_when_present(monkeypatch, tmp_path):
    info = seed(monkeypatch)
    db = str(tmp_path / "silk.db")
    monkeypatch.setenv("SILK_DB", db)
    import silk_storage
    aid = silk_storage.save_analysis({"product": "تمور"}, path=db)
    # التكلفة عمود جانبي مشتق من العرض؛ نثبّتها مباشرة في المخزن المعزول
    # (تثبيت اختبار على قاعدة مؤقتة — لا مساس بقاعدة حقيقية).
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE analyses SET cost_usd = '2.50', "
                     "market_name = 'قطر' WHERE id = ?", (aid,))
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    rc = cl.get("/platform/admin/metrics", headers=hdr(tok)).json()["research_costs"]
    assert rc["available"] is True
    row = next(r for r in rc["recent"] if r["id"] == aid)
    assert row["cost_usd"] == 2.5 and row["market"] == "قطر"
    assert rc["recent_total_usd"] == 2.5 and rc["recent_priced_runs"] == 1


# ═══════════ ٣ — الصفحة: قسم التكاليف أدمِن حصراً ════════════════════════════
def test_costs_section_is_admin_only_in_the_sections_table():
    m = re.search(r"const SECTIONS = \[(.*?)\n\];", _PAGE, re.S)
    assert m, "جدول الأقسام غير موجود"
    row = next((ln for ln in m.group(1).splitlines()
                if "adminCostsPanel" in ln), None)
    assert row, "قسم تكاليف البحث غائب عن جدول الأقسام"
    assert 'role: "silk_admin"' in row, (
        "قسم التكاليف ليس مقصوراً على الأدمِن — خرقٌ لقرار المالك")
    # ودالّة عرض التكاليف تُستدعى من مسار الأدمِن فقط.
    admin_body = _PAGE[_PAGE.index("async function loadAdmin"):
                       _PAGE.index("function renderResearchCosts")]
    assert "renderResearchCosts" in admin_body
    # مرساة نهاية مسار المصنع: `loadHome` تلي `loadFactory` مباشرةً منذ حذف
    # جدول المزايا (كانت `const UNLOCKS` — قرار 2026-08-18).
    factory_body = _PAGE[_PAGE.index("async function loadFactory"):
                         _PAGE.index("async function loadHome")]
    assert "renderResearchCosts" not in factory_body
    assert "research_costs" not in factory_body


# ═══════════ ٤ — هوية سِلك تُطابِق branding.yaml ميكانيكياً ══════════════════
def _branding() -> dict:
    out = {}
    for line in (_ROOT / "config" / "branding.yaml").read_text(
            encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


# `ids` صريحة: بلاها يبني pytest معرّفَ الاختبار من **محتوى الصفحة كاملاً**
# (مئاتُ الكيلوبايتات) فيتجاوز حدَّ طول المسار على ويندوز ويسقط الاختبارُ
# في التهيئة قبل أن يقيس شيئاً. الاسمُ هو المعرّف الطبيعي أصلاً.
_page_id = lambda v: v if isinstance(v, str) and v.endswith(".html") else ""


@pytest.mark.parametrize("page,name", [(_PAGE, "platform.html"),
                                       (_RESET, "reset-password.html"),
                                       (_LANDING, "platform-landing.html"),
                                       ((_ROOT / "web" / "checkout.html")
                                        .read_text(encoding="utf-8"),
                                        "checkout.html")],
                         ids=_page_id)
def test_page_colors_match_the_official_branding_file(page, name):
    """ألوان الصفحات من `config/branding.yaml` — لا هوية ثانية تنحرف.

    الصفحة ثابتة فلا تقرأ الملف وقت التشغيل؛ هذا الحارس هو آلية المزامنة:
    تغيير الهوية في الملف بلا تحديث الصفحات يُحمِّر البناء فوراً.

    **قرار المالك 2026-08-20 ينسخ قرار «نمط Stripe» (2026-08-18).** اللوحة
    السابقة كانت لوحة Stripe الحرفية (`#635BFF` نيلي، `#1A1F36` حبر،
    `#E3E8EE` حدود) — هوية شركة أخرى شُحنت في منتجنا، ومرّ ذلك من كل
    الحرّاس لأن الحارس كان يطابق **ملف الهوية** لا **مصدر** قيمه. اللوحة
    المعتمدة اليوم أزرق سِلك `#2563EB` بسلّمه الكامل، والذهبي الرسمي لم يعد
    لون واجهة (مخطط/علامة فقط — البند ٢ من أمر المالك).

    الفصل يبقى ثنائي الاتجاه على محورٍ جديد: الداشبورد على سلّم `dashboard_*`،
    والهبوط/الدفع/إعادة التعيين على `platform_*` الداكنة، وتقارير Word/PDF على
    `primary_color` الكحلي — ولا لون يعبر حدَّه في أيّ اتجاه.
    """
    b = _branding()
    # نيلي Stripe ممنوع على **كل** صفحة — لا أثر لهوية شركة أخرى في المنتج.
    assert "#635BFF" not in page, (
        f"{name}: نيلي Stripe عاد — الهوية المستعارة ممنوعة (قرار 2026-08-20)")
    assert "#1A1F36" not in page, (
        f"{name}: حبر Stripe عاد — الهوية المستعارة ممنوعة")
    if name == "platform.html":
        # داشبورد المصنع: سلّم أزرق سِلك كاملاً من الملف، لا قيمة مبعثرة.
        assert f"--pri:#{b['dashboard_primary_color']}" in page, (
            f"{name}: أساسي الداشبورد لا يطابق dashboard_primary_color "
            f"({b['dashboard_primary_color']})")
        for key in ("dashboard_primary_dark", "dashboard_primary_active",
                    "dashboard_primary_soft", "dashboard_primary_light",
                    "dashboard_ink_color", "dashboard_muted_color",
                    "dashboard_line_color", "dashboard_bg_color"):
            assert f"#{b[key]}" in page, (
                f"{name}: درجة السلّم {key} ({b[key]}) غائبة عن الداشبورد")
        assert f"#{b['secondary_color']}" in page, (
            f"{name}: الذهبي الرسمي غائب ({b['secondary_color']})")
        # الذهبي ليس لون واجهة (أمر المالك ٢026-08-20، البند ٢): لا يصير
        # أساسياً ولا لون الحالة النشطة في الشريط الجانبي.
        assert f"--pri:#{b['secondary_color']}" not in page, (
            f"{name}: الذهبي صار أساسيَّ الواجهة — ممنوع (لوحة/علامة فقط)")
        # الفصل بالاتجاهين: لا لوحة الهبوط الداكنة ولا كحلي التقارير أساساً.
        assert f"--pri:#{b['platform_primary_color']}" not in page, (
            f"{name}: عاد أساسُ الهبوط الداكن أساسَ الداشبورد — الفصل انهار")
        assert f"#{b['platform_accent_color']}" not in page, (
            f"{name}: لون تمييز الهبوط الداكن ما يزال في الداشبورد")
        assert f"--pri:#{b['primary_color']}" not in page, (
            f"{name}: كحلي التقارير صار أساسَ الداشبورد — الفصل انهار")
        return
    assert f"--pri:#{b['platform_primary_color']}" in page, (
        f"{name}: أساسي المنصّة لا يطابق platform_primary_color "
        f"({b['platform_primary_color']})")
    assert f"#{b['platform_primary_dark']}" in page, (
        f"{name}: درجة الغمق platform_primary_dark غائبة")
    assert f"#{b['platform_accent_color']}" in page, (
        f"{name}: لون التمييز اللافت platform_accent_color غائب")
    assert f"#{b['secondary_color']}" in page, (
        f"{name}: الذهبي الرسمي غائب ({b['secondary_color']})")
    # أزرق الداشبورد لا يتسرّب لصفحات الهوية الداكنة، وكحلي التقارير لم يعد
    # أساسيَّ صفحةٍ — مكانه الوحيد Word/PDF (§58: الفصل بالاتجاهين لا نصفه).
    assert f"#{b['dashboard_primary_color']}" not in page, (
        f"{name}: أزرق الداشبورد تسرّب لصفحةٍ على هوية سِلك الداكنة")
    assert f"#{b['dashboard_primary_dark']}" not in page, (
        f"{name}: درجة hover للداشبورد تسرّبت لصفحة الهوية الداكنة")
    assert f"--pri:#{b['primary_color']}" not in page, (
        f"{name}: كحلي التقارير ما يزال أساسيَّ الصفحة — الفصل انهار")


def test_report_navy_identity_is_untouched():
    """تقارير Word/PDF تبقى بالكحلي الرسمي — قارئها الحقيقي `_load_branding`
    يرى `primary_color=1B3B6F` كما كان (الفصل نصفه الثاني)."""
    import silk_reports
    b = silk_reports._load_branding()  # noqa: SLF001 — نفس قارئ الإنتاج
    assert b.get("primary_color") == "1B3B6F"
    assert b.get("secondary_color") == "C9A227"


# ═══════════ ٥ — حلقة «نسيت كلمة المرور» مكتملة ═════════════════════════════
def test_the_emailed_reset_link_leads_to_a_real_page(monkeypatch):
    """`{base}/reset-password?token=…` (الرابط المُرسَل فعلاً) يصل الصفحة.

    قبل هذه الموجة: الخلفية كاملة والرابط يقود 404 — أول مستخدم ينسى كلمته
    كان سيعلق ويحتاج دعماً يدوياً.
    """
    seed(monkeypatch)
    cl = client()
    r = cl.get("/reset-password?token=abc", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/reset-password.html?token=abc"
    # والصفحة نفسها موجودة وتستدعي نقطة التأكيد الحقيقية.
    assert (_ROOT / "web" / "reset-password.html").exists()
    assert "/platform/auth/password-reset/confirm" in _RESET
    assert 'get("token")' in _RESET


def test_login_screen_offers_the_forgot_password_path():
    assert 'id="forgotBtn"' in _PAGE, "لا رابط «نسيت كلمة المرور» على شاشة الدخول"
    assert "/auth/password-reset/request" in _PAGE


def test_reset_confirm_flow_works_end_to_end(monkeypatch):
    """الرمز الصادر يُستهلك عبر النقطة التي تستدعيها الصفحة — ويُبطل الجلسات."""
    monkeypatch.setenv("SILK_PLATFORM_EXPOSE_RESET_TOKEN", "1")
    seed(monkeypatch)
    f = make_factory("silver", "reset-e2e@example.com")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    r = cl.post("/platform/auth/password-reset/request",
                json={"email": f["email"]})
    raw = r.json().get("reset_token")
    assert raw, "علم الاختبار لم يُرجِع الرمز"
    r2 = cl.post("/platform/auth/password-reset/confirm",
                 json={"token": raw, "new_password": "NewSecret123"})
    assert r2.status_code == 200
    # الجلسة القديمة أُبطلت والكلمة الجديدة تعمل.
    assert cl.get("/platform/me", headers=hdr(tok)).status_code == 401
    login(cl, f["email"], "NewSecret123")


# ═══════════ كنس أكواد الأخطاء: كل كود يصدره الخادم له رسالة عربية ═══════════
def test_every_server_emitted_error_code_has_an_arabic_message():
    """يمسح مصادر `silk_platform` لكل كود خطأ ويطابقه بخريطة `ERR_AR`.

    **الحادثة:** الخادم يرسل `quota_exceeded` والخريطة كانت تحمل
    `quota_exhausted` — فرأى المصنع النصّ الإنجليزي الخام عند نفاد الحصّة.
    قاعدة هذا الحارس: الكنس آلي من المصدر لا قائمة يدوية تتقادم (نفس مبدأ
    «تغطية المُطهِّر تُكنَس من الحارس نفسه» — الدرس ١١).
    """
    src = ""
    for p in sorted((_ROOT / "silk_platform").glob("*.py")):
        src += p.read_text(encoding="utf-8")
    codes = set(re.findall(r'"error"\s*:\s*"([a-z_]+)"', src))
    # R6 (FE-6): الرفوضُ المنظَّمة عبر `_err(status, "code", …)` تُكنَس أيضاً.
    codes |= set(re.findall(r'_err\(\s*\d+,\s*"([a-z_]+)"', src))
    codes |= set(re.findall(r'(?:LifecycleError|TierChangeError)\(\s*\n?\s*"([a-z_]+)"', src))
    codes |= set(re.findall(r'"reason"\s*:\s*"([a-z_]+_quota_exceeded)"', src))
    codes |= {"monthly_quota_exceeded", "lifetime_quota_exceeded",
              "user_quota_exceeded"}   # أسباب quota.reserve_launch المُركَّبة
    m = re.search(r"const ERR_AR = \{(.*?)\n\};", _PAGE, re.S)
    assert m, "خريطة ERR_AR غير موجودة في الصفحة"
    mapped = set(re.findall(r"(?m)^\s*([a-z_]+)\s*:", m.group(1)))
    missing = codes - mapped
    assert not missing, (
        f"أكواد يصدرها الخادم بلا رسالة عربية في الصفحة: {sorted(missing)}")


if __name__ == "__main__":
    import subprocess
    import sys
    sys.exit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
