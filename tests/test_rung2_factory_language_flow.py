"""رُتبة ٢ — التدفّق الكامل للغة المصنع على **خادم حقيقي** (real-server lane).

> **لماذا ملفٌّ مستقلّ.** `test_rung2_real_server.py` يضرب لوحة المحرّك؛ هذا
> يضرب **مسار المصنع** كاملاً عبر HTTP حقيقي على `uvicorn api:app`:
>
>   إعدادات المصنع → تغيير لغة التقارير → حفظ → إنشاء دراسة → لقطة اللغة
>   → توليد التقرير → DOCX نهائي → PDF نهائي
>
> باللغتين. الحزمةُ الهرمتية تُثبِت العقود على TestClient؛ هذه الرتبة تُثبِت
> أنّ **الخادم المُقلَع فعلاً** يسلّم مصنوعاً بلغة المصنع الصحيحة.

المفاتيح المدفوعة منزوعة صراحةً في `LiveShapeServer`، ومقعدُ المحرّك المحاكى
(`SILK_PLATFORM_FAKE_ENGINE=deep`) يستبدل البحثَ الحيّ — فتشغيلةُ الدراسة
تعبر مسار الجسر الحقيقي (مطالبة ذرّية ← حصّة ← خيط ← حفظ) بلا نداءٍ خارجي.

Run: SILK_RUN_E2E=1 python3 -m pytest tests/test_rung2_factory_language_flow.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import silk_i18n  # noqa: E402

pytestmark = pytest.mark.e2e


# ── عميل HTTP صغير (نفس نمط رُتبة ٢ القائمة: urllib لا مكتبة إضافية) ────────

def _req(base: str, path: str, *, method: str = "GET", token: str = "",
         body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})


def _json(base: str, path: str, **kw):
    status, raw, _ = _req(base, path, **kw)
    try:
        return status, json.loads(raw.decode() or "{}")
    except Exception:  # noqa: BLE001
        return status, {"_raw": raw[:400].decode(errors="replace")}


@pytest.fixture(scope="module")
def server():
    from live_shape_server import LiveShapeServer
    with LiveShapeServer(platform=True) as srv:
        # المصنعُ المبذور «فضّي» بسقفٍ شهريّ حقيقيّ (٢ دراسات) — وهذا الملفّ
        # يُطلق أكثر. الترقيةُ تجري عبر **نقطة الأدمِن الحقيقية** لا بكتابةٍ
        # مباشرة في القاعدة: بوّابةُ الحصّة نفسها تبقى فاعلةً كما في الإنتاج،
        # ونحن نرفع السقفَ بالمسار المشروع بدل تعطيل الحارس.
        st, out = _json(srv.base_url, "/platform/auth/login", method="POST",
                        body={"email": LiveShapeServer.PLATFORM_ADMIN_EMAIL,
                              "password": LiveShapeServer.PLATFORM_PASSWORD})
        assert st == 200, out
        admin = out["token"]
        st, me = _json(srv.base_url, "/platform/auth/login", method="POST",
                       body={"email": LiveShapeServer.PLATFORM_FACTORY_EMAIL,
                             "password": LiveShapeServer.PLATFORM_PASSWORD})
        assert st == 200, me
        st, who = _json(srv.base_url, "/platform/me", token=me["token"])
        assert st == 200, who
        st, up = _json(srv.base_url,
                       f"/platform/admin/accounts/{who['account_id']}/tier",
                       method="POST", token=admin, body={"tier": "gold"})
        assert st == 200, up
        yield srv


def _login(base: str) -> str:
    from live_shape_server import LiveShapeServer as L
    st, out = _json(base, "/platform/auth/login", method="POST",
                    body={"email": L.PLATFORM_FACTORY_EMAIL,
                          "password": L.PLATFORM_PASSWORD})
    assert st == 200, out
    return out["token"]


def _set_report_language(base: str, token: str, lang: str) -> None:
    """مسارُ الحفظ الحقيقي — نفس النقطة التي تنقرها الواجهة."""
    st, out = _json(base, "/platform/account/language", method="PATCH",
                    token=token, body={"language_preference": lang})
    assert st == 200 and out.get("factory_language") == lang, out


def _create_and_launch(base: str, token: str, product: str) -> int:
    st, study = _json(base, "/platform/studies", method="POST", token=token,
                      body={"product": product, "market_pref": "ARE",
                            "hs_code": "080410"})
    assert st in (200, 201), study
    sid = study["id"]
    st, out = _json(base, f"/platform/studies/{sid}/launch", method="POST",
                    token=token)
    assert st == 200, out
    return sid


def _await_completion(base: str, token: str, sid: int,
                      timeout: float = 90.0) -> dict:
    """انتظر اكتمال الدراسة عبر **نقطة القراءة العامّة** لا عبر داخل العملية.

    الخادم عمليةٌ منفصلة، فلا وصول لـ`engine_bridge.wait_idle` من هنا —
    الاستطلاعُ عبر HTTP هو ما يفعله المتصفّح نفسه.
    """
    deadline = time.monotonic() + timeout
    row: dict = {}
    while time.monotonic() < deadline:
        st, row = _json(base, f"/platform/studies/{sid}", token=token)
        assert st == 200, row
        if row.get("state") in ("completed", "draft") and (
                row.get("analysis_id") or row.get("run_error")):
            break
        time.sleep(1.0)
    assert row.get("state") == "completed", (
        f"الدراسة لم تكتمل: state={row.get('state')} "
        f"run_error={row.get('run_error')}")
    return row


def _download(base: str, token: str, path: str, dest: str) -> str:
    status, raw, _ = _req(base, path, token=token)
    assert status == 200, f"{path} -> {status}: {raw[:300]!r}"
    with open(dest, "wb") as fh:
        fh.write(raw)
    return dest


def _pdf_text(pdf_path: str) -> str:
    """نصُّ الـPDF المُسلَّم فعلاً — الدليلُ على المصنوع النهائي لا الوسيط."""
    if not shutil.which("pdftotext"):
        if os.environ.get("SILK_PDF_LOCAL_SKIP", "").strip() in ("1", "true"):
            pytest.skip("SILK_PDF_LOCAL_SKIP=1 — نصّ الـPDF لم يُستخرَج")
        pytest.fail("pdftotext غائب — لا يُتحقَّق من لغة الـPDF النهائي")
    out = pdf_path + ".txt"
    subprocess.run(["pdftotext", "-enc", "UTF-8", pdf_path, out],
                   check=True, timeout=120)
    with open(out, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _docx_text(path: str) -> str:
    from tests.conftest import docx_all_text
    return docx_all_text(path)


# ══════════════════════════════════════════════════════════════════════════
# التدفّق الكامل — باللغتين، على خادمٍ حقيقي
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang,product", [("ar", "تمور"), ("en", "dates")])
def test_full_factory_language_flow_over_a_real_server(lang, product, server,
                                                       tmp_path):
    """إعدادات المصنع ← لغة ← حفظ ← دراسة ← لقطة ← تقرير ← DOCX ← PDF.

    كلُّ خطوةٍ عبر HTTP حقيقي على خادمٍ مُقلَع، والتحقّقُ الأخير على **نصّ
    الـPDF المستخرَج** لا على كائنٍ وسيط.
    """
    base = server.base_url
    token = _login(base)

    # (١) إعدادات المصنع: غيّر لغة التقارير واحفظ — ثم تأكّد أنها حُفِظت فعلاً.
    _set_report_language(base, token, lang)
    st, me = _json(base, "/platform/me", token=token)
    assert st == 200 and me["factory_language"] == lang, me
    assert me["factory_language_chosen"] is True

    # (٢) أنشئ دراسةً وأطلقها — مسارُ الجسر الحقيقي بمقعدٍ محاكى.
    sid = _create_and_launch(base, token, product)
    row = _await_completion(base, token, sid)

    # (٣) لقطةُ اللغة مختومةٌ على الدراسة نفسها.
    st, rep = _json(base, f"/platform/studies/{sid}/report", token=token)
    assert st == 200, rep
    assert rep["study"]["report_language"] == lang
    assert rep["study"]["factory_language_at_generation"] == lang
    assert rep["view"]["report_language"] == lang

    # (٣ب) **الموجة Z · Z-06** — أساسُ الحكم يصل حمولةَ سطح المصنع نفسِه،
    # لا كائناً وسيطاً في الذاكرة: `web/platform.html` يعرض `decision.basis`،
    # فغيابُه من هذه الحمولة يعني سطحاً يقرأ حكماً بلا أن يعرف على أيّ شيءٍ
    # بُني — وهو البند الذي وُجدت الموجةُ Z لإغلاقه.
    _dec = (rep["view"].get("decision") or {})
    _basis = _dec.get("basis")
    if _dec.get("verdict"):
        assert _basis, "حكمٌ يصل المصنع بلا أساسٍ معروض (Z-06)"
        assert _basis.get("pillars"), _basis
        for _k in ("col_pillar", "col_strength", "col_note", "not_computed",
                   "conditions_head"):
            assert _basis.get(_k), f"مفتاحُ عرضٍ ناقص: {_k}"
        _blob = json.dumps(_basis, ensure_ascii=False)
        for _bad in ("political_stability", "tam_log", "price_position"):
            assert _bad not in _blob, f"معرّفٌ داخليّ في حمولة المصنع: {_bad}"
        assert silk_i18n.foreign_prose_spans(
            " ".join([_basis.get("head", "")]
                     + [r.get("note", "") for r in _basis["pillars"]]
                     + list(_basis.get("conditions") or [])), lang) == [], (
            f"أساسُ الحكم بلغةٍ غير «{lang}» على سطح المصنع")

    # (٤) DOCX النهائي — يُنزَّل من الخادم ويُقرأ فعلاً.
    docx = _download(base, token, f"/platform/studies/{sid}/report.docx",
                     str(tmp_path / f"r_{lang}.docx"))
    assert os.path.getsize(docx) > 5000
    dtext = _docx_text(docx)
    allow = silk_i18n.entity_allowlist(rep["view"])
    assert silk_i18n.foreign_prose_spans(dtext, lang, allow) == [], (
        f"DOCX بلغة «{lang}» فيه نثرٌ بلغةٍ أخرى")

    # (٥) PDF النهائي — يُحوَّل على الخادم ويُستخرَج نصُّه هنا.
    st, raw, hdrs = _req(base, f"/platform/studies/{sid}/report.pdf",
                         token=token)
    if st == 503:
        # نصّ السبب المُعلَن يُطبَع مع الفشل (عودة CI الحيّة 2026-08-27): 503
        # تأتي من ثلاثة فروع مختلفة (لا محرّك / فشل تحويل / رفض حارس الأقواس)،
        # وبلا النصّ يستحيل التمييز بينها من سجلّ CI.
        detail = raw.decode("utf-8", "replace")[:400] if isinstance(
            raw, (bytes, bytearray)) else str(raw)[:400]
        pytest.fail("تعذّر تصدير PDF من الخادم (503) — لا يُعلَن التسليم "
                    f"جاهزاً بلا PDF مُتحقَّق منه. سبب الخادم: {detail}")
    assert st == 200, raw[:300]
    pdf = str(tmp_path / f"r_{lang}.pdf")
    with open(pdf, "wb") as fh:
        fh.write(raw)
    assert raw[:5] == b"%PDF-"
    body = _pdf_text(pdf)
    assert len(body.strip()) > 200, "نصّ الـPDF شبه فارغ — تحويلٌ فاشلٌ صامت"
    assert silk_i18n.foreign_prose_spans(body, lang, allow) == [], (
        f"PDF بلغة «{lang}» فيه نثرٌ بلغةٍ أخرى")

    # (٦) مرساةٌ إيجابية على الغلاف **والتذييل** — التذييل يُطبَع على كل صفحة
    # ولا يراه فحصُ متن الـdocx إطلاقاً (python-docx لا يقرأ الترويسات).
    if lang == "ar":
        assert "دراسة سوق" in body
        assert "سلك" in body or "سِلك" in body
    else:
        assert "Export Market Study" in body
        assert "Silk Market Intelligence" in body, (
            "تذييلُ الصفحة ليس بلغة التقرير")
        assert "منصة تحليل أسواق التصدير" not in body, (
            "تذييلٌ عربيٌّ على تقريرٍ إنجليزيّ")


def test_language_change_mid_run_does_not_touch_a_running_study(server):
    """تبديلُ لغة المصنع **أثناء** تشغيلةٍ حيّة لا يمسّ لقطتها."""
    base = server.base_url
    token = _login(base)
    _set_report_language(base, token, "ar")
    sid = _create_and_launch(base, token, "حليب")
    # التبديل فوراً بعد الإطلاق — بينما الخيط يعمل أو بعد اكتماله مباشرةً.
    _set_report_language(base, token, "en")
    _await_completion(base, token, sid)
    st, rep = _json(base, f"/platform/studies/{sid}/report", token=token)
    assert st == 200, rep
    assert rep["study"]["report_language"] == "ar", (
        "لقطةُ دراسةٍ جارية انقلبت بتبديلٍ لاحق")
    assert rep["view"]["report_language"] == "ar"
    # والدراسةُ **التالية** تتبع الإعداد الجديد — الإعداد يحكم القادم لا الماضي.
    sid2 = _create_and_launch(base, token, "milk")
    _await_completion(base, token, sid2)
    st, rep2 = _json(base, f"/platform/studies/{sid2}/report", token=token)
    assert st == 200 and rep2["study"]["report_language"] == "en"


def test_no_request_header_can_override_the_factory_language(server):
    """`Accept-Language` وغيرُه **لا** يغيّر لغة التقرير — مصدرُ الحقيقة واحد.

    المصنعُ عربيّ؛ نطلب تقريره بترويسةٍ إنجليزيةٍ صريحة فيجب أن يبقى عربياً.
    """
    base = server.base_url
    token = _login(base)
    _set_report_language(base, token, "ar")
    sid = _create_and_launch(base, token, "تمور")
    _await_completion(base, token, sid)

    req = urllib.request.Request(
        base + f"/platform/studies/{sid}/report")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept-Language", "en-US,en;q=0.9")
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.loads(r.read().decode())
    assert payload["study"]["report_language"] == "ar", (
        "ترويسةُ طلبٍ قلبت لغة التقرير — مصدرُ الحقيقة انكسر")
    assert payload["view"]["report_language"] == "ar"


def test_the_arabic_flow_is_unchanged_end_to_end(server, tmp_path):
    """المسارُ العربي (السلوك القائم) يسلّم DOCX وPDF عربيَّين كما كان."""
    base = server.base_url
    token = _login(base)
    _set_report_language(base, token, "ar")
    sid = _create_and_launch(base, token, "تمور سكري")
    _await_completion(base, token, sid)
    docx = _download(base, token, f"/platform/studies/{sid}/report.docx",
                     str(tmp_path / "ar_flow.docx"))
    text = _docx_text(docx)
    # العناوين العربية القائمة حرفياً — لا انحدار في اللغة الافتراضية.
    for needle in ("دراسة سوق تصديرية", "القرار وأساسه", "المراجع"):
        assert needle in text, f"عنوانٌ عربيٌّ قائم اختفى: {needle}"
