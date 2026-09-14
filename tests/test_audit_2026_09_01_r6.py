"""أقفال R6 — الواجهة (التدقيق الجنائي 2026-09-01، المرحلة ٦).

لماذا هذا الملف: صفحاتُ HTML بلا `Cache-Control` فتعلق نسخةٌ قديمة بعد النشر
(FE-16)؛ نحو أربعين رفضاً في واجهة المنصّة بنصٍّ إنجليزيّ خام (`detail="…"`) يراه
المصنعُ كما هو (FE-6)؛ الإشعاراتُ لا تُستطلَع إلا مع دراسةٍ جارية (FE-2)؛ حقلُ
الشحن غائبٌ من نافذة المنتج ومصدرُ رمز HS غيرُ مرئيّ (FE-7)؛ حقولُ دراسةٍ ميتة
تُقبَل وتُخزَّن (FE-8)؛ جدولُ الأدمِن يجلب كلَّ الدراسات بلا حدّ (FE-9)؛ وسلسلةُ
تفاصيل صغيرة (FE-4/10/14/17/18/19/20/22/23/25) ونصوصٌ عربية صلبة خارج `ar_en`.

هرمتي: قواعد مؤقّتة، لا شبكة. Hermetic only.
"""
from __future__ import annotations

import ast
import os
import pathlib
import re
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.platform_helpers import (client, hdr, login, make_factory,  # noqa: E402
                                    make_product_study, seed)

pytest.importorskip("fastapi")

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


_PAGE = _read("web/platform.html")


def _fn_body(src: str, marker: str) -> str:
    """جسمُ دالّة JavaScript بمطابقة الأقواس من أوّل `{` بعد العلامة."""
    i = src.index(marker)
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        c = src[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
    raise AssertionError(f"unbalanced body after {marker!r}")


def _dict_keys(name: str) -> set:
    m = re.search(r"const " + name + r" = \{(.*?)\n\};", _PAGE, re.S)
    assert m, f"{name} missing"
    body = re.sub(r'"(?:[^"\\]|\\.)*"', '""', m.group(1))
    return set(re.findall(r"\b([a-z_0-9]+)\s*:", body))


def _root_client():
    from fastapi.testclient import TestClient
    import api as root_api
    return TestClient(root_api.create_app())


def _pconn():
    from silk_platform import db as pdb
    return pdb.connect()


# ══════════════ FE-16 — HTML لا يُخزَّن: Cache-Control على صفحات الواجهة ═══════════
def test_html_pages_carry_cache_control_no_cache_and_health_does_not():
    with patch.dict(os.environ, {"SILK_DB": os.path.join(tempfile.mkdtemp(), "silk.db")}):
        os.environ.pop("SILK_API_KEY", None)
        cl = _root_client()
        for path in ("/platform.html", "/", "/index.html"):
            r = cl.get(path)
            assert r.status_code == 200, (path, r.status_code)
            assert "text/html" in r.headers.get("content-type", ""), path
            assert r.headers.get("Cache-Control") == "no-cache", (path, dict(r.headers))
        h = cl.get("/health")
        assert h.status_code == 200
        assert "Cache-Control" not in h.headers


# ══════════════ FE-6 — لا رفضَ بنصٍّ خام: كلُّ detail كائنٌ {error, message} ══════════
_DETAIL_EXEMPT = {"_as_int", "_require_fields"}      # مدقّقاتُ الحقول العامّة (قرار الخطّة)


def test_platform_api_raises_no_plain_string_details_outside_the_field_validators():
    tree = ast.parse(_read("silk_platform/api.py"))
    bad: list = []

    def visit(node, fn):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "HTTPException":
                for kw in node.keywords:
                    raw = isinstance(kw.value, (ast.Constant, ast.JoinedStr)) or (
                        isinstance(kw.value, ast.Call)
                        and getattr(kw.value.func, "id", None) == "str")   # مراجعة R6: str(exc)
                    if kw.arg == "detail" and raw and fn not in _DETAIL_EXEMPT:
                        bad.append((node.lineno, fn))
        for child in ast.iter_child_nodes(node):
            visit(child, fn)
    visit(tree, "<module>")
    assert not bad, f"plain-string HTTPException details remain: {bad}"


def test_every_error_code_has_arabic_and_english_messages():
    src = ""
    for p in sorted((_ROOT / "silk_platform").glob("*.py")):
        src += p.read_text(encoding="utf-8")
    codes = set(re.findall(r'"error"\s*:\s*"([a-z_]+)"', src))
    codes |= set(re.findall(r'_err\(\s*\d+,\s*"([a-z_]+)"', src))     # رموزُ `_err(...)` أيضاً
    ar, en = _dict_keys("ERR_AR"), _dict_keys("ERR_EN")
    assert not (codes - ar), sorted(codes - ar)
    assert not (codes - en), sorted(codes - en)
    for code in ("auth_required", "forbidden_role", "not_found", "invalid_credentials",
                 "login_throttled", "bad_hs_code", "bad_market_code", "study_not_draft",
                 "image_not_owned", "product_not_owned", "password_policy", "upload_too_large"):
        assert code in ar and code in en, code


def test_plain_detail_rejections_reach_the_client_as_error_objects(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "fe6@f.local")
    cl = client()
    r = cl.get("/platform/me")                                   # بلا جلسة
    assert r.status_code == 401 and r.json()["detail"]["error"] == "auth_required", r.text
    r = cl.post("/platform/auth/login", json={"email": f["email"], "password": "wrong-pass-1"})
    assert r.status_code == 401 and r.json()["detail"]["error"] == "invalid_credentials", r.text
    tok = login(cl, f["email"], f["password"])
    r = cl.post("/platform/products", json={"name": "x", "hs_code": "12"}, headers=hdr(tok))
    assert r.status_code == 422 and r.json()["detail"]["error"] == "bad_hs_code", r.text
    r = cl.get("/platform/studies/999999", headers=hdr(tok))
    assert r.status_code == 404 and r.json()["detail"]["error"] == "not_found", r.text
    for code in ("auth_required", "invalid_credentials", "bad_hs_code", "not_found"):
        assert code in _dict_keys("ERR_AR") and code in _dict_keys("ERR_EN"), code


# ══════════════ FE-2 — الإشعاراتُ تُستطلَع كلَّ دقيقة وعند عودة التبويب ══════════════
def test_notifications_poll_every_minute_and_refresh_on_tab_return():
    assert re.search(r"let _notifPoll\b", _PAGE), "لا مؤقّتَ إشعارات"
    assert re.search(r"_notifPoll\s*=\s*setInterval\([\s\S]{0,600}?60000", _PAGE), \
        "استطلاعُ الإشعارات ليس كلَّ ٦٠ ثانية"
    assert "clearInterval(_notifPoll)" in _fn_body(_PAGE, "async function doLogout()")
    vis = _PAGE[_PAGE.index('document.addEventListener("visibilitychange"'):]
    vis = vis[:vis.index("});") + 3]
    assert "loadNotifications" in vis, "عودةُ التبويب لا تحدّث الإشعارات"


# ══════════════ FE-7 — الشحنُ في نافذة المنتج، ومصدرُ الرمز مرئيّ ═══════════════════
def test_product_dialog_has_shipping_and_the_list_shows_the_hs_source(monkeypatch):
    assert 'name="pship"' in _PAGE
    assert "shipping_per_unit" in _fn_body(_PAGE, "function productDialog(")
    assert "HS_SOURCE_AR" in _PAGE and "HS_SOURCE_EN" in _PAGE
    assert 'data-i18n="th_hs_source"' in _PAGE
    assert "th_hs_source" in _dict_keys("I18N_EN")
    assert "hs_source" in _fn_body(_PAGE, "async function loadProducts()")
    seed(monkeypatch)
    f = make_factory("gold", "ship@f.local")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    r = cl.post("/platform/products", json={"name": "تمر", "shipping_per_unit": 1.5},
                headers=hdr(tok))
    assert r.status_code in (200, 201), r.text
    r2 = cl.post("/platform/products", json={"name": "عسل", "hs_code": "040900"},
                 headers=hdr(tok))
    assert r2.status_code in (200, 201), r2.text
    rows = {p["name"]: p for p in cl.get("/platform/products", headers=hdr(tok)).json()["products"]}
    assert rows["تمر"]["shipping_per_unit"] == 1.5
    assert rows["تمر"]["hs_source"] == "unknown" and rows["عسل"]["hs_source"] == "manual"


# ══════════════ FE-8 — حقولُ الدراسة الميتة لا تُقبَل ═════════════════════════════
def test_dead_study_fields_are_ignored_on_create_and_patch(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "dead@f.local")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    r = cl.post("/platform/studies", json={"product": "تمور سكري", "title_en": "T",
                                           "description_en": "D", "target_count": 7},
                headers=hdr(tok))
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]
    conn = _pconn()
    try:
        row = conn.execute("SELECT title_en, description_en, target_count FROM studies "
                           "WHERE id = ?", (sid,)).fetchone()
        assert row["title_en"] is None and row["description_en"] is None
        assert int(row["target_count"] or 0) == 0
    finally:
        conn.close()
    r = cl.patch(f"/platform/studies/{sid}", json={"title_en": "X", "description_en": "Y",
                                                   "target_count": 9}, headers=hdr(tok))
    assert r.status_code == 200, r.text
    conn = _pconn()
    try:
        row = conn.execute("SELECT title_en, description_en, target_count FROM studies "
                           "WHERE id = ?", (sid,)).fetchone()
        assert row["title_en"] is None and row["description_en"] is None
        assert int(row["target_count"] or 0) == 0
    finally:
        conn.close()


# ══════════════ FE-9 — جدولُ الأدمِن بصفحةٍ محدودة ومُعلَنة ══════════════════════════
def test_admin_studies_page_is_100_by_default_500_at_most_and_the_page_says_so(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("gold", "many@f.local")
    for i in range(150):
        make_product_study(f["account_id"], f["user_id"], product=f"منتج {i}")
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    assert len(cl.get("/platform/admin/studies", headers=hdr(tok)).json()["studies"]) == 100
    assert len(cl.get("/platform/admin/studies?limit=500", headers=hdr(tok)).json()["studies"]) == 150
    assert cl.get("/platform/admin/studies?limit=900", headers=hdr(tok)).status_code == 422
    assert "ADMIN_LIMIT" in _PAGE and "adminStudiesNote" in _PAGE
    assert re.search(r'"/admin/studies\?limit="\s*\+\s*', _PAGE), "الصفحةُ لا تمرّر الحدّ"
    assert 'id="adminStudiesNote"' in _PAGE


# ══════════════ FE-17/18/19/20/23/14/10/22 — تفاصيلُ الصفحة ══════════════════════
def test_warn_message_style_exists_and_the_empty_state_belongs_to_the_renderer():
    assert ".msg.warn{" in _PAGE, "لا صنفَ .msg.warn"
    tag = re.search(r'<div id="studiesEmpty"[^>]*>', _PAGE).group(0)
    assert "data-i18n" not in tag, "المُصيِّر يملك نصَّ الفراغ — data-i18n يعيد كتابته"


def test_notif_menu_marks_read_only_after_the_server_confirms():
    body = _fn_body(_PAGE, "async function toggleNotifMenu()")
    assert "ids" in body and '"/notifications/read"' in body
    assert "catch" in body and "tell(" in body, "فشلُ التعليم صامت"
    # P3 (BIZ-11): العدّادُ لم يعد يُصفَّر عمياً — يُطرَح منه ما أكّد الخادمُ تعليمَه.
    assert body.index('"/notifications/read"') < body.index("NOTIF.unread =")


def test_loadall_guards_overlap_and_study_dialogs_reload_the_table_only():
    body = _fn_body(_PAGE, "async function loadAll()")
    assert "_loading" in body, "لا حارسَ تداخل في loadAll"
    dlg = _fn_body(_PAGE, "function dialog(title, bodyHtml, onSubmit, submitLabel, reload)")
    assert 'reload === "studies"' in dlg and "loadStudies()" in dlg
    for marker in ("function editStudyBtn(", "function deleteStudyBtn("):
        assert '"studies"' in _fn_body(_PAGE, marker), marker


def test_switch_lang_reloads_first_and_reports_a_failed_save():
    body = _fn_body(_PAGE, "async function switchLang()")
    assert body.index("await loadAll()") < body.index('"/me/language"')
    assert "try" in body and "catch" in body and "tell(" in body


def test_api_helper_maps_network_failures_to_a_human_message():
    body = _fn_body(_PAGE, "async function api(path, opts)")
    assert "TypeError" in body, "فشلُ fetch يصل خاماً"
    assert "تعذّر الاتصال بالخادم" in body


def test_plan_card_derives_its_feature_hint_from_pricing_flags():
    assert "تصدير التقارير ووصول API والعلامة البيضاء في الباقة البلاتينية." not in _PAGE
    card = _PAGE[_PAGE.index('ar_en("الباقة الحالية"'):]
    card = card[:card.index("if (next) {")]
    assert "api_access" in card and "white_label" in card
    assert "في الباقة " in card
    assert 'dd(TIER_AR, TIER_EN, "gold")' in card
    assert 't.key === "platinum"' not in card


def test_research_costs_declare_their_window(monkeypatch):
    info = seed(monkeypatch)
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    rc = cl.get("/platform/admin/metrics", headers=hdr(tok)).json()["research_costs"]
    assert rc.get("available") is True, rc
    assert rc["window"] == 8
    assert "rc.window" in _fn_body(_PAGE, "function renderResearchCosts(rc)")


def test_no_hardcoded_arabic_button_labels_remain():
    assert '}, "حفظ");' not in _PAGE
    assert '}, "احذف نهائياً");' not in _PAGE
    assert "_durText" in _PAGE and "grace_s" in _fn_body(_PAGE, "function _durText(s)")


# ══════════════ FE-25 — تقاريرُ المقعد المحاكى موسومةٌ عيّنةً (تحقّقٌ بالتصميم) ═══════
def test_fake_engine_reports_carry_the_sample_caveat():
    from silk_platform import engine_bridge
    out = engine_bridge._fake_result("عسل سدر", "040900")
    blob = str(out)
    assert "عيّنة" in blob and "fake" in blob.lower()


# ══════════════ رُتبة ٣ — الخطواتُ الجديدة موجودة في التدفّق ═════════════════════════
def test_rung3_platform_flow_has_the_new_steps():
    flow = _read("tests/e2e/platform_flow.cjs")
    for step in ("factory_bell_click_zeroes_badge", "factory_hs_source_badge",
                 "admin_all_studies_no_note_below_limit"):
        assert f'ok("{step}")' in flow, step


# ══════════════ مراجعة R6 (/code-review high) — اكتشافاتٌ أُقفلت أحمر أوّلاً ════════════
def test_notif_menu_falls_back_to_mark_all_when_unread_exceeds_the_page():
    """القائمةُ صفحةٌ (أحدث ٣٠): إرسالُ معرّفات المعروض وحده كان يترك ما فوق الصفحة غيرَ
    مقروء إلى الأبد (الشارةُ تعود بعد الاستطلاع ولا تُصفَّر) — يُعلَّم الكلُّ حين يفيض."""
    body = _fn_body(_PAGE, "async function toggleNotifMenu()")
    assert "NOTIF.unread > ids.length" in body
    # P3 (BIZ-11، تدقيق 2026-09-01) **حدّث العقد**: البطّانيةُ (`{}` = علّم الكلّ)
    # كانت تبتلع ما وصل بعد العرض، فصارت علامةً مائية عند أحدثِ معرّفٍ مرئيّ.
    # المعنى المقفول واحد: حين يفيض غيرُ المقروء عن الصفحة لا نرسل معرّفاتِ
    # المعروض وحدها. النصُّ المقفول تغيّر لأنّ السلوكَ تحسّن، لا لأنّ القفل أزعج.
    assert "{up_to_id: seenMax} : {ids}" in body


def test_reset_page_renders_structured_policy_details():
    """`password_policy` صار `{error, message}` — صفحةُ إعادة التعيين كانت تعرض النصَّ فقط
    حين يكون `detail` نصّاً، فضاع سببُ الرفض."""
    page = _read("web/reset-password.html")
    assert "d.message" in page


def test_dead_study_fields_are_not_writable_anywhere():
    """FE-8 قال «الطلبُ لا يكتبها» — قائمةُ الكتابة في المستودع كانت ما تزال تسمح بها،
    وسطرُ `target_count = 0` كتابةٌ ميتة (العمودُ بافتراضٍ ٠)."""
    from silk_platform import repository
    for dead in ("title_en", "description_en", "target_count"):
        assert dead not in repository._WRITABLE["studies"], dead
    assert 'fields["target_count"] = 0' not in _read("silk_platform/api.py")


def test_upload_and_wallet_rejections_are_structured(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "ext@f.local")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    r = cl.post("/platform/images", files={"file": ("x.exe", b"MZ" * 40, "application/octet-stream")},
                headers=hdr(tok))
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] in ("bad_upload", "image_content_mismatch"), r.text
    assert "bad_upload" in _dict_keys("ERR_AR") and "bad_upload" in _dict_keys("ERR_EN")
