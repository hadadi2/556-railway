"""لغة المصنع تحكم لغة التقرير — factory language controls report language.

> **العقد المُختبَر (الموجة ٠).** إعدادُ لغةٍ **على مستوى المصنع** هو المصدر
> الوحيد للغة أيّ تقريرٍ يُولَّد؛ تُلتقَط لقطتُه ذرّياً عند إطلاق الدراسة؛ ولا
> يُولَّد إلا تقريرٌ واحد بتلك اللغة. لا اختيارَ لغةٍ أثناء التوليد، ولا توليدَ
> مزدوج، ولا مسارَ ترجمةٍ من لغةٍ إلى أخرى.
>
> ويُفحَص **المصنوعُ النهائي** (DOCX، ومعه PDF حين يتوفّر المحوّل) لا الكائنُ
> الوسيط: عرضٌ صحيحٌ خلف مستندٍ خاطئ اللغة فشلٌ كامل من زاوية المصنع.

Run: python3 -m pytest tests/test_factory_report_language.py -q
"""
from __future__ import annotations

import ast
import os
import pathlib
import shutil
import subprocess

import pytest

import silk_i18n
from tests.conftest import docx_all_text
from tests.platform_helpers import (client, hdr, login, make_factory,
                                    make_product_study, seed)

_ROOT = pathlib.Path(__file__).resolve().parent.parent
PW = "Factory1234"


# ── أدوات مشتركة · shared fixtures ──────────────────────────────────────────

def _set_factory_language(account_id: int, lang: str) -> None:
    """اكتب لغة المصنع مباشرةً — مسار الكتابة نفسه الذي تستعمله النقطة."""
    from silk_platform import db as pdb, factory_settings as fs
    conn = pdb.connect()
    try:
        fs.set_factory_language(conn, account_id, lang)
        conn.commit()
    finally:
        conn.close()


def _study_row(study_id: int) -> dict:
    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        row = conn.execute("SELECT * FROM studies WHERE id = ?",
                           (study_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def _canonical_result(lang_marker_ar: bool = True) -> dict:
    """نتيجةُ بحثٍ عميقٍ قانونية واحدة — **نفس الأرقام** مهما كانت لغة العرض.

    الأدلة عربية عمداً (طبقة الأدلة الداخلية عربية — §17)، فيثبت الاختبار أن
    تقريراً إنجليزياً لا يرث حرفاً منها.
    """
    return {
        "product": "حليب مبستر", "hs_code": "040110", "classified": True,
        "year": 2024, "data_year": 2023, "markets": [],
        "deep_research": {
            "market": {"iso3": "JOR", "name_ar": "الأردن", "name_en": "Jordan"},
            "missions": {
                "trade_flow": {
                    "agent": "LLMMissionAgent:trade_flow", "ok": True,
                    "summary": "بلغت واردات الأردن 8.47 مليون دولار سنة 2023.",
                    "findings": [{"value": "واردات 2023: 8.47 مليون دولار",
                                  "source": "UN Comtrade", "confidence": 0.9,
                                  "retrieved_at": "2026-08-01"}]},
                "competitors": {
                    "agent": "LLMMissionAgent:competitors", "ok": True,
                    "summary": "حصة السعودية 12% من واردات السوق.",
                    "findings": [{"value": "حصة السعودية 12%",
                                  "source": "UN Comtrade", "confidence": 0.8,
                                  "retrieved_at": "2026-08-01"}]},
            },
            "analyst": {"report": {"summary": "تقاطعات مكتملة جزئياً.",
                                   "ok": True},
                        "missing_categories": ["entry_cost"],
                        "by_category": {}},
            "verdict": {"verdict": "CONDITIONAL-GO", "confidence": 0.62,
                        "note": "دخول مشروط بحسم بيانات 2024."},
            "report": {"report": _writer_text_ar() if lang_marker_ar
                       else _writer_text_en(),
                       "review_cycles": 1, "unresolved_notes": []},
        },
    }


def _writer_text_ar() -> str:
    from silk_ai_judge import report_sections
    secs = report_sections("ar")
    body = []
    # الحشو متنوّع بعدد القسم عمداً — التكرار الحرفي يُفشِله `repeated_span`
    # (البند 11، الدرس 131) وسؤال هذا الملف لغةُ الفحص لا التكرار.
    for i, s in enumerate(secs, 1):
        body.append(f"## {i}. {s}\nبلغت واردات الأردن في محور {s} نحو "
                    f"{8 + i}.4 مليون دولار سنة 2023 وفق UN Comtrade.")
    return "\n\n".join(body)


def _writer_text_en() -> str:
    from silk_ai_judge import report_sections
    secs = report_sections("en")
    body = []
    for i, s in enumerate(secs, 1):
        body.append(f"## {i}. {s}\nWithin the {s} scope, Jordan's imports "
                    f"reached USD {8 + i}.4 million in 2023 per UN Comtrade.")
    return "\n\n".join(body)


def _render_client_docx(result: dict, lang: str, tmp_path) -> str:
    """ابنِ **المصنوع النهائي** بنفس مسار الإنتاج: build_view ← render_client_docx."""
    from silk_render import build_view
    from silk_reports import render_client_docx
    view = build_view(result, lang)
    out = os.path.join(str(tmp_path), f"client_{lang}.docx")
    return render_client_docx(view, out)


def _allowlist(result: dict, lang: str) -> tuple:
    """استثناءُ الكيانات المرصودة — **نفس** ما تستعمله البوابة في الإنتاج.

    الفحص بلا هذه القائمة أشدُّ من العقد نفسه: أسماءُ المصادر والعلامات
    الرسمية استثناءٌ بنيويّ مُعلَن (§13)، وحجبُها يجعل الاختبار يرفض تقريراً
    سليماً. نستعملها هنا كي يقيس الاختبارُ العقدَ المكتوب لا عقداً أشدّ منه.
    """
    from silk_render import build_view
    return silk_i18n.entity_allowlist(build_view(result, lang))


# ══════════════════════════════════════════════════════════════════════════
# §16 — الاختبارات الخمسة المطلوبة حرفياً
# ══════════════════════════════════════════════════════════════════════════

def test_1_factory_arabic_produces_an_arabic_artifact(monkeypatch, tmp_path):
    """لغة المصنع = ar ⇒ لقطةُ الدراسة «ar» و**المصنوع النهائي عربي**."""
    seed(monkeypatch)
    acc = make_factory("gold", "ar-factory@f.local")
    _set_factory_language(acc["account_id"], "ar")
    with client() as cl:
        tok = login(cl, "ar-factory@f.local", PW)
        sid = make_product_study(acc["account_id"], acc["user_id"], "حليب")
        from tests.platform_helpers import mock_engine
        mock_engine(monkeypatch)
        r = cl.post(f"/platform/studies/{sid}/launch", headers=hdr(tok))
        assert r.status_code == 200, r.text
    row = _study_row(sid)
    assert row["report_language"] == "ar"
    assert row["factory_language_at_generation"] == "ar"

    path = _render_client_docx(_canonical_result(True), "ar", tmp_path)
    text = docx_all_text(path)
    assert silk_i18n.foreign_prose_spans(text, "ar") == [], (
        "تقريرٌ عربيّ يحوي نثراً إنجليزياً")
    assert "دراسة سوق تصديرية" in text          # الغلاف بالعربية فعلاً
    assert "القرار وأساسه" in text              # عنوانُ قسمٍ عربيّ


def test_2_factory_english_produces_an_english_artifact(monkeypatch, tmp_path):
    """لغة المصنع = en ⇒ لقطةُ الدراسة «en» و**المصنوع النهائي إنجليزي**."""
    seed(monkeypatch)
    acc = make_factory("gold", "en-factory@f.local")
    _set_factory_language(acc["account_id"], "en")
    with client() as cl:
        tok = login(cl, "en-factory@f.local", PW)
        sid = make_product_study(acc["account_id"], acc["user_id"], "milk")
        from tests.platform_helpers import mock_engine
        mock_engine(monkeypatch)
        r = cl.post(f"/platform/studies/{sid}/launch", headers=hdr(tok))
        assert r.status_code == 200, r.text
    row = _study_row(sid)
    assert row["report_language"] == "en"
    assert row["factory_language_at_generation"] == "en"

    path = _render_client_docx(_canonical_result(False), "en", tmp_path)
    text = docx_all_text(path)
    assert silk_i18n.foreign_prose_spans(text, "en") == [], (
        "تقريرٌ إنجليزيّ يحوي نثراً عربياً")
    assert "Export Market Study" in text
    assert "The decision and its basis" in text
    # ولا يحمل عنواناً عربياً من القالب:
    assert "القرار وأساسه" not in text


def test_3_started_arabic_stays_arabic_when_factory_switches(monkeypatch):
    """بدءٌ بالعربية ← تبديلُ المصنع للإنجليزية ← الدراسة تبقى عربية."""
    seed(monkeypatch)
    acc = make_factory("gold", "flip-ar@f.local")
    _set_factory_language(acc["account_id"], "ar")
    with client() as cl:
        tok = login(cl, "flip-ar@f.local", PW)
        sid = make_product_study(acc["account_id"], acc["user_id"], "حليب")
        from tests.platform_helpers import mock_engine
        mock_engine(monkeypatch)
        assert cl.post(f"/platform/studies/{sid}/launch",
                       headers=hdr(tok)).status_code == 200
        # تبديلٌ **بعد** الإطلاق عبر النقطة الحقيقية.
        r = cl.patch("/platform/account/language", headers=hdr(tok),
                     json={"language_preference": "en"})
        assert r.status_code == 200, r.text
    assert _study_row(sid)["report_language"] == "ar", (
        "لقطةُ الدراسة انقلبت بتبديلٍ لاحق — تقريرٌ مولَّد لا تتغيّر لغته")


def test_4_started_english_stays_english_when_factory_switches(monkeypatch):
    """بدءٌ بالإنجليزية ← تبديلُ المصنع للعربية ← الدراسة تبقى إنجليزية."""
    seed(monkeypatch)
    acc = make_factory("gold", "flip-en@f.local")
    _set_factory_language(acc["account_id"], "en")
    with client() as cl:
        tok = login(cl, "flip-en@f.local", PW)
        sid = make_product_study(acc["account_id"], acc["user_id"], "milk")
        from tests.platform_helpers import mock_engine
        mock_engine(monkeypatch)
        assert cl.post(f"/platform/studies/{sid}/launch",
                       headers=hdr(tok)).status_code == 200
        r = cl.patch("/platform/account/language", headers=hdr(tok),
                     json={"language_preference": "ar"})
        assert r.status_code == 200, r.text
    assert _study_row(sid)["report_language"] == "en"


def test_5_both_languages_consume_the_same_canonical_object(tmp_path):
    """**تكافؤ دلاليّ بنيويّ**: العارضان يقرآن الكائن التحليلي نفسه.

    الإثباتُ على **الكائن** لا على نصّه: استخراجُ الأرقام من النثر دليلٌ ضعيف
    (رقمٌ ناقص يمرّ صامتاً)، والمطلوب أن يكون القرارُ والثقةُ والموانعُ
    والمخاطرُ والمصادرُ والإجراءات **هي هي** قبل العرض أصلاً.
    """
    from silk_render import build_view
    result = _canonical_result(True)
    v_ar = build_view(result, "ar")
    v_en = build_view(result, "en")

    dr_ar, dr_en = v_ar["deep_research"], v_en["deep_research"]
    # (١) الحكم واحدٌ رمزاً ونغمةً — التسميةُ وحدها تختلف.
    assert dr_ar["verdict"] == dr_en["verdict"]
    assert dr_ar["verdict_tone"] == dr_en["verdict_tone"]
    assert dr_ar["verdict_label"] != dr_en["verdict_label"]
    # (٢) الثقة والأرقام والأدلة — متطابقة بنيوياً.
    assert (dr_ar["verdict"] or {}).get("confidence") == \
           (dr_en["verdict"] or {}).get("confidence")
    assert dr_ar["missions"].keys() == dr_en["missions"].keys()
    for key in dr_ar["missions"]:
        f_ar = dr_ar["missions"][key]["findings"]
        f_en = dr_en["missions"][key]["findings"]
        assert [x.get("value") for x in f_ar] == [x.get("value") for x in f_en]
        assert [x.get("source") for x in f_ar] == [x.get("source") for x in f_en]
        assert [x.get("confidence") for x in f_ar] == \
               [x.get("confidence") for x in f_en]
    # (٣) عددُ الفجوات المعلنة واحد — النصّ يختلف، والعدّ لا.
    assert len(dr_ar["limits"]) == len(dr_en["limits"])
    assert len(dr_ar.get("gap_register") or []) == \
           len(dr_en.get("gap_register") or [])
    # (٤) لغةُ العرض معلنةٌ صراحةً على العرض نفسه.
    assert v_ar["report_language"] == "ar" and v_en["report_language"] == "en"


# ══════════════════════════════════════════════════════════════════════════
# الفصل الصلب: لغةُ الأدلة الداخلية ≠ لغةُ تقرير العميل (تصحيح المالك ٢)
# ══════════════════════════════════════════════════════════════════════════

def test_arabic_internal_evidence_cannot_leak_into_an_english_client_report(
        tmp_path):
    """أدلّةٌ عربيةٌ + كاتبٌ إنجليزيّ ⇒ صفرُ نثرٍ عربيّ في المصنوع النهائي.

    البعثات هنا عربيةٌ صراحةً (كما في الإنتاج). ما يمنع تسرّبها ليس ثقةً في
    النموذج بل ثلاثُ طبقات: إلزامُ العقد، وتوليدُ النصوص القالبية من مفاتيح
    `silk_i18n`، والبوابةُ الحاجزة.
    """
    result = _canonical_result(False)      # كاتبٌ إنجليزيّ، بعثاتٌ عربية
    path = _render_client_docx(result, "en", tmp_path)
    text = docx_all_text(path)
    spans = silk_i18n.foreign_prose_spans(text, "en")
    assert spans == [], f"تسرّبَ نثرٌ عربيّ إلى تقريرٍ إنجليزيّ: {spans[:2]}"


def test_a_deliberate_arabic_leak_is_blocked_not_warned():
    """حقنُ تسرّبٍ عربيٍّ عمداً ⇒ **FAIL** لا تحذير — البوابة حاجزة."""
    import silk_quality_gate as Q
    leaked = (_writer_text_en()
              + "\n\nتعذّر التحقّق من متطلبات التسجيل لدى الجهة المختصة.")
    findings = Q._check_language_consistency(leaked, "en", {})
    assert findings, "تسرّبٌ عربيٌّ صريح لم تلتقطه بوابة الاتساق"
    assert findings[0]["check"] == "language_consistency"
    assert findings[0]["check"] in Q.FAIL_TRIGGER_CHECKS, (
        "اتساق اللغة ليس حاجزاً — تقريرٌ مختلط يمكن أن يُسلَّم")


def test_language_consistency_and_quality_are_separate_channels():
    """الاتساقُ حاجزٌ في `findings`؛ الجودةُ تحذيريةٌ في قناتها الخاصّة."""
    import silk_quality_gate as Q
    assert "language_consistency" in Q.FAIL_TRIGGER_CHECKS
    # لا فحصَ جودةٍ في قائمة الإفشال — الجودة حكمٌ متدرّج لا ثنائيّ.
    assert not any(c.startswith("language_quality")
                   for c in Q.FAIL_TRIGGER_CHECKS)
    out = Q.run_quality_gate({"deep_research": {
        "report": {"text": _writer_text_ar()}, "missions": {}, "analyst": {}}})
    assert "language_quality" in out and "skipped_checks" in out
    assert out["report_language"] == "ar"


def test_quality_gate_declares_skipped_checks_for_english(tmp_path):
    """فحصٌ بلا مرآةٍ إنجليزية يُعلَن مُتخطّى — لا مرورَ صامت."""
    import silk_quality_gate as Q
    out = Q.run_quality_gate({"report_language": "en", "deep_research": {
        "report": {"text": _writer_text_en()}, "missions": {}, "analyst": {}}})
    skipped = {s["check"] for s in out["skipped_checks"]}
    assert "english_field_and_mission_key_leak" in skipped
    assert all(s.get("reason") for s in out["skipped_checks"]), (
        "بندٌ متخطّى بلا سببٍ معلَن")


# ══════════════════════════════════════════════════════════════════════════
# مصدر الحقيقة — بنيويّاً لا اتفاقياً (تصحيح المالك ٤)
# ══════════════════════════════════════════════════════════════════════════

def test_factory_language_resolver_reads_only_the_account_column():
    """`factory_language` لا تقرأ طلباً ولا ترويسةً ولا تفضيلَ مستخدم.

    حارسٌ بنيويّ (AST) على غرار `tests/test_platform_isolation_ast_guard.py`:
    الاتفاقُ وحده لا يمنع أحداً من إضافة سقوطٍ على `users.language_preference`
    بعد ستّة أشهر — الحارسُ يمنعه.
    """
    src = (_ROOT / "silk_platform" / "factory_settings.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "factory_language")
    args = [a.arg for a in fn.args.args]
    assert args == ["conn", "account_id"], (
        f"مُحلّل لغة المصنع اكتسب مدخلاً جديداً: {args}")
    body = ast.get_source_segment(src, fn) or ""
    for banned in ("request", "header", "Accept-Language", "users",
                   "language_preference FROM users", "localStorage"):
        assert banned.lower() not in body.lower(), (
            f"مُحلّل لغة المصنع يقرأ «{banned}» — مصدرُ الحقيقة انكسر")
    # ولا مسارَ تقريرٍ يقرأ تفضيلَ المستخدم لغةً للتقرير.
    api_src = (_ROOT / "silk_platform" / "api.py").read_text(encoding="utf-8")
    report_zone = api_src.split("/studies/{study_id}/report")[1]
    assert "ctx.language_preference" not in report_zone, (
        "نقطةُ تقريرٍ تقرأ لغة واجهة المستخدم — تصحيح المالك ٤")


def test_study_snapshot_is_written_inside_the_atomic_claim():
    """اللقطة تُكتب في **جملة المطالبة الذرّية نفسها** لا في تحديثٍ لاحق."""
    src = (_ROOT / "silk_platform" / "api.py").read_text(encoding="utf-8")
    claim = src.split("UPDATE studies SET state = 'in_progress'")[1][:900]
    assert "report_language = ?" in claim, (
        "لقطةُ اللغة خرجت من جملة المطالبة الذرّية — تبديلٌ أثناء تشغيلةٍ "
        "حيّة يصير قادراً على إنتاج تقريرٍ مختلط")
    assert "factory_language_at_generation = ?" in claim
    assert "AND state = 'draft'" in claim   # ما تزال ذرّية فعلاً


def test_migration_012_is_additive_only():
    """الترحيل إضافيٌّ بحتاً — لا DROP ولا DELETE ولا تعديلَ صفٍّ قائم."""
    body = (_ROOT / "migrations" / "platform"
            / "013_factory_language.sql").read_text(encoding="utf-8")
    assert body.count("ADD COLUMN") == 4
    # التعليقات تُجرَّد قبل الفحص: رأسُ الترحيل يوثّق القاعدة نصّاً («لا DROP
    # ولا DELETE»)، فمسحُ الملفّ كاملاً كان سيُبلِغ عن نفسه زوراً.
    sql = "\n".join(ln for ln in body.splitlines()
                    if not ln.lstrip().startswith("--")).upper()
    for banned in ("DROP ", "DELETE ", "UPDATE ", "ALTER COLUMN"):
        assert banned not in sql, f"ترحيل غير إضافي: {banned}"
    assert "DEFAULT 'ar'" in body, (
        "الافتراضي ليس عربياً — مصانع قائمة تنقلب لغةُ تقاريرها صامتةً")


def test_patch_account_language_validates_and_audits(monkeypatch):
    """النقطة: تحقّقٌ صارم، ختمُ اختيار، وقيدُ تدقيق — مرآةُ `/me/language`."""
    seed(monkeypatch)
    acc = make_factory("silver", "audit-lang@f.local")
    with client() as cl:
        tok = login(cl, "audit-lang@f.local", PW)
        assert cl.patch("/platform/account/language", headers=hdr(tok),
                        json={"language_preference": "fr"}).status_code == 422
        r = cl.patch("/platform/account/language", headers=hdr(tok),
                     json={"language_preference": "en"})
        assert r.status_code == 200 and r.json()["factory_language"] == "en"
        me = cl.get("/platform/me", headers=hdr(tok)).json()
        assert me["factory_language"] == "en"
        assert me["factory_language_chosen"] is True
        # لغةُ الواجهة **لم تتغيّر** — إعدادان مستقلّان لا يُستبدَل أحدهما بالآخر.
        assert me["language_preference"] == "ar"
    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        rows = [r["action"] for r in conn.execute(
            "SELECT action FROM audit_log WHERE account_id = ?",
            (acc["account_id"],))]
    finally:
        conn.close()
    assert "account_language_changed" in rows


def test_ui_shows_the_language_but_never_asks_for_it():
    """§15: الواجهة تعرض لغة التقرير كمؤشّر، ولا تطلب اختيارها عند التوليد."""
    page = (_ROOT / "web" / "platform.html").read_text(encoding="utf-8")
    # بطاقةُ إعدادٍ حقيقية موصولة بالنقطة الحقيقية (لا حقلٌ معزول).
    assert 'id="rlangSel"' in page and 'id="rlangSaveBtn"' in page
    assert '"/account/language"' in page
    assert "renderReportLangCard" in page
    # الإعدادان متمايزان نصّياً — لا يُقرأ أحدهما مكان الآخر.
    assert "pf_rlang_h" in page and "pf_lang_h" in page
    assert "لغة تقارير المصنع" in page and "لغة الواجهة" in page
    # نافذةُ الدراسة تعرض المؤشّر ولا تحمل منتقياً.
    dialog = page.split("function studyDialog(")[1].split("\nfunction ")[0]
    assert 'id="studyLangNote"' in dialog
    assert "<select" not in dialog.replace('<select id="rlangSel"', ""), (
        "منتقي لغةٍ ظهر في تدفّق إنشاء الدراسة — §15 يمنعه")


def test_the_language_valve_forces_arabic_when_switched_off(monkeypatch):
    """صمّامُ الطبقة (البند ٩١): الإطفاء يعيد السلوك السابق حرفياً."""
    monkeypatch.setenv("SILK_REPORT_LANGUAGE_ENABLED", "0")
    assert silk_i18n.normalize("en") == "ar"
    assert silk_i18n.is_rtl("en") is True
    monkeypatch.delenv("SILK_REPORT_LANGUAGE_ENABLED", raising=False)
    assert silk_i18n.normalize("en") == "en"


def test_terms_dictionary_has_both_languages_for_every_key():
    """تكافؤُ القاموس — مفتاحٌ بلا إحدى اللغتين نصٌّ ناقصٌ يصل العميل."""
    assert silk_i18n.terms_missing_language() == []
    assert len(silk_i18n.TERMS) >= 100
    # ولا قيمةَ مطابقةً حرفياً بين اللغتين إلا حيث يكون ذلك صحيحاً (رموز).
    same = [k for k, v in silk_i18n.TERMS.items() if v["ar"] == v["en"]]
    assert same == [], f"مفاتيحُ تسميتُها واحدة في اللغتين: {same}"


def test_client_guard_has_an_english_mirror_that_allows_business_english():
    """حارسُ نظافة العميل يحرس نفس المعنى بلا حجب لغة الأعمال الشرعية."""
    from silk_reports import _client_forbidden_hits
    legit = ("The regulatory status is confirmed and the entry run rate "
             "supports a successful launch. Call the distributor first.")
    assert _client_forbidden_hits(legit, "en") == [], (
        "الحارس الإنجليزي يحجب نثراً تجارياً شرعياً")
    # ويلتقط التسريب الحقيقي:
    for leak in ("The mission status was successful.",
                 "Volza data confirms the importer.",
                 "See dp7 for the citation."):
        assert _client_forbidden_hits(leak, "en"), f"تسريبٌ لم يُلتقَط: {leak}"


# ══════════════════════════════════════════════════════════════════════════
# المصنوع النهائي: PDF — فشلٌ لا تخطٍّ في الإنتاج/CI (تصحيح المالك ٥)
# ══════════════════════════════════════════════════════════════════════════

def _pdf_skip_allowed() -> bool:
    """التخطّي مسموح **فقط** ببيئةٍ محلّيةٍ موسومة صراحةً."""
    return os.environ.get("SILK_PDF_LOCAL_SKIP", "").strip() in ("1", "true")


@pytest.mark.parametrize("lang", ["ar", "en"])
def test_final_pdf_artifact_is_in_the_factory_language(lang, tmp_path):
    """الدليلُ النهائي: **PDF فعليّ** بنصٍّ باللغة الصحيحة.

    غيابُ محوّل الـPDF **فشلٌ** لا تخطٍّ (تصحيح المالك ٥): الحاوية تشحن
    `soffice` والخطّ، ووظيفةُ CI المطلوبة تشغّل هذا. التخطّي مسموح فقط
    ببيئةٍ محلّيةٍ موسومة `SILK_PDF_LOCAL_SKIP=1`، وحينها يُقال صراحةً إن
    دليل الـPDF **لم يُؤخَذ** — لا يُدَّعى نجاحٌ بلا تحويل.
    """
    from silk_reports import _find_soffice, docx_to_pdf
    if not _find_soffice():
        if _pdf_skip_allowed():
            pytest.skip("SILK_PDF_LOCAL_SKIP=1 — دليل الـPDF لم يُؤخَذ "
                        "(بيئة محلّية بلا LibreOffice)")
        pytest.fail("محوّل الـPDF (soffice) غائب — الإنتاج وCI يشحنانه؛ "
                    "لا يُعلَن التسليم جاهزاً بلا PDF مُتحقَّق منه")
    docx = _render_client_docx(_canonical_result(lang == "ar"), lang, tmp_path)
    pdf = docx_to_pdf(docx, os.path.join(str(tmp_path), f"out_{lang}.pdf"),
                      lang=lang)
    assert os.path.getsize(pdf) > 2000
    with open(pdf, "rb") as fh:
        assert fh.read(5) == b"%PDF-"

    # **النصّ المستخرَج من الـPDF نفسه** — لا حجمُ الملفّ وحده: ملفٌّ سليمُ
    # الترويسة قد يحمل لغةً خاطئة. هذا هو الدليل الذي طلبه المالك.
    if not shutil.which("pdftotext"):
        if _pdf_skip_allowed():
            pytest.skip("SILK_PDF_LOCAL_SKIP=1 — نصّ الـPDF لم يُستخرَج")
        pytest.fail("pdftotext غائب — لا يُتحقَّق من لغة الـPDF النهائي")
    txt_path = os.path.join(str(tmp_path), f"out_{lang}.txt")
    subprocess.run(["pdftotext", "-enc", "UTF-8", pdf, txt_path],
                   check=True, timeout=120)
    body = pathlib.Path(txt_path).read_text(encoding="utf-8", errors="replace")
    assert len(body.strip()) > 200, "نصّ الـPDF شبه فارغ — تحويلٌ فاشلٌ صامت"
    spans = silk_i18n.foreign_prose_spans(
        body, lang, _allowlist(_canonical_result(lang == "ar"), lang))
    assert spans == [], (
        f"الـPDF النهائي بلغة «{lang}» يحوي نثراً بلغةٍ أخرى: {spans[:2]}")
    # ومرساةٌ إيجابية: عنوانُ الغلاف بلغته فعلاً داخل الـPDF المُسلَّم.
    anchor = ("دراسة سوق" if lang == "ar" else "Export Market Study")
    assert anchor in body, f"غلافُ الـPDF لا يحمل «{anchor}»"

# ══════════════════════════════════════════════════════════════════════════
# مراجعة ذاتية (§58) — التقرير **الغنيّ** بالإنجليزية: العائلة التي انكسرت
# ══════════════════════════════════════════════════════════════════════════
#
# المراجعةُ الذاتية كشفت أنّ المرورَ الأول اختبر تقريراً إنجليزياً **فقيراً**:
# بلا نموذجٍ اقتصادي، بلا مسرد، بلا جهات اتصال، بلا تدهور — فلم تُستدعَ
# المُصيّراتُ العربية الثابتة أصلاً. هذا الاختبار يبني العرضَ الغنيّ الذي
# يستدعيها كلَّها معاً، فيقفل العائلة لا الحالةَ الواحدة.

def _rich_result(lang: str) -> dict:
    """نتيجةٌ تُشغِّل **كلَّ** مُصيّرٍ فرعيّ: اقتصاد + مسرد + جهات اتصال + تدهور."""
    result = _canonical_result(lang == "ar")
    dr = result["deep_research"]
    dr["economics"] = {
        "anchor_price": {"per_unit": 4.2, "currency": "EUR"},
        "reverse_solve": {"max_exw": 2.1, "headline_scenario": "base",
                          "scenarios": [{"scenario": "base", "freight_pct": 8,
                                         "distributor_pct": 15,
                                         "retailer_pct": 30, "max_exw": 2.1}]},
    }
    dr["importer_leads"] = {
        "path": "scraper",
        "note": "مرصود عبر مكشطة خرائط قوقل — ملاحظةٌ داخلية عربية",
        "leads": [{"name": "Al Noor Trading BV",
                   "address": "Damrak 12, Amsterdam", "phone": "+31 20 555 0100",
                   "email": "info@alnoor.example", "website": "alnoor.example",
                   "rating": 4.4, "review_count": 87, "maps_link": "—",
                   "doc_level": "◐ مرشّح موثَّق جزئياً"}],
    }
    dr["glossary"] = [{"term": "HHI", "gloss": "مؤشر يقيس تركّز السوق"}]
    result["degraded"] = True
    result["degraded_reason"] = "تعذّر الوصول لخدمة التحليل الآلي"
    dr["degraded"] = True
    dr["degraded_reason"] = result["degraded_reason"]
    return result


@pytest.mark.parametrize("lang", ["ar", "en"])
def test_a_rich_report_renders_clean_in_both_languages(lang, tmp_path):
    """تقريرٌ غنيٌّ بكلّ أقسامه يخرج **نظيفَ اللغة** في اللغتين.

    كانت المُصيّراتُ العربية الثابتة (الاقتصاد، المسرد، لافتة التدهور، جدول
    جهات الاتصال، مُطهِّر العميل، طبقة «لغة التاجر») تعمل بلا شرطٍ لغويّ —
    فتصطدم بالبوابة الحاجزة ويخرج المصنع الإنجليزيّ **بلا تقرير إطلاقاً**.
    """
    path = _render_client_docx(_rich_result(lang), lang, tmp_path)
    text = docx_all_text(path)
    spans = silk_i18n.foreign_prose_spans(
        text, lang, _allowlist(_rich_result(lang), lang))
    assert spans == [], f"تقريرٌ غنيّ بلغة «{lang}» فيه نثرٌ أجنبيّ: {spans[:2]}"
    # ولافتةُ التدهور **حاضرة** — التحذير لا يضيع مع تفريع اللغة.
    assert "DEGRADED" in text, "لافتة التدهور سقطت من التقرير"


def test_entity_allowlist_reads_the_leads_list_not_the_wrapper_dict():
    """`importer_leads` قاموسٌ لا قائمة — والخطأ كان يُفرِغ قائمة الاستثناء.

    الأثر كان على **المسار العربي**: عنوانٌ لاتينيّ لجهة اتصال (شارع/مدينة)
    بلا استثناء يصير «نثراً إنجليزياً» في تقريرٍ عربيّ، فتحجبه البوابة
    الحاجزة ويسقط التصدير — انحدارٌ في اللغة الافتراضية.
    """
    view = {"deep_research": {"importer_leads": {
        "path": "scraper", "note": "n",
        "leads": [{"name": "Al Noor Trading BV",
                   "address": "Damrak 12, Amsterdam"}]}}}
    allow = silk_i18n.entity_allowlist(view)
    assert "Al Noor Trading BV" in allow and "Damrak 12, Amsterdam" in allow
    line = "جهة الاتصال الأولى: Al Noor Trading BV — Damrak 12, Amsterdam."
    assert silk_i18n.foreign_prose_spans(line, "ar", allow) == []


def test_section_structure_check_uses_the_reports_own_language():
    """فحصُ البنية يقارن بقائمة **لغة التقرير** لا بالعربية دائماً.

    بدون ذلك كان كلُّ تقريرٍ إنجليزيّ سليم يُبلَّغ «الأحد عشر قسماً مفقودة»
    و`section_structure` في `FAIL_TRIGGER_CHECKS` — أي: لا تقرير إنجليزيّ
    يمرّ أبداً.
    """
    import silk_quality_gate as Q
    from silk_ai_judge import report_sections
    body = "\n\n".join(
        f"## {i}. {s}\nImports reached USD 8.4M in 2023 (UN Comtrade)."
        for i, s in enumerate(report_sections("en"), 1))
    out = Q.run_quality_gate({"report_language": "en", "deep_research": {
        "report": {"text": body}, "analyst": {},
        # الموجة B (البند T-01): دليلٌ واحدٌ مرصودٌ بمصدرٍ عموميّ — بلا أيّ
        # دليلٍ تُفشِل البوّابةُ عمداً، وهذا الاختبارُ سؤالُه لغةُ فحص البنية.
        "missions": {"trade_flow": {"findings": [
            {"value": 8400000, "source": "UN Comtrade", "confidence": 0.8,
             "note": "imports observed 2023"}]}}}})
    assert not [f for f in out["findings"]
                if f["check"] == "section_structure"], (
        "فحصُ البنية يقرأ قائمةً بلغةٍ أخرى")
    assert out["verdict"] != "FAIL"


def test_english_terms_never_trip_the_english_client_guard():
    """نصوصُنا الإنجليزية القالبية لا تحمل مفردةً يحظرها حارسُنا نفسه.

    قاعدةٌ بديهية يسهل خرقها: كتبتُ «in this run» في ثلاثة نصوص فحجبها
    الحارسُ — تقريرٌ لا يخرج بسبب نصٍّ كتبناه نحن.
    """
    from silk_reports import _client_forbidden_hits
    offenders = {k: _client_forbidden_hits(v["en"], "en")
                 for k, v in silk_i18n.TERMS.items()
                 if _client_forbidden_hits(v["en"], "en")}
    assert not offenders, f"نصوصٌ إنجليزية يحظرها الحارس: {offenders}"


def test_quality_gate_declares_every_arabic_only_check_as_skipped():
    """كلُّ فحصٍ عربيِّ الأنماط يُعلَن مُتخطّى على الإنجليزية — لا PASS صامت.

    بوابةٌ نصفُها خامدٌ تُصدِر PASS يُقرأ «فُحِص ونجح» — ادّعاءُ جودةٍ لم
    تُقَس، وهو عينُ ما يمنعه عقدُ عدم الاختلاق.
    """
    import silk_quality_gate as Q
    out = Q.run_quality_gate({"report_language": "en", "deep_research": {
        "report": {"text": _writer_text_en()}, "missions": {}, "analyst": {}}})
    declared = {s["check"] for s in out["skipped_checks"]}
    for check, _reason in Q._AR_ONLY_CHECKS:
        assert check in declared, f"فحصٌ خامدٌ بلا إعلان: {check}"
    assert all(s.get("reason") for s in out["skipped_checks"])

