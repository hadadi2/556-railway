"""حُرّاس صفحة الهبوط الجديدة — `web/platform-landing.html` (2026-08-17).

قرار المالك: «صفحة الهبوط سيئة جدا…اضف الباقات من اقتراحك واسعار…انميشن
كرة ارضية متحركة…ازرق فاتح نفس المنصات العالمية». العائلات المقفلة:
الاكتفاء الذاتي (CSP)، رابط الخطوط (علّة حية: الصفحة الأولى لم تربط
fonts.css أصلاً)، الهيرو باحترام تفضيل تقليل الحركة، ولا سعر مثبّت
في الملف (المصدر الواحد `config/pricing.yaml` عبر النقطة العامة).

تحديث 2026-08-18: المالك استبدل الهيرو بتصميمه (حزمة silkhero) — كرة canvas
النقطية صارت مدار ١٢ وكيلاً حول كرة SVG ساكنة؛ حارس الكرة تطوّر معها
(`test_hero_orbit_is_present_and_respectful`) وبقيت بقية العائلات كما هي.
"""
from __future__ import annotations

import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_LANDING = (_ROOT / "web" / "platform-landing.html").read_text(encoding="utf-8")
_LANDING = _LANDING.replace('<script src="/marketing.js" defer></script>', "<script>" + (_ROOT / "web/marketing.js").read_text() + "</script>")
_CHECKOUT_PATH = _ROOT / "web" / "checkout.html"


def _pages():
    out = [(_LANDING, "platform-landing.html"), ((_ROOT / "web/pricing.html").read_text(), "pricing.html")]
    if _CHECKOUT_PATH.exists():
        out.append((_CHECKOUT_PATH.read_text(encoding="utf-8"), "checkout.html"))
    return out


# `ids` صريحة: بلاها يبني pytest معرّفَ الاختبار من **محتوى الصفحة كاملاً**
# (مئاتُ الكيلوبايتات) فيتجاوز حدَّ طول المسار على ويندوز ويسقط الاختبارُ
# في التهيئة قبل أن يقيس شيئاً. الاسمُ هو المعرّف الطبيعي أصلاً.
_page_id = lambda v: v if isinstance(v, str) and v.endswith(".html") else ""


@pytest.mark.parametrize("page,name", _pages(), ids=_page_id)
def test_page_is_fully_self_contained(page, name):
    """لا مرجع خارجياً ولا eval — CSP الخدمة تحجبهما حياً (اتفاق البيت)."""
    external = re.findall(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)', page)
    assert not external, f"{name}: مراجع خارجية ستُحجَب: {external}"
    for bad in ("eval(", "new Function(", 'setTimeout("', 'setInterval("'):
        assert bad not in page, f"{name}: {bad}"


def test_fonts_are_actually_linked():
    """العلّة الحية المرصودة: الصفحة الأولى لم تربط ملف الخطوط إطلاقاً —
    الرابط جذري (`/fonts/…`) لأن الصفحة تُخدم من مسارين (/platform و…html)."""
    assert 'href="/fonts/fonts.css"' in _LANDING


def test_landing_script_parses_with_node():
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node") or next(
        (p for p in ("/opt/node22/bin/node", "/usr/bin/node") if
         pathlib.Path(p).exists()), None)
    if not node:
        pytest.skip("node غير متوفّر")
    m = re.search(r"<script>(.*)</script>", _LANDING, re.S)
    assert m
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "landing.js"
        f.write_text(m.group(1), encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)],
                           capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:800]


def test_research_hero_uses_twelve_real_missions_and_respects_reduced_motion():
    """Owner replaced the dashboard image with the twelve-agent workflow."""
    import ast
    catalog = ast.parse((_ROOT / 'silk_missions.py').read_text())
    mission_keys = set()
    for node in ast.walk(catalog):
        if isinstance(node, ast.Dict):
            pairs = {k.value: v for k, v in zip(node.keys, node.values)
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if 'key' in pairs and 'mission' in pairs and isinstance(pairs['key'], ast.Constant):
                mission_keys.add(pairs['key'].value)
    rendered = re.findall(r'data-agent="([a-z_]+)"', _LANDING)
    assert len(rendered) == len(set(rendered)) == 12
    assert set(rendered) == mission_keys
    assert 'id="researchPause"' in _LANDING
    assert 'src="/silk-approved-preview.png"' not in _LANDING
    motion_css = (_ROOT / 'web/research-motion.css').read_text()
    assert 'prefers-reduced-motion:reduce' in motion_css
    assert 'animation-play-state:paused' in motion_css
    assert "border-radius:0 0 50% 50%" in _LANDING
    assert 'src="/silk-logo.png"' in _LANDING


def test_landing_is_served_gzipped():
    """كرة الهيرو المضمّنة ضاعفت الصفحة (~140KB) — الضغط شرط الشحن، وإلا
    عاد الهبوط بطيئاً على شبكات الجوال أول ما يفتحه عميل."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import api
    client = TestClient(api.create_app())
    r = client.get("/platform", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_no_hardcoded_prices_and_declared_fetch_failure():
    """الأسعار من `GET /platform/pricing` وقت التشغيل حصراً — رقم مثبّت هنا
    كان سينحرف صامتاً أول ما يعدّل المالك pricing.yaml. كرة الهيرو تُستبعد
    من الفحص: مساراتها أرقام هندسية عمياء قد تصادف أي رقم."""
    assert '"/platform/pricing"' in _LANDING
    page = re.sub(r'<svg id="heroGlobe".*?</svg>', "", _LANDING, flags=re.S)
    for price in ("749", "1899", "1,899", "4999", "4,999",      # القديمة
                  "699", "1799", "1,799", "4499", "4,499",      # الشهرية
                  "6990", "6,990", "17990", "17,990",
                  "44990", "44,990"):                           # السنوية
        assert price not in page, f"سعر مثبّت في الصفحة: {price}"
    assert "تعذّر تحميل الأسعار" in _LANDING          # فشل الجلب معلَن، لا صمت
    assert "/checkout.html?plan=" in _LANDING


def test_portal_contract_and_bilingual_toggle():
    assert 'dir="rtl"' in _LANDING and 'lang="ar"' in _LANDING
    assert "تسجيل الدخول" in _LANDING
    assert 'href="/platform.html"' in _LANDING
    assert 'id="langBtn"' in _LANDING
    assert "silk_lang" in _LANDING
    # الإنجليزية تُطبَّق وقت التشغيل والعربية تبقى المؤلَّفة في الترميز.
    assert "data-i18n" in _LANDING and "L_EN" in _LANDING


def test_customer_copy_keeps_source_and_illustration_context():
    """شرح الوكلاء مباشر بلا تذييل مكرر وفق تصحيح المالك."""
    assert "حجم الطلب" in _LANDING
    assert "كل وكيل يبحث في تخصصه" in _LANDING
    assert "تصوّر توضيحي" not in _LANDING
    for jargon in ("لا اختلاق", "غير مرصود", "تحت كل رقم"):
        assert jargon not in _LANDING


# ═══ حرّاس إعادة كتابة المحتوى (2026-08-20) ═══════════════════════════════
# الحادثة: صفحة الهبوط التي تبيع «لا اختلاق» كانت تحمل رقمين يكذّبهما الكود —
# «140+ سوقاً» بينما `COUNTRIES` ٣٨ سوقاً والسقف الأقصى ١٠٠ بصمّام مطفأ
# افتراضياً، و«9 دقائق» بلا أي سند بينما الزمن المعلن الوحيد ٩٠٠ث.
# القاعدة المستخلَصة: كل رقم على سطح البيع يُشتقّ من ثابت في الكود، والحارس
# يقرأ الثابت نفسه — لا نسخة يدوية تنحرف صامتاً عند أول تعديل للمحرّك.

def _stat_value(key: str) -> str:
    """قيمة بطاقة رقم في الهيرو كما تظهر للزائر."""
    m = re.search(rf'data-i18n="{key}">([^<]+)<', _LANDING)
    assert m, f"بطاقة الرقم {key} مفقودة من الهيرو"
    return m.group(1).strip()


def _landing_en() -> dict:
    """مفاتيح `L_EN` — تُجرَّد السلاسل أولاً كي لا تُحسب «key:» داخل نصّ."""
    m = re.search(r"var L_EN = \{(.*?)\n\};", _LANDING, re.S)
    assert m, "قاموس L_EN غير موجود"
    body = re.sub(r'"(?:[^"\\]|\\.)*"', '""', m.group(1))
    body = re.sub(r"'(?:[^'\\]|\\.)*'", "''", body)
    # المفاتيح تُلتقط أينما وقعت — عدّة مفاتيح في السطر الواحد مشروعة
    # (`ag1: "…", ag2: "…"`)، ومطابقة بداية السطر وحدها كانت عمياء عنها.
    return set(re.findall(r'\b([a-zA-Z_0-9]+)\s*:', body))


def test_every_landing_i18n_key_has_english():
    """الثغرة المرصودة: `tests/test_platform_i18n.py` يفحص التكافؤ في
    `platform.html` و`reset-password.html` فقط — وصفحة الهبوط بمفاتيحها
    الـ١٤٩ كانت بلا فحص. مفتاح بلا إنجليزية لا يرمي خطأً: `applyLang`
    يتخطّاه صامتاً (`if (v == null) return;`) فتبقى فقرة عربية وحيدة وسط
    واجهة إنجليزية بلا من ينتبه."""
    keys = set(re.findall(r'data-i18n="([a-zA-Z_0-9]+)"', _LANDING))
    missing = keys - _landing_en()
    assert not missing, f"مفاتيح هبوط بلا إنجليزية: {sorted(missing)}"


def test_no_fabricated_market_count_and_no_multi_market_promise():
    """«140+ سوقاً» كان اختلاقاً — ثم تبيّن أن العيب أعمق من الرقم.

    الوضع الافتراضي لدراسة المنصّة `deep` (`engine_bridge.study_mode`)،
    والمسار العميق **يرفض الإطلاق بلا سوق مستهدفة** (`api.py` بوابة
    `study_no_market_deep`) و`_target_countries` يحصر المحرّك في تلك السوق
    وحدها. فبيعُ «ترتيب الأسواق المرشّحة» كمخرَج الدراسة وصفٌ للمسار السريع
    لا للمنتج الافتراضي — ولذلك سقط عدّاد الأسواق من الهيرو أصلاً.
    """
    page = re.sub(r'<svg id="heroGlobe".*?</svg>', "", _LANDING, flags=re.S)
    visible = re.sub(r"<style>.*?</style>", "", page, flags=re.S)
    assert "140" not in visible, "ادعاء «140 سوقاً» عاد"
    # أي عدد أسواق يُعرض لاحقاً يجب أن يُشتقّ من قائمة المرتِّب نفسها.
    from silk_market_ranker import COUNTRIES
    for bogus in re.findall(r"(\d+)\s*(?:\+\s*)?سوقاً", page):
        assert int(bogus) == len(COUNTRIES), (
            f"عدد أسواق معروض ({bogus}) لا يطابق len(COUNTRIES)="
            f"{len(COUNTRIES)}")


def test_owner_removed_numeric_marketing_promises():
    """المالك حذف العدّادات ووعود الدقائق صراحةً من التصميم المعتمد."""
    assert 'class="proof-stats"' not in _LANDING
    for obsolete in ('data-i18n="stv2"', 'data-i18n="stv3"', '15 دقيقة', '15 minutes'):
        assert obsolete not in _LANDING


def test_approved_copy_and_separate_pricing_link():
    assert 'href="/pricing.html"' in _LANDING
    assert 'تحت كل رقم في التقرير سطر يقول من أين جاء ومتى' not in _LANDING
    assert 'الإمارات' not in _LANDING
    assert 'قوة المنافسة' in _LANDING


def test_no_internal_or_paid_vendor_name_leaks_to_the_sales_page():
    """منقّي سطح العميل (`silk_reports.py`) يحظر أسماء المزوّدين الداخلية عن
    التقرير — وسطح البيع أولى: مصدر لا يظهر في التقرير لا يُعلَن هنا."""
    for vendor in ("Volza", "Explee", "Serper", "SerpApi", "LocalPrice",
                   "pytrends", "GDELT", "فولزا", "إكسبلي"):
        assert vendor not in _LANDING, f"اسم مزوّد داخلي على صفحة البيع: {vendor}"


def test_landing_focuses_on_three_customer_steps():
    assert _LANDING.count('class="card" data-reveal') == 3
    for label in ('فرص البيع', 'المنافسة والأسعار', 'متطلبات الدخول'):
        assert label in _LANDING


def test_no_download_format_is_promised_without_a_button():
    """الواجهة تعرض زرّ PDF وحده (`pdfBtn` في web/platform.html) — ونقطة
    Word تبقى خادمية بلا زر بقرار موثَّق. وعدُ تنزيلٍ لا يجد زرّاً على
    الشاشة وعدٌ بلا إنفاذ، وهو ما تمنعه هذه الصفحة عن نفسها."""
    page = (_ROOT / "web" / "platform.html").read_text(encoding="utf-8")
    if "docxBtn(" not in page:
        assert "Word" not in _LANDING, (
            "الهبوط يعد بتنزيل Word بينما لا زرّ Word في المنصّة")
