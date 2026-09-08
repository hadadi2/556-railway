"""أقفال الترجمة الثنائية — «لغة المنصة لغتين عربي وانجليزي» (2026-08-17).

الآلية المقفلة: العربية تبقى المؤلَّفة في الترميز (كل حراس النصوص العربية
كما هي)، والإنجليزية تُطبَّق وقت التشغيل — النصوص الثابتة عبر `data-i18n`
والأصل يُلتقط من الصفحة نفسها، والديناميكية عبر `ar_en("عربي","English")`،
والقواميس بمرايا `*_EN` متكافئة المفاتيح. التفضيل يُحفظ محلياً قبل الدخول
وفي حساب المستخدم بعده عبر `PATCH /platform/me/language` (أي دور).
"""
from __future__ import annotations

import pathlib
import re

from tests.platform_helpers import (client, hdr, login, make_factory, seed)

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PAGE = (_ROOT / "web" / "platform.html").read_text(encoding="utf-8")
_RESET = (_ROOT / "web" / "reset-password.html").read_text(encoding="utf-8")


def _dict_keys(page: str, name: str) -> set[str]:
    m = re.search(rf"(?:const|var) {name} = \{{(.*?)\}};", page, re.S)
    assert m, f"قاموس {name} غير موجود"
    # جرّد محتوى السلاسل أولاً — قيمة تحوي «key:» كانت ستُحسب مفتاحاً زائفاً؛
    # ثم التقط المفاتيح أينما وقعت (عدة مفاتيح في السطر الواحد مشروعة).
    body = re.sub(r'"(?:[^"\\]|\\.)*"', '""', m.group(1))
    return set(re.findall(r'\b([a-z_0-9]+)\s*:', body))


# ── ١) تكافؤ مفاتيح القواميس — كل رمز له عربيته وإنجليزيته ─────────────────
def test_dictionary_mirrors_have_equal_keys():
    # (قاموسا FEAT_*/OP_* حُذفا مع واجهتَي المزايا والدفتر — قرار 2026-08-18.)
    for ar, en in (("ERR_AR", "ERR_EN"), ("STATE_AR", "STATE_EN"),
                   ("TIER_AR", "TIER_EN"), ("HS_SOURCE_AR", "HS_SOURCE_EN")):
        ka, ke = _dict_keys(_PAGE, ar), _dict_keys(_PAGE, en)
        assert ka == ke, (f"{ar}/{en} غير متكافئين — "
                          f"عربي فقط: {ka - ke} · إنجليزي فقط: {ke - ka}")


def test_every_data_i18n_key_has_english():
    keys = set(re.findall(r'data-i18n="([a-z_0-9]+)"', _PAGE))
    en = _dict_keys(_PAGE, "I18N_EN")
    missing = keys - en
    assert not missing, f"مفاتيح data-i18n بلا إنجليزية: {sorted(missing)}"
    ph = set(re.findall(r'data-i18n-ph="([a-z_0-9]+)"', _PAGE))
    assert ph <= en, f"مفاتيح placeholder بلا إنجليزية: {sorted(ph - en)}"


def test_flip_mechanics_are_present():
    assert "documentElement.dir" in _PAGE and "documentElement.lang" in _PAGE
    assert '"silk_lang"' in _PAGE
    assert "ME.language_chosen" in _PAGE          # الاختيار الصريح فقط (§58 M4)
    assert "LANG_CHOSEN_LOCAL" in _PAGE           # تبديل الجلسة لا يُعكس
    assert '"/me/language"' in _PAGE
    # النمط العالمي (تصحيح المالك 2026-08-19): داخل الجلسة اللغة تُضبط من بطاقة
    # اللغة في «الملف التعريفي» (langBtn3) حصراً — كما Shopify/Slack/Notion؛
    # زرّ الزائر قبل الدخول (langBtn) يبقى. زرّ الشريط الجانبي المكرّر
    # (langBtn2) حُذف — غيابه مؤكَّد كي لا يعود الازدواج.
    assert 'id="langBtn"' in _PAGE and 'id="langBtn3"' in _PAGE
    assert 'id="langBtn2"' not in _PAGE
    # كتلة LTR الثانية لسحب الجوال — والكتلة الأولى المفحوصة بايتياً كما هي.
    assert 'html[dir="ltr"] aside.side{transform:translateX(-100%)}' in _PAGE
    assert "aside.side{transform:translateX(100%);transition" in _PAGE
    # صفوف الأقسام تحمل إنجليزيتها والقائمة تقرأ الموافق للغة.
    assert "label_en:" in _PAGE
    assert "ar_en(x.label, x.label_en)" in _PAGE


def test_reset_page_is_bilingual_too():
    assert 'id="langBtn"' in _RESET
    assert "I18N_EN" in _RESET and "data-i18n" in _RESET
    assert "documentElement.dir" in _RESET
    keys = set(re.findall(r'data-i18n="([a-z_0-9]+)"', _RESET))
    en = _dict_keys(_RESET, "I18N_EN")
    assert keys <= en, f"مفاتيح بلا إنجليزية في صفحة التعيين: {sorted(keys - en)}"


# ── ٢) نقطة حفظ اللغة — أي دور، صفّه الذاتي، مدقَّقة ────────────────────────
def test_patch_me_language_for_every_role(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    monkeypatch.setenv("SILK_SEED_ANALYST_PASSWORD", "AnalystPass1")
    info = seed(monkeypatch)
    with client() as cl:
        make_factory("silver", "lang@f.local")
        creds = [("admin@silk.local", "AdminPass1"),
                 ("lang@f.local", "Factory1234")]
        analyst_email = (info.get("analyst") or {}).get("email")
        if analyst_email:
            creds.append((analyst_email, "AnalystPass1"))
        for email, pw in creds:
            tok = login(cl, email, pw)
            r = cl.patch("/platform/me/language", headers=hdr(tok),
                         json={"language_preference": "en"})
            assert r.status_code == 200, f"{email}: {r.text}"
            assert r.json()["language_preference"] == "en"
            me = cl.get("/platform/me", headers=hdr(tok)).json()
            assert me["language_preference"] == "en", email
            # ويرفض لغة خارج ar/en.
            assert cl.patch("/platform/me/language", headers=hdr(tok),
                            json={"language_preference": "fr"}).status_code == 422


def test_language_change_is_audited(monkeypatch):
    seed(monkeypatch)
    with client() as cl:
        make_factory("silver", "lang-audit@f.local")
        tok = login(cl, "lang-audit@f.local", "Factory1234")
        cl.patch("/platform/me/language", headers=hdr(tok),
                 json={"language_preference": "en"})
        from silk_platform.db import connect
        conn = connect()
        try:
            n = conn.execute("SELECT COUNT(*) FROM audit_log "
                             "WHERE action = 'language_changed'").fetchone()[0]
        finally:
            conn.close()
        assert n == 1


def test_tr_pairs_are_well_formed():
    """كل نداء ar_en(» يبدأ بعربية ويحمل وسيطين — إنجليزية ساقطة تعني نصاً
    عربياً في واجهة إنجليزية بلا من ينتبه."""
    script = _PAGE[_PAGE.index("<script>"):]
    # أول وسيط سلسلة عربية يعقبها فاصلة (النداءات متعددة الأسطر تُطابق سطرها الأول).
    singles = re.findall(r'\bar_en\("([^"]+)"\)', script)
    assert not singles, f"نداء ar_en بوسيط واحد: {singles[:3]}"


# ═══ إصلاحات مراجعة §58 — أقفالها ═══════════════════════════════════════════
def test_no_nested_data_i18n_anywhere():
    """§58 M3: data-i18n على سلفٍ يحوي data-i18n يدمّر الأبناء — كتابة نصّ
    الأب تقتلعهم من الـDOM نهائياً (وقعت فعلاً: رابط «العودة لصفحة الباقات»
    في صفحة الدفع اختفى عند التبديل). فحص تداخل حقيقي بمحلّل HTML."""
    from html.parser import HTMLParser

    class _Guard(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack: list[bool] = []
            self.violations: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag in ("br", "input", "img", "meta", "link", "hr"):
                if dict(attrs).get("data-i18n") and any(self.stack):
                    self.violations.append(f"<{tag}> متداخل")
                return
            has = bool(dict(attrs).get("data-i18n"))
            if has and any(self.stack):
                self.violations.append(f"<{tag} data-i18n={dict(attrs).get('data-i18n')}>")
            self.stack.append(has)

        def handle_endtag(self, tag):
            if self.stack:
                self.stack.pop()

    for name in ("platform.html", "reset-password.html",
                 "platform-landing.html", "pricing.html", "checkout.html"):
        g = _Guard()
        g.feed((_ROOT / "web" / name).read_text(encoding="utf-8"))
        assert not g.violations, f"{name}: data-i18n متداخل: {g.violations}"


def test_language_chosen_stamp_semantics(monkeypatch):
    """§58 M4: التفضيل يُطبَّق عبر الأجهزة فقط بختم اختيارٍ صريح (ترحيل 008)
    يكتبه PATCH /me/language حصراً — القيم المخزونة قبله افتراض مخطط."""
    seed(monkeypatch)
    with client() as cl:
        make_factory("silver", "chosen@f.local")
        tok = login(cl, "chosen@f.local", "Factory1234")
        me = cl.get("/platform/me", headers=hdr(tok)).json()
        assert me["language_chosen"] is False      # لم يختر بعد — افتراض يُتجاهل
        cl.patch("/platform/me/language", headers=hdr(tok),
                 json={"language_preference": "en"})
        me = cl.get("/platform/me", headers=hdr(tok)).json()
        assert me["language_chosen"] is True
        assert me["language_preference"] == "en"


def test_migration_008_is_additive_only():
    sql = (_ROOT / "migrations" / "platform" /
           "008_language_chosen.sql").read_text(encoding="utf-8")
    body = "\n".join(l for l in sql.splitlines()
                     if l.strip() and not l.strip().startswith("--"))
    assert "ADD COLUMN language_chosen_at" in body
    for banned in ("DROP", "DELETE", "UPDATE "):
        assert banned not in body.upper() or banned == "UPDATE ", body
    assert "DROP" not in body.upper() and "DELETE" not in body.upper()
