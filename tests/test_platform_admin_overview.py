"""أقفال «نظرة عامة» الأدمِن — KPI حقيقية + سلسلة شهرية مرصودة + رسم يدوي.

قرار المالك (2026-08-17): «مازالت الخدمات في داشبورد الادمن سيئة ولا يستفاد
منها». اللوحة الجديدة تُغذّى من `GET /platform/admin/metrics` الموسَّعة
(مفاتيح إضافية فقط) — الشهور من سجلّ التدقيق (append-only) لا من أختام
الدراسة التي تُمسَح عند الفشل.
"""
from __future__ import annotations

import datetime
import pathlib

from tests.platform_helpers import (client, hdr, login, make_factory,
                                    make_product_study, seed)

_PAGE = pathlib.Path(__file__).resolve().parent.parent / "web" / "platform.html"


def _month() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")


def test_admin_metrics_new_keys_reflect_seeded_activity(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        acc = make_factory("gold", "overview@f.local")
        import silk_platform.engine_bridge as eb
        monkeypatch.setattr(
            eb, "_run_engine",
            lambda product, hs_code, market_pref, *_a, **_k: {
                "classified": True, "analysis_id": 555,
                "markets": [{"country": "الإمارات", "confidence": 0.5,
                             "components": {}}]})
        tok = login(cl, "overview@f.local", "Factory1234")
        sid = make_product_study(acc["account_id"], acc["user_id"], "تمور")
        assert cl.post(f"/platform/studies/{sid}/launch",
                       headers=hdr(tok)).status_code == 200
        assert eb.wait_idle()

        atok = login(cl, "admin@silk.local", "AdminPass1")
        m = cl.get("/platform/admin/metrics", headers=hdr(atok)).json()
        # المفاتيح القديمة كما هي (إضافي فقط).
        for k in ("accounts_by_tier", "active_studies", "vault_balance_cents",
                  "research_costs"):
            assert k in m
        assert m["factory_accounts"] >= 1
        assert m["total_users"] >= 2            # أدمِن البذر + مصنعنا على الأقل
        assert m["launched_this_month"] >= 1
        assert m["completed_this_month"] >= 1
        assert m["checkout_requests_this_month"] == 0

        series = m["studies_by_month"]
        assert len(series) == 12
        assert series[-1]["month"] == _month()
        assert series[-1]["launched"] >= 1
        assert series[-1]["completed"] >= 1
        # شهرٌ بلا نشاط = صفر مرصود (عدُّ السجلّ أعاد لا-شيء) — حاضر لا محذوف.
        assert series[0]["launched"] == 0 and series[0]["completed"] == 0
        months = [r["month"] for r in series]
        assert months == sorted(months), "السلسلة غير مرتّبة زمنياً"


def test_admin_metrics_still_admin_only(monkeypatch):
    seed(monkeypatch)
    with client() as cl:
        make_factory("silver", "ov-role@f.local")
        tok = login(cl, "ov-role@f.local", "Factory1234")
        assert cl.get("/platform/admin/metrics",
                      headers=hdr(tok)).status_code == 403


def test_overview_page_wiring_reads_the_real_metric_keys():
    """الصفحة تقرأ مفاتيح الردّ الحقيقية وترسم SVG يدوياً (لا مكتبة خارجية)."""
    html = _PAGE.read_text(encoding="utf-8")
    assert 'id="adminHomePanel"' in html
    assert '{key: "overview"' in html
    # يظهر أولاً بين أقسام الأدمِن — الأدمِن يهبط عليه.
    assert html.index('{key: "overview"') < html.index('{key: "accounts"')
    # `vault_balance_cents` خرجت من قائمة القراءة مع بطاقة الخزنة (قرار
    # المالك 2026-08-20: التمويل يُحذف من الواجهة) — النقطة ما زالت تُرجعها.
    for key in ("studies_by_month", "launched_this_month",
                "completed_this_month", "factory_accounts", "total_users",
                "checkout_requests_this_month", "accounts_by_tier"):
        assert key in html, f"الصفحة لا تقرأ {key}"
    # الرسم اليدوي CSP-safe + حالة فراغ معلنة.
    assert "createElementNS" in html
    # الحالة الفارغة تُعلَن بالحالة الموحّدة (أيقونة + ماذا حدث + ماذا تفعل)
    # بدل سطرٍ عائم — قرار 2026-08-20. الحارس يقفل **المعنى** لا نصّاً بعينه:
    # `renderStudiesChart` تنادي `emptyState` قبل أن ترسم أيّ محور.
    chart_body = html.split("function renderStudiesChart(")[1].split("\nfunction ")[0]
    assert "emptyState(" in chart_body, (
        "مخطّط الأدمِن بلا حالة فراغ معلنة — يرسم محاوراً فارغة")
    assert "لا بيانات كافية" in chart_body, (
        "الحالة الفارغة لا تقول إن البيانات غير كافية")
    # ونفس حدود مخطّط المصنع: قياسٌ من الحاوية وارتفاعٌ صريح ونسبة أبعاد،
    # وإلا عاد الرسم يتمدّد بلا حدّ (فحص شامل 2026-08-20).
    assert "host.clientWidth" in chart_body, (
        "مخطّط الأدمِن لا يقيس حاويته — يعود المقياس بلا حدّ")
    assert "preserveAspectRatio" in chart_body and 'height: String(H)' in chart_body, (
        "مخطّط الأدمِن بلا ارتفاع صريح أو نسبة أبعاد")
    # زر فحص المصادر يستدعي النقطة الحقيقية ويعرض حالات المحرّك كما هي.
    assert '"/admin/diagnostics"' in html
    for state in ("reachable_empty", "no_key", "unreachable"):
        assert state in html, f"حالة {state} بلا عرض"


def test_the_admin_header_bar_carries_no_per_account_action():
    """أفعال الحساب في مكانٍ واحد: صفُّه في الجدول — لا في رأس نفس الشاشة.

    السابقة (رصد المالك البصري 2026-08-20): «تمويل/الطبقة/حصّة المستخدم» كانت
    في `#adminBar` وفي كلّ صفٍّ من جدول الحسابات معاً، والشريط مقيَّدٌ أصلاً
    بقسم الحسابات — أي أنه لا يظهر إلا حيث الجدول. نفس النافذة تُفتَح من
    الاثنين، والفرق أنّ زرّ الصفّ يأتي بالحساب مُختاراً سلفاً؛ فزرّ الرأس
    مجموعةٌ فرعيةٌ منه وظيفياً. الحارس يقفل عدم عودته.
    """
    html = _PAGE.read_text(encoding="utf-8")
    for dead in ('id="fundBtn"', 'id="tierBtn"', 'id="quotaBtn"'):
        assert dead not in html, f"{dead}: زرّ حسابٍ عاد إلى رأس شاشة الجدول"
    header = html.split('<header class="top">')[1].split("</header>")[0]
    assert "data-act=" not in header and "fundDialog" not in header, (
        "فعل حسابٍ عاد إلى الرأس")
    # ...وأزرار الصفوف هي الموضع الوحيد، بمقبضٍ ثابت يقصده اختبار المتصفّح.
    accounts = html.split('const body = $("accountsBody");')[1].split("\n}")[0]
    for act in ("tier", "quota"):
        assert f'"{act}")' in accounts, f"زرّ صفّ {act} بلا مقبض data-act"
    assert "if (act) b.dataset.act = act;" in html, "mkBtn لا تضبط المقبض"
    # وأفعال الحساب تعيش في قسمها: «الباقات» يحمل نسختَي «كل الحسابات»،
    # و«نظرة عامة» يبقى فيها «فحص المصادر» وحده (لم تعد سطحَ أفعالٍ ثالثاً).
    for bid in ("tierAcctBtn", "quotaAcctBtn", "diagBtn"):
        assert f'id="{bid}"' in html, f"{bid} غائب"
    for dead in ("homeFundBtn", "homeTierBtn", "homeQuotaBtn"):
        assert f'id="{dead}"' not in html, (
            f"{dead}: فعل حسابٍ عاد إلى «نظرة عامة» — موضعه «الباقات»")


def test_funding_has_no_surface_left_in_the_page():
    """«حساب التمويل ما له أي فائدة» (قرار المالك 2026-08-20).

    بعد تحوّل «الباقة فقط» لا يُخصَم من المحفظة شيء عند إطلاق دراسة، فزرّ
    التمويل كان يكتب قيداً في الدفتر لا قارئ له، وبطاقة «خزنة المنصّة» رقماً
    لا يقود إلى قرار. **الخادم لا يُمَسّ**: `POST /admin/fund` والدفتر
    والخزنة و`vault_balance_cents` باقية — واجهةٌ تُحذَف لا بيانات.
    """
    html = _PAGE.read_text(encoding="utf-8")
    for dead in ('id="homeFundBtn"', 'function fundDialog(', '"/admin/fund"',
                 'data-act="fund"', '"fund")'):
        assert dead not in html, f"{dead}: سطح تمويلٍ عاد إلى الصفحة"
    # يُفحَص **نداء الرسم** لا العبارة: ذكرُها في تعليقٍ يشرح سبب حذفها
    # إنذارٌ كاذب على شيفرةٍ سليمة (نفس درس `_without_comments`).
    assert '_kpi(ar_en("خزنة المنصّة"' not in html, "بطاقة خزنة المنصّة عادت"
    assert "vault_balance_cents" not in html, "الصفحة عادت تقرأ رصيد الخزنة"
    # ...والنقطة نفسها ما زالت في الخادم (لا حذف بيانات).
    api = (pathlib.Path(__file__).resolve().parent.parent /
           "silk_platform" / "api.py").read_text(encoding="utf-8")
    assert '/admin/fund"' in api, "نقطة التمويل حُذفت من الخادم — لم يُطلَب ذلك"


def test_the_plans_section_is_the_one_place_a_plan_is_defined():
    """قسم «الباقات» يجمع السعر والحصّة والمشتركين — ثلاثة مواضع صارت واحداً.

    وكل رقمٍ فيه يصرّح بمصدره: `overridden` يفرّق قيمة القاعدة عن قيمة الملف،
    فلا تُعرَض قيمةٌ معدَّلة كأنها التسعيرة المُقرّة.
    """
    html = _PAGE.read_text(encoding="utf-8")
    assert 'id="tiersPanel"' in html and '{key: "tiers"' in html
    assert '"/admin/tiers/"' in html, "لا سبيل لتعديل باقة من الصفحة"
    body = html.split("function renderTiers()")[1].split("\nfunction ")[0]
    assert "t.overridden" in body, "الجدول لا يصرّح بمصدر الرقم"
    assert "accounts_by_tier" in body, "عمود المشتركين لا يقرأ المصدر الحقيقي"
    # غياب المقاييس ≠ صفر مشتركين — الفرق معلَن لا مطموس.
    assert 'byTier ? String(Number(byTier[t.key] || 0)) : "—"' in body, (
        "غياب المقاييس يُعرَض صفراً — اختلاق")
    # الأساسية محكومة بسقف مدى الحياة، فلا رقم شهريّ يُعرَض لها.
    assert "سقف مدى الحياة" in body, (
        "الأساسية تعرض حدّاً شهرياً لا يقرؤه أحد")


def test_the_plan_mix_bar_reads_the_metrics_and_declares_its_gaps():
    """توزيع المشتركين شريطٌ واحد — لا سطرٌ مدفون ولا أربع بطاقات فوق سبع."""
    html = _PAGE.read_text(encoding="utf-8")
    assert 'id="tierBar"' in html
    body = html.split("function renderTierBar(")[1].split("\nfunction ")[0]
    assert "emptyState(" in body, "الشريط بلا حالة فراغ معلنة"
    assert "if (!byTier)" in body, "فشل جلب المقاييس يُعرَض صفراً"
    assert 'role", "img"' in body and "aria-label" in body, (
        "شريطٌ بلا بديلٍ نصّي — يُقرأ باللون وحده")
    # الرقم بجانب كل اسم: لا ترميزَ باللون وحده (وصول).
    assert 'r.n + " · "' in body
    # ولا نسخة ثانية من نفس الحقيقة داخل بطاقة الـKPI.
    kpis = html.split("function renderKpis(")[1].split("\nfunction ")[0]
    assert "tierFoot" not in kpis, "توزيع الباقات عاد سطراً مدفوناً في البطاقة"


def test_the_admin_header_bar_is_gated_by_role_alone():
    """ما بقي في الشريط فعلان عامّان («إعادة تعيين كلمة مستخدم» و«تحديث»)،

    فتقييده بقسم الحسابات كان يحرم الأدمِن من «تحديث» على «كل الدراسات»
    و«تكاليف البحث» و«نظرة عامة»، ويترك الرأس هناك صفّاً شبه فارغ.
    """
    html = _PAGE.read_text(encoding="utf-8")
    # كاتبان: `showSection` ومسارُ فشل التحديث (يعيد شريط الدور كي لا يصير
    # «اضغط تحديث» طريقاً مسدوداً). يجب أن يتّفقا: الدور وحده، بلا قسم.
    lines = [ln.strip() for ln in html.splitlines()
             if '$("adminBar").classList.toggle' in ln]
    assert lines, "لا أحد يبدّل شريط الأدمِن"
    for ln in lines:
        assert 'silk_admin' in ln, f"تبديلٌ بلا تفريق بالدور: {ln}"
        assert "target.key" not in ln, (
            f"الشريط ما زال مقيَّداً بقسم وقد زالت أفعال الحساب منه: {ln}")
    bar = html.split('id="adminBar"')[1].split("</div>")[0]
    assert "refreshBtn2" in bar, "«تحديث» غادر شريط الأدمِن"
    # «إعادة تعيين كلمة مستخدم» انتقلت إلى «الملف التعريفي» (قرار المالك
    # 2026-08-20): فعلُ هوية مكانه صفحة الهوية لا رأسُ كل شاشة.
    assert "resetUserBtn" not in html, "زرّ إعادة التعيين عاد إلى الرأس"
    assert 'id="pfResetCard"' in html and 'id="pfResetBtn"' in html, (
        "بطاقة إعادة التعيين غائبة عن «الملف التعريفي»")
    assert '$("pfResetBtn").onclick = resetUserDialog;' in html, (
        "البطاقة بلا فعل — زرٌّ لا يكتب شيئاً")
    # وهي أدمِن حصراً بنفس بوّابة الخادم، لا إخفاءً بصرياً لزرٍّ يُردّ 403.
    assert '$("pfResetCard").classList.toggle("hide", ME.role !== "silk_admin")' \
        in html, "بطاقة إعادة التعيين بلا تصفية بالدور"
