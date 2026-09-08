"""حارس اكتمال حذف المقاعد — the seats-deletion completeness guard.

قرار المالك (2026-08-19): حذف «المقاعد» — المستخدمين الفرعيين داخل حساب
المصنع — نهائياً. سابقتُه أمرُ 2026-08-18 («احذف المستخدمون لانه مستخدم واحد
فقط») الذي نُفِّذ في **الواجهة وحدها** فبقي الإنفاذ كلّه في الخادم: وحدة
`users.py` وستّ نقاط HTTP وبوّابة `require_seat` وحقلٌ في كل باقة ووعدٌ في
صفحتَي البيع. هذا الحارس يُكمِل الحذف ويمنع عودته:

١) لا مسار HTTP للمستخدمين الفرعيين مسجَّلاً في تطبيق المنصّة.
٢) لا وحدة `users.py` على القرص ولا استيراد لها.
٣) لا رمز مقاعد في الاستحقاقات/الباقات/التسعير.
٤) لا أثر مقاعد في صفحة المنصّة ولا في قواميس الترجمة ولا في صفحتَي البيع.
٥) **والمقابل — الأهمّ:** جدول `users` ودورة الدخول والهويّة تبقى سليمة.

الخامس هو ما يميّز هذا الحارس عن حارس حذف التنقيب: هناك حُذفت وحداتٌ لا يعتمد
عليها شيء، وهنا يُمَسّ جدولٌ **يحمل تسجيل الدخول نفسه** — فحارسٌ يقيس الغياب
وحده يشجّع، عند أول فشل، على حذفٍ أوسع يكسر المصادقة. ما يبقى يُقاس كما يذهب.
"""
from __future__ import annotations

import pathlib
import re

from tests.platform_helpers import client, hdr, login, make_factory, seed, setup_env

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "silk_platform"

# `/admin/users/{id}/reset` مسارُ أدمِن لإعادة تعيين كلمة مرور — ليس مقعداً.
_BANNED_ROUTE_RE = re.compile(r"^/platform/users(/|$)")


def test_no_sub_user_route_is_registered(monkeypatch):
    setup_env(monkeypatch)
    from silk_platform.api import create_platform_app
    paths = {getattr(r, "path", "") for r in create_platform_app().routes}
    leftovers = {p for p in paths if _BANNED_ROUTE_RE.match(p)}
    assert not leftovers, f"مسارات مستخدمين فرعيين ما تزال مسجَّلة: {sorted(leftovers)}"
    # ومسارُ الأدمِن يبقى — الحذف لا يبتلع ما ليس منه.
    assert any(p.endswith("/admin/users/{user_id}/reset") for p in paths), (
        "مسار إعادة تعيين كلمة المرور الأدمِني اختفى مع حذف المقاعد")


def test_users_module_is_gone_and_unimported():
    assert not (_PKG / "users.py").exists(), (
        "silk_platform/users.py عاد — إدارةُ مستخدمين فرعيين محذوفة بقرار مالك")
    for path in _PKG.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue          # الذكر في شرحٍ يؤرّخ القرار مشروع
            assert not re.search(r"\busers\s+as\b|\bfrom \.users\b", stripped), (
                f"{path.name}: ما يزال يستورد وحدة المستخدمين الفرعيين")


def test_seat_symbols_are_gone_from_entitlements_tiers_and_pricing():
    ent = (_PKG / "entitlements.py").read_text(encoding="utf-8")
    for needle in ("def seat_limit", "def seats_used", "def require_seat",
                   "def _tiers_with_more_seats", "seats_limit:",
                   '"seats_exceed_target_tier"'):
        assert needle not in ent, (
            f"silk_platform/entitlements.py: {needle} عاد — بوّابة المقاعد محذوفة")
    models = (_PKG / "models.py").read_text(encoding="utf-8")
    assert not re.search(r"\n *users: int", models), (
        "TierLimits.users عاد — الباقات بلا سقف مستخدمين بقرار المالك")
    pricing = (_PKG / "pricing.py").read_text(encoding="utf-8")
    assert '"seats"' not in pricing, (
        "حمولة التسعير العامّة تَعِد بمقاعد لا إنفاذ لها")


def test_no_seat_surface_survives_in_any_page():
    page = (_ROOT / "web" / "platform.html").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", " ", page, flags=re.S)      # الشروح تؤرّخ القرار
    for needle in ("seats_k", "th_seats", "sSeats", "sBar", "seats_limit",
                   "seats_used", "seat_limit_reached", "seats_exceed_target_tier"):
        assert needle not in code, f"web/platform.html: {needle} عاد"
    assert not re.search(r'key:\s*"users"', code), "قسم المستخدمين عاد للتنقّل"
    # وعدُ البيع يسقط مع الإنفاذ — وعدٌ بلا سقف أسوأ من الاثنين.
    for name in ("checkout.html", "platform-landing.html", "pricing.html", "marketing.js"):
        sales = (_ROOT / "web" / name).read_text(encoding="utf-8")
        assert "seats" not in sales.lower(), f"web/{name}: وعد المقاعد ما يزال معروضاً"


def test_the_login_identity_survives_intact(monkeypatch):
    """الاختبار المضادّ — ما يبقى مُقاسٌ كما ما يذهب."""
    from silk_platform import db as pdb
    info = seed(monkeypatch)
    conn = pdb.connect()
    try:
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    finally:
        conn.close()
    for t in ("users", "sessions", "accounts"):
        assert t in tables, f"جدول {t} اختفى — الدخول مستحيل بدونه"
    for c in ("account_id", "email", "password_hash", "role", "is_active"):
        assert c in cols, f"عمود users.{c} اختفى — عمود صلاحية أو هويّة"
    # و`users` يبقى في قائمة الجداول المستأجَرة: استعلامٌ غير منطَّق فيه مسارُ
    # صلاحية، لا مجرّد تسريب صفّ.
    from tests.test_platform_isolation_ast_guard import TENANT_TABLES
    assert "users" in TENANT_TABLES

    # ودورةُ دخولٍ كاملة تنجح فعلاً — لا فحصَ مخطّطٍ يكفي عن هذا.
    cl = client()
    fac = make_factory("silver", "seats-guard@f.local")
    tok = login(cl, fac["email"], fac["password"])
    assert cl.get("/platform/me", headers=hdr(tok)).status_code == 200
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    assert cl.get("/platform/me", headers=hdr(admin)).status_code == 200


def test_a_legacy_sub_user_can_still_be_disabled_by_the_admin(monkeypatch):
    """ملاحظة مراجعة §58: الحذف أزال **كل** مسار لتعطيل مستخدمٍ قائم.

    حسابٌ أُنشئ له مستخدمٌ فرعيّ قبل هذه الموجة يظلّ قادراً على الدخول
    وإطلاق الدراسات إلى الأبد لولا هذه النقطة الأدمِنية. تعطيلٌ لا حذف، وجلسته
    تُنهى في المعاملة نفسها.
    """
    from silk_platform import db as pdb, passwords
    from silk_platform.db import now_iso
    info = seed(monkeypatch)
    fac = make_factory("silver", "legacy-owner@f.local")
    conn = pdb.connect()
    try:
        now = now_iso()
        cur = conn.execute(
            "INSERT INTO users (account_id, email, password_hash, role, "
            "first_name, last_name, language_preference, created_at, updated_at)"
            " VALUES (?,?,?, 'factory', 'L', 'Legacy', 'ar', ?, ?)",
            (fac["account_id"], "legacy-sub@f.local",
             passwords.hash_password("Factory1234"), now, now))
        legacy_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    cl = client()
    tok = login(cl, "legacy-sub@f.local", "Factory1234")
    assert cl.get("/platform/me", headers=hdr(tok)).status_code == 200

    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    r = cl.post(f"/platform/admin/users/{legacy_id}/deactivate", headers=hdr(admin))
    assert r.status_code == 200, r.text
    # جلستُه ماتت فوراً، ولا يستطيع الدخول ثانيةً.
    assert cl.get("/platform/me", headers=hdr(tok)).status_code == 401
    r2 = cl.post("/platform/auth/login",
                 json={"email": "legacy-sub@f.local", "password": "Factory1234"})
    assert r2.status_code == 401, r2.text
    # ولا تلمس النقطةُ حسابات سِلك.
    assert cl.post(f"/platform/admin/users/{info['analyst']['id']}/deactivate",
                   headers=hdr(admin)).status_code == 422


def test_the_unscoped_reader_has_one_caller_behind_a_role_check():
    """`get_unscoped` قارئٌ بلا نطاق — قفلٌ نصّي لأن حارس العزل لا يرى
    `repository.py` (جُمَله مبنيّة بعمود مالكٍ لا يظهر حرفياً)، فمدخلُ
    allowlist له كان زينةً لا إنفاذاً (ملاحظة مراجعة §58)."""
    api_src = (_PKG / "api.py").read_text(encoding="utf-8")
    assert api_src.count("get_unscoped(") == 1, (
        "للقارئ غير المنطَّق أكثر من مستدعٍ — كل مستدعٍ يحتاج فحص دورٍ وقيد تدقيق")
    branch = api_src.split("if ctx.is_silk_admin:")[1].split("# factory")[0]
    assert "get_unscoped(" in branch, "القارئ غير المنطَّق خارج فرع الأدمِن"
    assert 'action="admin_study_view"' in branch, "فتحُ الأدمِن بلا قيد تدقيق"
    assert 'resource_type == "study"' in branch, (
        "القارئ غير المنطَّق غير محصور بالدراسات — الصور والبريد خلف الجدار")
    for path in _PKG.glob("*.py"):
        if path.name in ("api.py", "repository.py"):
            continue
        assert "get_unscoped(" not in path.read_text(encoding="utf-8"), (
            f"{path.name}: يستدعي القارئ غير المنطَّق بلا فحص دور")
