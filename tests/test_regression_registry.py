"""سجلّ الانحدار الموحّد — one guard per real incident, one meta-test for coverage.

> **الغرض (أمر المُشرِف).** لكل حادثة إنتاجية حقيقية في هذا المستودع — صفوف
> `docs/LESSONS.md` **وفخاخ** `silk-operations` §2 (THE TRAPS) — حارسٌ واحد
> يُفشِل على عودة نفس العائلة، و**اختبار تغطية شامل** (meta) يثبت أنّ كل حادثة
> مُسجَّلة هنا فعلاً — فلا تسقط حادثة من الشبكة بصمت. يشمل ذلك **الحوادث الثلاث
> لعطل 501 في تصدير docx** (صفوف LESSONS ٣/١١/١٣) بحُرّاس سلوكيين فعليين.
>
> **Why a registry (not just per-file lock-tests).** Lock-tests live scattered
> across `tests/`; this file is the single index that maps EVERY known incident
> to a live guard and then proves — mechanically — that the index is complete
> against both incident ledgers. A new incident that lands in either ledger
> without a registry entry fails `test_meta_registry_covers_every_known_incident`.

هرمتي بالكامل (قراءة مصدر + سلوك محلي، بلا شبكة). الحُرّاس السلوكية (٣/١١/١٣)
تبني/تنقّي فعلياً من المدوّنة القانونية الحقيقية الشكل — لا نماذج مثالية.

Run: python3 -m pytest tests/test_regression_registry.py -q
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

import pathlib
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))


def _read(rel: str) -> str:
    """اقرأ ملف مصدرٍ — و«api.py» تعني **طبقة الـAPI كاملةً**.

    البند ٧ (تدقيق 2026-08-27): جسم تشغيلة `/research` انتقل حرفياً إلى
    `silk_research_pipeline.py`. الحُرّاس هنا تسأل «هل الوصلة في مسار
    الطلب؟» لا «هل هي في هذا الملف؟» — فحدود الملفات تفصيلُ إعادة
    هيكلة، والوصلة هي العقد. راجع `tests/api_source.py`.
    """
    if rel == "api.py":
        from tests.api_source import api_layer
        return api_layer()
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _exists(rel: str) -> bool:
    return os.path.exists(os.path.join(_ROOT, rel))


def _needles(rel: str, *needles: str):
    """حارس وجود: كل إبرة حاضرة في الملف — يعيد callable للتسجيل."""
    def check():
        assert _exists(rel), f"ملف الإنفاذ مفقود: {rel}"
        src = _read(rel)
        missing = [n for n in needles if n not in src]
        assert not missing, f"{rel}: رموز/علامات إنفاذ مفقودة {missing}"
    return check


def _absent(rel: str, *forbidden: str):
    def check():
        src = _read(rel)
        present = [n for n in forbidden if n in src]
        assert not present, f"{rel}: رموز يجب أن تكون قد أُزيلت لا تزال {present}"
    return check


# ── حُرّاس سلوكية للحوادث الثلاث لعطل docx-501 (LESSONS ٣/١١/١٣) ──────────────

def _guard_docx501_row3():
    """LESSONS ٣ — 501 شُحن لأن الاختبارات نماذج مموّهة. الحارس: تصدير docx
    العميل يُنتِج ملفاً حقيقياً قابلاً للفتح من **المدوّنة القانونية الحقيقية
    الشكل** (لا نموذج)، بلا 501."""
    import silk_render
    from silk_reports import render_client_docx
    from canonical_netherlands import netherlands_research_blob
    view = silk_render.build_view(netherlands_research_blob())
    path = render_client_docx(view, os.path.join(tempfile.mkdtemp(), "c.docx"))
    assert os.path.exists(path)
    from docx import Document
    doc = Document(path)
    assert any(p.text.strip() for p in doc.paragraphs), "docx فارغ"


def _guard_docx501_row11():
    """LESSONS ١١ — 501 تكرّر لأن محفّزات الحارس العربية بلا استبدال مقابل.
    الحارس: مصطلح حكم عربي ممنوع («درجة الثقة») يُحيَّد فعلياً بمُطهِّر/منقِّي
    العميل فلا يبقى في مخرَج التصدير."""
    from silk_reports import _client_redact_text, _client_forbidden_hits
    leaked = "التقييم يعتمد درجة الثقة العالية على مصدر البيانات"
    cleaned = _client_redact_text(leaked)
    assert not _client_forbidden_hits(cleaned), (
        f"محفّز حارس عربي بقي بعد التنقية: {_client_forbidden_hits(cleaned)}")


def _guard_docx501_row13():
    """LESSONS ١٣ — docx يفشل حياً (501) بينما الهرمتي أخضر؛ الحارس كان يرفض
    على تسرّب واحد. القاعدة «نقِّ لا ترفض»: مصطلح إنجليزي عارٍ متسرّب يُستبدَل
    بمحايد ويُسلَّم المستند — لا 501. الحارس: `_client_redact_text` ينقّي
    مصطلحاً إنجليزياً تشغيلياً بدل رفعه."""
    from silk_reports import _client_redact_text, _client_forbidden_hits
    leaked = "mission status: successful run"
    assert _client_forbidden_hits(leaked), "التهيئة خاطئة — النص يجب أن يتسرّب أولاً"
    cleaned = _client_redact_text(leaked)
    assert not _client_forbidden_hits(cleaned), (
        f"مصطلح إنجليزي تشغيلي بقي بعد التنقية: {_client_forbidden_hits(cleaned)}")


# ── حُرّاس سلوكية لفخّي المسار (markets:[] + view بعد التخزين) ────────────────

def _guard_trap_markets_empty():
    """TRAP «markets:[] misroutes exporters» — نتيجة /research دوماً markets:[]؛
    أي مسار عرض يثق بـ`markets[0]` يحصل على {} فيُنتِج صفحة /analyze فارغة.
    الحارس: build_view للمدوّنة القانونية يُنتِج فرع deep_research (لا قالب
    فارغ) رغم markets:[]."""
    import silk_render
    from canonical_netherlands import netherlands_research_blob
    blob = netherlands_research_blob()
    assert blob["markets"] == [], "المدوّنة القانونية يجب أن تحمل markets:[]"
    view = silk_render.build_view(blob)
    assert view.get("deep_research"), "build_view لم يُنتِج فرع deep_research"


def _guard_trap_view_after_persist():
    """TRAP «view attached AFTER persist on one path» — البلوب المخزَّن قد لا
    يحمل view مشتقّاً؛ مسار القراءة يجب أن يعيد بناءه. الحارس: `GET /analyses/{id}`
    يبني view عند غيابه (`found["view"] = _view(found)`)."""
    src = _read("api.py")
    assert 'found["view"] = _view(found)' in src or 'found["view"]=_view(found)' in src, (
        "مسار /analyses/{id} لا يعيد بناء view الغائب")
    assert 'found.setdefault("analysis_id"' in src, (
        "مسار /analyses/{id} لا يضمن analysis_id للبلوبات الأقدم")


# ── حُرّاس تراب باقية (وجود رمز الإصلاح، file:line-anchored) ──────────────────

def _guard_trap_two_sanitizers():
    """TRAP «مُطهِّران مختلفان» — R8/TEST-4: كان وجودَ رمزٍ؛ صار **سلوكاً**: مطهِّرُ نصّ
    العميل يزيل السقالةَ التشغيلية، ومطهِّرُ العرض يحيّد ريبر `DataPoint` — وكلاهما
    يترك الجملةَ العربية السليمة كما هي (لا تطهيرَ يأكل المحتوى)."""
    import silk_render
    import silk_reports
    dirty = "أضف بطاقة منتجك (product_card) — DataPoint(value=None, source='x')"
    clean_view = silk_render._strip_internal_plumbing(dirty)
    assert "DataPoint(" not in clean_view, clean_view
    assert "أضف بطاقة منتجك" in clean_view, clean_view
    out = silk_reports._client_sanitize(dirty) if hasattr(silk_reports, "_client_sanitize") \
        else clean_view
    assert "product_card" not in out or "(product_card)" not in out, out
    assert callable(getattr(silk_reports, "_client_assert_clean", None))


def _guard_trap_redaction_mangling():
    """TRAP «التنقيحُ يُشوّه» — R8/TEST-4: حارسٌ سلوكيّ الآن. المنقِّحُ يخفي المفتاحَ
    ويُبقي الرسالةَ مقروءة (التشويهُ كان يبتلع النصّ حول المفتاح)، واسمُ مرحلة التصعيد
    ما زال طويلاً بما يكفي (`_escalate{attempt}`) فلا يُقصّ."""
    import silk_diagnostics
    msg = ("400 Client Error for url: https://comtradeapi.un.org/data/v1/get"
           "?subscription-key=SEKRET-abc123&cmdCode=080410 while fetching")
    out = silk_diagnostics._redact(msg)
    assert "SEKRET-abc123" not in out, out
    assert "400 Client Error" in out and "while fetching" in out, out
    _needles("silk_ai_judge.py", "_escalate{attempt}")()
    _absent("silk_ai_judge.py", "maxtok_retry")()


def _guard_trap_strip_plumbing_three_leaks():
    """TRAP «_strip_internal_plumbing leaked three raw forms» — الحارس يبني
    السلاسل الإنتاجية الحرفية الثلاث ويؤكّد تحييد كلٍّ منها (silk-operations §4:
    القفل بالسلسلة الحرفية). الثلاث: ريبر DataPoint(...) يُحيَّد كاملاً بلا
    نصف-ترجمة؛ JSON مضمَّن بمفاتيح score/summary يُحيَّد؛ رمز حكم بأي حالة أحرف."""
    from silk_render import _strip_internal_plumbing
    # (١) ريبر DataPoint(...) — كامل التحييد، لا نصف-ترجمة، تُستخرَج القيمة
    dp = ("مبنيّ على DataPoint(value='واردات 120 مليون دولار', source='UN "
          "Comtrade', confidence=0.9, note='n', retrieved_at='2026-07-01', "
          "status='')")
    o1 = _strip_internal_plumbing(dp)
    assert "DataPoint(" not in o1 and "confidence=" not in o1, o1
    assert "درجة الثقة=" not in o1, f"نصف-ترجمة: {o1}"
    assert "واردات 120 مليون دولار" in o1, o1
    # (٢) JSON مضمَّن بمفاتيح score/summary
    o2 = _strip_internal_plumbing('التوصية: {"score": 0.72, "summary": "سوق واعد"}')
    assert "{" not in o2 and '"summary"' not in o2, o2
    assert "سوق واعد" in o2, o2
    # (٣) رمز حكم بأي حالة أحرف
    o3 = _strip_internal_plumbing("الحكم go — مراقبة قبل الدخول")
    assert not re.search(r"\bgo\b", o3, re.I), f"رمز حكم خام بقي: {o3}"


def _guard_trap_parallel_cache_window():
    # فخّ معروف غير مُصلَح بعد (نافذة الذاكرة المؤقتة عبر ١٢ بعثة متوازية).
    # الحارس يُبقيه مُتتبَّعاً: آلية التوازي (ThreadPoolExecutor) لا تزال في
    # مُشغّل البعثات، والفخّ موسوم صراحةً «Known, not yet fixed» في المهارة.
    _needles("silk_missions.py", "ThreadPoolExecutor")()
    _needles(".claude/skills/silk-operations/SKILL.md", "not yet fixed")()


# كل مدخلة: Incident(key, source, match, check)
#   source: "LESSONS" (key=رقم الصفّ int) أو "trap" (key=slug، match=جزء من
#   اسم الفخّ العريض في §2). check: callable يُفشِل على عودة الانحدار.


def _guard_datapoint_repr_flexible():
    """LESSONS ١٧ — ريبر DataPoint المختصر/الشاذ كان يمرّ نصف مترجم (هجوم
    المشرف الحي). الحارس: النمط المرن + شبكة الأمان يمسكان كل العائلة."""
    import silk_render as _r
    cases = [
        "DataPoint(value=None, confidence=0.0)",
        "DataPoint(value='12.5', source='comtrade', confidence=0.9, "
        "note='ok (x)', retrieved_at='2026', status='ok')",
        "DataPoint(confidence=0.5, value=None)",
        "قبل DataPoint(value=None, confidence=0.0) بعد",
    ]
    for c in cases:
        out = _r._strip_internal_plumbing(c)
        assert "DataPoint" not in out and "confidence" not in out and \
               "درجة الثقة=" not in out, f"leak: {c!r} -> {out!r}"
    assert _r._strip_internal_plumbing(cases[1]).strip().startswith("12.5")


def _guard_vendor_name_leak():
    """LESSONS ١٨ — اسم مزوّد داخلي (Volza/Explee/…) تسرّب لسطح العميل (بلاغ
    UK الحي). الحارس السلوكي: الأسطر الحرفية المسرّبة (سطر «الخطوة التالية»
    القديم + ترجمة `silk_narrative` التي تُسمّي المزوّد) تُحيَّد فعلياً بمنقِّي
    العميل فلا يبقى اسم مزوّد في مخرَج التصدير؛ وسطر next_step المُولَّد لم
    يعُد يحمل اسم مزوّد أصلاً."""
    from silk_reports import (_client_redact_text, _client_forbidden_hits,
                              _client_sanitize)
    # (١) الأسطر الحرفية المسرّبة من البلاغ الحي — كلٌّ يتسرّب أولاً ثم يُحيَّد.
    leaked = [
        "فعّل خدمة التعميق المدفوعة للتحقق من المستوردين وجهات الاتصال (Volza/Explee)",
        "إكسبلي غير متاح حالياً",
        "فولزا: لا مستوردون بالاسم مرصودون لرمز 0804 في GBR",
        "buyers via Serper and SerpApi, priced by LocalPrice",
        "seasonality from pytrends; risk news from GDELT",
    ]
    for line in leaked:
        assert _client_forbidden_hits(line), (
            f"التهيئة خاطئة — يجب أن يتسرّب أولاً: {line!r}")
        cleaned = _client_redact_text(_client_sanitize(line))
        assert not _client_forbidden_hits(cleaned), (
            f"اسم مزوّد بقي بعد التنقية: {_client_forbidden_hits(cleaned)}")
    # (٢) الحارس الصارم يملك أسماء المزوّدين لاتينيةً وعربيةً معاً — لا يعتمد
    # على المُطهِّر وحده (متغيّر مستقبلي يفلت المُطهِّر يبقى يُرفَع بصوت عالٍ).
    for v in ("Volza", "Explee", "إكسبلي", "فولزا", "LocalPrice", "Serper",
              "SerpApi", "pytrends", "GDELT"):
        hits = _client_forbidden_hits(f"مبنيّ على {v} التجارية")
        assert any(h.startswith("vendor_name") for h in hits), (
            f"اسم مزوّد ليس في قائمة الرفض الصارم (_client_assert_clean): {v}")
    # (٣) سطر next_step المُولَّد لا يحمل اسم مزوّد إطلاقاً.
    import silk_render
    from canonical_netherlands import netherlands_research_blob
    blob = netherlands_research_blob()
    blob["deep_research"]["verdict"] = {"verdict": "GO", "confidence": 0.7,
                                        "ai": {"verdict": "GO"}}
    view = silk_render.build_view(blob)
    nxt = (view.get("deep_research") or {}).get("next_step") or ""
    assert nxt and not _client_forbidden_hits(nxt), (
        f"سطر الخطوة التالية يحمل اسم مزوّد: {nxt!r}")


def _guard_export_format_contract():
    """LESSONS ١٩ — عائلة export-format-contract (بلاغ المُشرِف عند السطر): زرّ
    «تصدير التقرير» الأساسي كان موصولاً بـ`dlReport("docx")` فينزّل Word بينما
    المُسلَّم النهائي للعميل PDF غير قابل للتحرير (§3، اتفاق المالك). الحارس:
    (١) زرّ PDF موصول بـ`dlReport("pdf")` لا docx؛ (٢) `dlReport` يملك فرع pdf
    بامتداد `.pdf` ورسالة 503 عربية صريحة؛ (٣) بطاقة الدردشة المصغّرة تُصدِّر
    PDF؛ (٤) الخادم يخدم report.pdf بنوع application/pdf؛ (٥) صورة النشر
    (Dockerfile) + وظيفة e2e تُثبّتان محرّك التحويل فلا يموت الزرّ حياً."""
    html = _read("web/index.html")
    # (١) الوصلة الأساسية: PDF لا docx (السطر المعطوب الأصلي غائب).
    assert '$("#pdfBtn").addEventListener("click",function(){dlReport("pdf")})' \
        in html, "زرّ PDF غير موصول بـdlReport(\"pdf\")"
    assert '$("#pdfBtn").addEventListener("click",function(){dlReport("docx")})' \
        not in html, "زرّ PDF لا يزال موصولاً بتنزيل docx (البلاغ الأصلي)"
    # زرّ Word ثانوي حاضر (النسخة القابلة للتحرير للمشغّل، لا العميل).
    assert 'id="wordBtn"' in html and \
        '$("#wordBtn").addEventListener("click",function(){dlReport("docx")})' \
        in html, "زرّ Word الثانوي غائب أو غير موصول"
    # (٢) فرع pdf في dlReport: امتداد .pdf + رسالة 503 العربية الصريحة.
    assert 'kind==="pdf"' in html, "dlReport بلا فرع pdf"
    assert '"سِلك_تقرير_"+id+".pdf"' in html, "اسم/امتداد ملف الـPDF خاطئ"
    assert "محرّك التحويل غير متاح — جرّب Word مؤقتاً" in html, \
        "رسالة 503 العربية الصريحة غائبة"
    assert "r.status===503" in html, "فرع pdf لا يعالج 503 صراحةً"
    # (٣) بطاقة الدردشة المصغّرة تُصدِّر PDF لا docx.
    assert 'data-act="pdf"' in html, "بطاقة الدردشة المصغّرة لا تُصدِّر PDF"
    assert 'this.dataset.act==="board"?nav("board"):dlReport("pdf")' in html, \
        "معالج بطاقة الدردشة لا يستدعي dlReport(\"pdf\")"
    # (٤) الخادم يخدم report.pdf بنوع application/pdf.
    api = _read("api.py")
    assert "/analyses/{analysis_id}/report.pdf" in api and \
        'media_type="application/pdf"' in api, "نقطة نهاية report.pdf غائبة/خاطئة"
    # (٥) محرّك التحويل مثبَّت على النشر (Dockerfile) وفي وظيفة e2e — كي يعمل
    # الزرّ حيّاً لا في CI فقط (البند ٦ من أمر العمل).
    dockerfile = _read("Dockerfile")
    assert "libreoffice-writer" in dockerfile, \
        "محرّك تحويل PDF غير مثبَّت في صورة النشر — الزرّ سيموت حياً بـ503"
    e2e = _read(".github/workflows/e2e-live-shape.yml")
    assert "libreoffice-writer" in e2e, \
        "وظيفة e2e لا تثبّت محرّك التحويل — تأكيد %PDF سيفشل"
    # التدفّق يؤكّد توقيع %PDF على المسار الأساسي.
    flow = _read("tests/e2e/live_shape_flow.cjs")
    assert 'pdfBuf[0] === 0x25 && pdfBuf[1] === 0x50' in flow, \
        "تدفّق e2e لا يؤكّد توقيع %PDF لزرّ PDF"


def _guard_world_tier2_no_fabrication():
    """LESSONS ٢٠ — عائلة tier2-fabrication (تصميم الميزة أ، قفل استباقي): توسيع
    الترتيب لكل دول العالم يجب ألّا يختلق قيمة فئة-٢ ولا يفجّر ميزانية كومتريد.
    الحارس (قراءة مصدر + سلوك حيّ): (١) وحدة الترتيب لا تقرأ أيّ CSV محلّي؛
    (٢) الفئة-٢ تحمل الوسم التعاقدي + فجوتَي موقع السعودية/المنافسة معلنتين؛
    (٣) نداء العالم الواحد + التدهور عند نفاد الميزانية موجودان؛ (٤) ملف القفل
    قائم."""
    src = _read("silk_market_ranker.py")
    # (١) لا CSV محلّي في وحدة الترتيب إطلاقاً.
    for forbidden in ("agreements_l1", "demographics_l1", "market_locale",
                      "muslim_share", "requirements_l1"):
        assert forbidden not in src, f"الترتيب يقرأ CSV محلّياً: {forbidden}"
    # (٢) الوسم التعاقدي + الفجوة المعلنة + المسجّل + الصمّام.
    for needle in ('TIER2_LABEL = "تغطية أساسية — بيانات محلية محدودة"',
                   'def _tier2_gather_row', 'status="tier2_gap"',
                   'def _world_markets_enabled', 'def world_import_totals',
                   'def _comtrade_budget_left'):
        assert needle in src, f"علامة إنفاذ الفئة-٢ مفقودة: {needle}"
    # (٣) نداء العالم الواحد (partner=0) مشترك للفئتين + تدهور الميزانية.
    assert 'flow="M", partner=0' in src, "نداء العالم الواحد (partner=0) غائب"
    assert '_comtrade_budget_left()' in src and '_WORLD_BUDGET_RESERVE' in src, \
        "فرع التدهور عند نفاد الميزانية غائب"
    # (٤) ملف القفل قائم بأقفاله السبعة.
    assert _exists("tests/test_world_coverage_tierA.py"), "ملف قفل الميزة أ مفقود"
    lock = _read("tests/test_world_coverage_tierA.py")
    for fn in ("test_tier_separation_and_labels",
               "test_tier2_never_carries_a_local_csv_value",
               "test_tier2_gather_makes_zero_comtrade_calls",
               "test_budget_exhausted_degrades_to_tier1_only",
               "test_ranking_is_deterministic_on_fixture"):
        assert f"def {fn}" in lock, f"قفل الميزة أ مفقود: {fn}"


def _guard_out_of_coverage_thin_study():
    """LESSONS ٢٢ — عائلة out-of-coverage-thin-study (مواصفة المالك، الميزة أ):
    سوقٌ خارج التغطية يجب ألّا يشغّل دراسةً هزيلة بل يُعاد برسالةٍ صادقة ويُسجَّل
    إشارةَ طلب. الحارس (قراءة مصدر): البوّابة + الرسالة الحرفية + التسجيل +
    تسطيح الواجهة + ملف القفل."""
    api = _read("api.py")
    assert "def _market_in_coverage" in api, "دالّة فحص التغطية غائبة"
    assert '"error": "out_of_coverage"' in api, "بوّابة خارج التغطية غائبة"
    assert "هذه السوق خارج التغطية الحالية" in api and \
        "تواصل معنا لإضافتها" in api, "الرسالة الصادقة الحرفية غائبة"
    assert '"out_of_coverage_demand"' in api, "تسجيل إشارة الطلب غائب"
    assert "_world_markets_enabled()" in api, "البوّابة غير مقيّدة بالصمّام"
    html = _read("web/index.html")
    assert "x.message||x.reason||x.error" in html, \
        "الواجهة لا تُسطّح رسالة detail (لن تظهر رسالة خارج التغطية)"
    assert _exists("tests/test_out_of_coverage_guard.py"), "ملف قفل البوّابة مفقود"
    lock = _read("tests/test_out_of_coverage_guard.py")
    for fn in ("test_out_of_coverage_market_returns_honest_message_and_logs_demand",
               "test_tier1_curated_market_is_always_covered",
               "test_flag_off_no_coverage_guard_any_country_works_todays_way"):
        assert f"def {fn}" in lock, f"قفل البوّابة مفقود: {fn}"


def _guard_intake_no_silent_guess():
    """LESSONS ٢١ — عائلة intake-silent-guess (تصميم الميزة ب، قفل استباقي):
    استقبال المنتج من صورة يجب ألّا يختلق اسماً ولا يبدأ تحليلاً قبل تأكيد
    المستخدم، والمحوّل أماميّ معزول عن طبقات التحليل. الحارس (قراءة مصدر):
    (١) عقد عدم الاختلاق (فرع readable/العتبة => تعذّر قراءة صادق)؛ (٢) حدود
    الصورة + التقييس + العزل؛ (٣) القياس (حجز واحد) في نقطة النهاية؛ (٤) المحوّل
    لا يستورد/يستدعي طبقات التحليل؛ (٥) ملف القفل قائم."""
    import ast as _ast
    src = _read("silk_product_intake.py")
    # (١) عقد عدم الاختلاق + الرسالة الموحّدة + العتبة.
    for needle in ('READ_FAILED_MSG = "تعذّرت القراءة — اكتب الاسم يدوياً"',
                   'def _read_failed', 'def intake_image', 'readable',
                   '_MIN_CONFIDENCE', 'def enabled'):
        assert needle in src, f"علامة إنفاذ الاستقبال مفقودة: {needle}"
    # (٢) حدود الصورة + التقييس + العزل.
    for needle in ('MAX_IMAGE_BYTES', 'ALLOWED_MEDIA_TYPES', 'def _decode_and_check',
                   'def _sanitize', 'def _isolate', '_MAGIC'):
        assert needle in src, f"علامة سلامة الصورة مفقودة: {needle}"
    # (٣) القياس — نقطة النهاية تحجز تفعيلة واحدة كأيّ نداء مدفوع.
    api = _read("api.py")
    assert 'def _intake_vision_allowed' in api and \
        'try_reserve_paid_calls(1)' in api, "قياس نداء الرؤية غائب"
    assert '@app.post("/products/intake")' in api, "نقطة نهاية الاستقبال غائبة"
    assert 'intake.enabled()' in api, "صمّام SILK_IMAGE_INTAKE غير مفحوص"
    # (٤) المحوّل أماميّ معزول — لا يستورد أيّ طبقة تحليل، ولا يستدعيها نصّاً.
    tree = _ast.parse(src)
    imported = {n.names[0].name.split(".")[0] for n in _ast.walk(tree)
                if isinstance(n, _ast.Import)}
    imported |= {(n.module or "").split(".")[0] for n in _ast.walk(tree)
                 if isinstance(n, _ast.ImportFrom)}
    forbidden = {"silk_engine", "silk_missions", "silk_market_analyst",
                 "silk_ai_judge", "silk_market_ranker", "correlation",
                 "silk_synthesis", "silk_llm_runtime"}
    assert imported.isdisjoint(forbidden), imported & forbidden
    for banned in ("analyze(", "deep_research(", "write_reviewed_report",
                   "ResearchManager", "rank_markets("):
        assert banned not in src, f"الاستقبال يمسّ مسار التحليل: {banned}"
    # (٥ب) **سلوكيّ** (R8/TEST-4): صورةٌ غيرُ مقروءة ⇒ «تعذّرت القراءة» لا اسمٌ مختلَق.
    import silk_product_intake as _intake
    _bad = _intake.intake_image("bm90LWFuLWltYWdl", "image/png", "product",
                                allow_vision=False, blocked_reason="اختبار")
    assert _bad.get("ok") is False, _bad
    assert _bad.get("status") in ("read_failed", "invalid_image"), _bad
    assert not (_bad.get("name") or "").strip(), _bad
    # (٥) ملف القفل قائم بأقفاله المركزية.
    assert _exists("tests/test_product_intake_featureB.py"), "ملف قفل الميزة ب مفقود"
    lock = _read("tests/test_product_intake_featureB.py")
    for fn in ("test_low_confidence_or_unreadable_never_fabricates",
               "test_intake_module_imports_no_pipeline_code",
               "test_endpoint_image_call_is_metered_from_the_cap",
               "test_image_validation_rejects_bad_inputs"):
        assert f"def {fn}" in lock, f"قفل الميزة ب مفقود: {fn}"


def _guard_unresolved_hs_silent_spend():
    """LESSONS ٢٣ — حادثة الفيتوتشيني: دراسةٌ مدفوعةٌ بدأت برمز HS غير محسوم.
    الحارس السلوكي: (١) المُصنِّف لا يختلق (منتجٌ مجهول => منتقٍ يدوي، hs6=None،
    ثقة 0.0)؛ (٢) `_validate` يرفض فصلًا مستبعَدًا وما ليس رمزًا (عقد عدم اختلاق)؛
    (٣) بوّابة `unresolved_hs` موجودةٌ وتسبق حجز الدولار في `/research`."""
    import silk_hs_classifier as hsc
    out = hsc.classify("qwxzptvbmzzz منتج لا وجود له", allow_claude=False)
    assert out["hs6"] is None and out["status"] == "manual" and \
        out["confidence"] == 0.0, out
    assert hsc._validate({"hs6": "270900", "confidence": 0.9}) is None  # فصل ٢٧
    assert hsc._validate({"hs6": "زائف", "confidence": 0.9}) is None    # ليس رمزًا
    api = _read("api.py")
    assert "def _require_hs6" in api and '"error": "unresolved_hs"' in api, \
        "بوّابة hs6 الصلبة غائبة"
    assert "def classify_hs" in api and "def _classify_general_allow_claude" in api, \
        "نقطة/حارس التصنيف غائبة"
    gate = api.index('"error": "unresolved_hs"')
    reserve = api.index("try_reserve_usd(_expected_usd)")
    assert gate < reserve, "بوّابة hs6 يجب أن تسبق حجز الدولار (لا إنفاق على رمز مجهول)"


def _guard_hardcoded_product_rule():
    """LESSONS ٢٤ — الحارسان (مُصنِّف HS + استشارة بلد المنشأ) قاعدتان مبنيّتان
    على البيانات لا حالتا منتج (نفس عائلة «التمور السعودية»). الحارس: (١) منطقهما
    يخلو من أيّ منتج/ISO/HS من العيّنات، والعتبة config-driven؛ (٢) سلوكيًا القاعدة
    تُعمَّم من ترتيب البيانات — عيّنةٌ مُرقَّعةٌ صناعيّةٌ تُطلق/تصمت بالعتبة."""
    import inspect
    import unittest.mock as _mock
    import silk_hs_classifier as hsc
    import silk_market_ranker as ranker
    blob = inspect.getsource(hsc)
    for fn in (ranker.world_export_totals, ranker.top_world_exporters,
               ranker.is_top_world_exporter, ranker._producer_advisory_topn):
        blob += "\n" + inspect.getsource(fn)
    for tok in ("معكرونة", "pasta", "fettuccine", "تمور", "dates", "olive",
                "عسل", "honey", "ITA", "ESP", "GBR", "ARE",
                "190219", "150910", "080410", "040900"):
        if tok.isascii():
            assert not re.search(r"(?<![A-Za-z0-9])" + re.escape(tok)
                                 + r"(?![A-Za-z0-9])", blob), \
                f"ترميزٌ صلبٌ في منطق الحارس: {tok}"
        else:
            assert tok not in blob, f"ترميزٌ صلبٌ في منطق الحارس: {tok}"
    assert "SILK_PRODUCER_ADVISORY_TOPN" in blob, "العتبة ليست config-driven"

    # سلوكي: القاعدة من البيانات — رموزٌ صناعيّةٌ بحتة (لا اسم حقيقي).
    def _fake(hs_code, year):
        return [{"iso3": c, "m49": "0", "total_usd": 9 - i}
                for i, c in enumerate(["XXA", "XXB", "XXC"])]
    with _mock.patch.object(ranker, "world_export_totals", side_effect=_fake):
        top, _l = ranker.is_top_world_exporter("AAAAAA", "XXA", 2023, 2)
        bot, _l2 = ranker.is_top_world_exporter("AAAAAA", "XXC", 2023, 2)
    assert top is True and bot is False, "القاعدة لا تتبع ترتيب البيانات"


def _guard_g41_domestic_production():
    """LESSONS ٦٤ — حارسُ المعقولية يقرأ الإنتاجَ المحليّ من البروفايل
    (DEF-1/G4.1). الحارس: (١) سوقٌ مُنتِجة (نيجيريا) لا تُوسَم؛ (٢) قطر (لا
    إنتاجٍ محلّيّ) تبقى مضبوطة (لا انحدار)؛ (٣) الإعفاءُ مرئيٌّ في المانيفست
    («guard_relaxed_domestic_producer») لا صامت."""
    import silk_plausibility as P

    def _blob(iso3, market_usd, imports_usd):
        return {"market": {"iso3": iso3}, "hs_code": "200811",
                "deep_research": {"missions": {"m": {"findings": [
                    {"value": imports_usd, "source": "UN Comtrade",
                     "note": f"إجمالي استيراد {iso3} من العالم"},
                    {"value": market_usd, "source": "ويب",
                     "note": "حجم السوق الكامل"}]}}}}

    nga = _blob("NGA", "497 مليون دولار", "7,000,000 دولار")
    assert P.check_magnitudes(nga) == [], "سوقٌ مُنتِجة (نيجيريا) وُسِمت زوراً"
    P.annotate(nga)
    exempt = (nga.get("deep_research") or {}).get("plausibility_exemptions")
    assert exempt and exempt[0].get("kind") == "guard_relaxed_domestic_producer", \
        "الإعفاءُ يجب أن يُسجَّل في المانيفست (لا صامت)"
    qat = _blob("QAT", "497 مليون دولار", "7,000,000 دولار")
    assert P.check_magnitudes(qat), "قطر (لا إنتاج) يجب أن تبقى مضبوطة — انحدار!"


def _guard_bloc_list_single_source():
    """LESSONS ٦٣ — عضويةُ الكتلة التجارية من مصدرٍ واحدٍ لا تتشعّب (DEF-2).
    الحارس: (١) `silk_blocs.EU27` كاملةٌ ٢٧؛ (٢) كلُّ مستهلكٍ هو الكائنُ نفسُه
    بالهُويّة (`is`) فلا نسخةَ قد تسقط أعضاءً؛ (٣) لا مستهلكٍ يُعيد تعريفَ مجموعةٍ
    خامّ (يستورد المصدرَ الواحد)؛ (٤) سلوكيًا عضوٌ كان غائباً (المجر) ينال الطبقةَ
    الكاملة ويطابق بندَ EU."""
    import inspect
    import silk_blocs
    import silk_requirements_agent as reqs
    import silk_tariffs_agent as tariffs
    import silk_eurostat_agent as euro

    assert len(silk_blocs.EU27) == 27, "EU27 ليست ٢٧ عضواً"
    for iso in ("HUN", "ROU", "BGR", "HRV", "CYP", "EST",
                "LVA", "LTU", "LUX", "MLT", "SVK", "SVN"):
        assert iso in silk_blocs.EU27, f"عضوٌ غائبٌ عن EU27: {iso}"

    assert reqs._EU is silk_blocs.EU27, "الاشتراطات لا تشير للمصدر الواحد"
    assert tariffs._EU_ISO3 is silk_blocs.EU27, "التعريفة لا تشير للمصدر الواحد"
    assert reqs._GCC is silk_blocs.GCC and tariffs._GCC_MEMBERS is silk_blocs.GCC
    assert euro.EU_EFTA_MARKETS == silk_blocs.EU27 | silk_blocs.EFTA

    for mod in (reqs, tariffs, euro):
        assert "silk_blocs" in inspect.getsource(mod), \
            f"{mod.__name__} لا يستورد المصدر الواحد"

    # سلوكي: المجر (كانت غائبةً) تنال «مقنّن بالكامل» وتطابق بندَ EU.
    tier, _n = reqs.codification_tier("HUN")
    assert tier == "مقنّن بالكامل", "المجر سقطت للطبقة الجزئية"
    eu_row = {"market": "EU", "category": "all", "direction": "import"}
    assert reqs._matches(eu_row, "HUN", "all", "import", animal=False)


def _guard_wrong_direction_study():
    """LESSONS ٢٥ — عائلة wrong-direction-study (Wave 1.5، A): استشارةُ بلد
    المنشأ تُعمَّم لأشقّائها. الحارس السلوكي: (١) تصدير إلى بلد المنشأ نفسه =>
    self_origin (config-driven عبر env)؛ (٢) فصلٌ مقيَّد من مرجع المالك؛
    (٣) البوّابة في api؛ (٤) صفر ISO/HS مكتوب صلبًا في منطق المطابقة."""
    import silk_prerun as sp
    import os as _os
    old = _os.environ.get("SILK_ORIGIN_ISO3")
    _os.environ["SILK_ORIGIN_ISO3"] = "SAU"
    try:
        assert any(a["kind"] == "self_origin"
                   for a in sp.sibling_advisories("080410", "SAU"))
        assert not any(a["kind"] == "self_origin"
                       for a in sp.sibling_advisories("080410", "ITA"))
    finally:
        if old is None:
            _os.environ.pop("SILK_ORIGIN_ISO3", None)
        else:
            _os.environ["SILK_ORIGIN_ISO3"] = old
    # فصلٌ مقيَّد من المرجع (خنزير في سوقٍ خليجية) — عضوٌ من العائلة.
    assert any(a["kind"] == "restricted_chapter"
               for a in sp.sibling_advisories("020329", "SAU"))
    api = _read("api.py")
    assert '"error": "prerun_advisory"' in api and "advisories_ack" in api, \
        "بوّابة أشقّاء الاستشارة غائبة"
    # صفر رمز HS/دولة مكتوب صلبًا في منطق المطابقة.
    import inspect
    blob = "\n".join(inspect.getsource(fn) for fn in (
        sp.sibling_advisories, sp._restricted_hits))
    assert not re.search(r"(?<!\d)\d{4,6}(?!\d)", blob), "رمز HS صلب في المطابقة"
    assert not re.search(r'"[A-Z]{3}"', blob), "رمز دولة صلب في المطابقة"


def _guard_silent_external_failure():
    """LESSONS ٢٦ — عائلة silent-external-failure (Wave 1.5، C): فشلُ خدمةٍ
    خارجية مُهيَّأة يُعلَن للمشغّل. الحارس السلوكي: (١) record_service_failure
    يكتب صفَّ service_failure؛ (٢) المكشطة تُعلِن فشلها؛ (٣) جدول التدقيق قائم."""
    import silk_ops_log
    import tempfile as _tf
    import unittest.mock as _mock
    with _tf.TemporaryDirectory() as td:
        path = os.path.join(td, "ops.db")
        with _mock.patch.object(silk_ops_log, "_db_path", lambda: path):
            silk_ops_log.record_service_failure("comtrade", "429 rate limited")
            rows = silk_ops_log.last_errors(5, path)
    assert rows and rows[0]["kind"] == "service_failure" and \
        rows[0]["context"]["service"] == "comtrade"
    assert "record_service_failure" in _read("silk_gmaps.py"), \
        "المكشطة لا تُعلِن فشلها للمشغّل"
    assert _exists("docs/EXTERNAL_SERVICES_FAILURE_AUDIT.md"), "جدول التدقيق مفقود"


def _guard_readiness_before_spend():
    """LESSONS ٢٧ — عائلة spend-before-knowing (Wave 1.5، D): لوحةُ الجاهزية
    تعرض كلَّ تدهورٍ قبل الحجز. الحارس: نقطة `/research/readiness` + المُركِّب
    `_readiness_checks` (مع can_run/blocking) قائمان، والصمّام config-driven."""
    api = _read("api.py")
    assert "def _readiness_checks" in api and "def research_readiness" in api, \
        "لوحة الجاهزية (نقطة/مُركِّب) غائبة"
    assert '"/research/readiness"' in api and '"can_run"' in api and \
        '"blocking"' in api, "عقد لوحة الجاهزية غير مكتمل"
    import silk_prerun
    assert hasattr(silk_prerun, "advisories_enabled")


def _guard_leads_table_hygiene():
    """LESSONS ٢٨ — عنقود أوّل PDF: جدولُ روابط العميل نُقِّي عند الحدّ. الحارس
    السلوكي على المدوّنة القانونية (فيتوتشيني): جغرافيا خاطئة/نثر/حشو تُسقَط،
    الصالح يبقى، وسطر الإخلاء بارامتري بالمنتج (لا «التمور السعودية»)."""
    import silk_render
    import silk_reports
    from canonical_fettuccine import fettuccine_research_blob
    md = silk_reports.render_markdown(
        silk_render.build_view(fettuccine_research_blob()))
    seg = md[md.find("قائمة مستوردين"):]
    assert "Pastificio Milano" in seg          # صالح — يبقى
    assert "NutsWorld" not in seg              # جغرافيا أمريكية — يُسقَط
    assert "Italy imports a significant" not in seg   # نثر — يُسقَط
    assert "Anonimo Distribuzione" not in seg  # حشو — يُسقَط
    assert "فيتوتشيني" in seg and "التمور السعودية" not in md


def _guard_report_arabic_shape_a4():
    """LESSONS ٢٩ — العلامة «سِلك» كُسِرت «ِس لك» + الصفحة Letter لا A4. الحارس
    السلوكي: docx يحوي «سلك» متّصلة بلا كسرة، بمقاس A4 (210×297مم)."""
    import silk_render
    import silk_reports
    from canonical_fettuccine import fettuccine_research_blob
    import tempfile
    from docx import Document
    view = silk_render.build_view(fettuccine_research_blob())
    path = silk_reports.render_client_docx(
        view, os.path.join(tempfile.mkdtemp(), "r.docx"))
    doc = Document(path)
    txt = "\n".join(p.text for p in doc.paragraphs)
    for s in doc.sections:
        for hf in (s.header, s.footer):
            txt += "\n" + "\n".join(p.text for p in hf.paragraphs)
    assert "سلك" in txt and "سِلك" not in txt, "العلامة غير آمنة التشكيل"
    sec = doc.sections[0]
    assert abs(sec.page_width.mm - 210) < 1 and abs(sec.page_height.mm - 297) < 1, \
        "الصفحة ليست A4"


def _guard_client_template_no_hardcoded_product():
    """LESSONS ٣٠ — «التمور السعودية» كانت مثبَّتةً في تقرير أيّ منتج (عائلة
    hardcoded-product-rule موسَّعة للقوالب). الحارس: سطر الإخلاء بارامتري بالمنتج
    ولا يحمل اسم منتجٍ مثبَّت."""
    import inspect
    from silk_gmaps import maps_disclaimer, MAPS_DISCLAIMER
    src = inspect.getsource(maps_disclaimer)
    for tok in ("التمور", "dates", "معكرونة", "pasta"):
        assert tok not in src, f"اسم منتجٍ مثبَّت في سطر الإخلاء: {tok}"
    assert "التمور" not in MAPS_DISCLAIMER
    assert "عسل" in maps_disclaimer("عسل")   # يُشتَقّ من المنتج فعلًا


def _guard_analyze_persist_canonical_db():
    """LESSONS ٣١ — نتائج /analyze لم تكن محفوظةً في القاعدة القانونية: المحرّك
    ثبّت `db_path="data/silk.db"` النسبيّ فكتب لقرصٍ لا يقرأ منه أحد (المعرّف «1»
    ثم 404). الحارس السلوكي: مع SILK_DATA_DIR مضبوطًا، `analyze(persist=True)`
    يكتب لقاعدة `_db_path()` نفسها التي يقرأ منها `get_analysis` (بمسار افتراضي)."""
    import importlib
    tmp = tempfile.mkdtemp()
    saved = {k: os.environ.get(k) for k in ("SILK_DATA_DIR", "SILK_DB")}
    try:
        os.environ["SILK_DATA_DIR"] = tmp
        os.environ.pop("SILK_DB", None)
        import silk_engine
        import silk_storage
        importlib.reload(silk_storage)
        importlib.reload(silk_engine)
        # لا شبكة: المحرّك يتدهور لفجوات معلنة لكن الصفّ يُحفَظ ويُقرَأ.
        import unittest.mock as M
        with M.patch("requests.get", side_effect=OSError("blocked")), \
             M.patch("requests.post", side_effect=OSError("blocked")), \
             M.patch("requests.sessions.Session.request", side_effect=OSError("blocked")):
            result = silk_engine.analyze("شاي أخضر", persist=True)
        aid = result.get("analysis_id")
        assert aid is not None, "لم يُرفَق analysis_id رغم persist=True"
        assert silk_storage._db_path() == os.path.join(tmp, "silk.db")
        found = silk_storage.get_analysis(aid)   # path=None → _db_path()
        assert found is not None and found.get("product") == "شاي أخضر", (
            "الصفّ غير موجود في القاعدة القانونية — الجذر: كُتب لقرصٍ نسبيّ آخر")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import silk_storage
        importlib.reload(silk_storage)


def _guard_new_source_contracts():
    """LESSONS ٣٢ — مصدرٌ جديد = نفس العقود (فجوة معلنة/ops/مخزَّن/محكوم/نظيف
    الشروط). الحارس السلوكي: (أ) IMF/WTO دون الشبكة => فجوة معلنة None/0.0 لا
    اختلاق؛ (ب) WTO بلا مفتاح => فجوة معلنة بصفر نداء شبكة؛ (ج) سلسلة التراجع
    كلا-الفشلين تُبقي مصدر WITS؛ (د) البوّابة العربية للبنك الدولي تطابق تامّ
    (لا تُحوِّل WITS)؛ (هـ) كل نطاق مُفضَّل بعثته تملك web_search (لا إعداد ميت)."""
    from unittest.mock import patch
    import silk_imf_agent as imf
    import silk_wto_tariff as wto
    import silk_tariffs_agent as tar
    import silk_missions as M
    from silk_data_layer import DataPoint, public_source_url, WORLD_BANK_AR_PORTAL

    # (أ) لا اختلاق دون الشبكة
    with patch("silk_cache.cached_get", return_value=None):
        assert imf.imf_indicator("NLD", "gdp_growth").value is None
    # (ب) WTO بلا مفتاح => صفر نداء شبكة
    saved = {k: os.environ.get(k) for k in ("WTO_TTD_API_KEY", "WTO_API_KEY")}
    try:
        os.environ.pop("WTO_TTD_API_KEY", None)
        os.environ.pop("WTO_API_KEY", None)
        with patch("silk_cache.cached_get") as cg:
            dp = wto.wto_applied_tariff("080410", "NLD")
        cg.assert_not_called()
        assert dp.value is None
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    # (ج) سلسلة التراجع: كلا الفشلين => مصدر WITS يبقى
    with patch("silk_wto_tariff.wto_applied_tariff",
               return_value=DataPoint(None, "WTO TTD", 0.0, "x")), \
         patch("silk_tariffs_agent.applied_tariff",
               return_value=DataPoint(None, "World Bank WITS", 0.0, "y")):
        dp = tar.tariff_with_fallback("080410", "NLD")
    assert dp.value is None and dp.source == "World Bank WITS"
    # (د) البوّابة العربية للعميل: تطابق تامّ، WITS لا يُحوَّل
    assert public_source_url("World Bank", arabic=True) == WORLD_BANK_AR_PORTAL
    assert public_source_url("World Bank WITS", arabic=True) != WORLD_BANK_AR_PORTAL
    assert public_source_url("World Bank") == "https://data.worldbank.org/"
    # (هـ) لا نطاق مُفضَّل بعثته بلا web_search
    for key in M.PREFERRED_DOMAINS:
        assert "web_search" in M.MISSIONS[key]["allowed_tools"]


def _guard_report_quality_upgrade():
    """LESSONS ٣٢ — إصلاحُ المحرّك لا تحرير التقرير (تدقيق زبدة الفول السوداني/
    اليمن): كل عائلة عيبٍ تحريريّ صارت إنفاذًا حتميًّا. الحارس السلوكي على
    مدوّنة اليمن الإنتاجية الشكل: (١) عقد التأكيد يُعلِّم الرمز الخاطئ ولا
    يُعلِّم الصحيح؛ (٢) الرمز المُعلَّم يُعيد التأطير بملاحظةٍ واحدة + يسقف
    الثقة؛ (٣) شرطا قلب الحكم حقلان مهيكلان."""
    import silk_render as R
    from silk_hs_confirm import confirm_hs, is_flagged, CONTEXTUAL_TAG
    from tools.canonical_yemen import yemen_research_blob
    # (١) عقد التأكيد: الصفة المميّزة لا تخسر أمام كلمة ثانوية عارية.
    assert is_flagged(confirm_hs("زبدة الفول السوداني", "040510"))
    assert confirm_hs("تمور", "080410")["confirmed"] is not False
    # (٢) التأطير + سقف الثقة على المدوّنة، بملاحظةٍ واحدة (لا تكرار).
    dr = R.build_view(yemen_research_blob())["deep_research"]
    assert dr["hs_flagged"] is True
    assert dr["verdict"]["confidence"] <= 0.5
    assert sum(1 for l in dr["limits"] if CONTEXTUAL_TAG in l) == 1
    # (٣) شرطا قلب الحكم المهيكلان (حكم مراقبة).
    assert len(dr["flip_conditions"]) == 2
    assert all(c.get("closes_via") for c in dr["flip_conditions"])


def _guard_parse_provenance_not_prose():
    """LESSONS ٣٣ — حلِّل المصدر لا النثر: قاعدةُ إفصاح التقادُم تُرسى إلى
    بياناتٍ بنيوية. الحارس السلوكي: (١) `fact_year` يقرأ الوسم البنيويّ
    `year=YYYY`/`retrieved_at`؛ (٢) حقيقةٌ متقادِمة تُوسَم بأيّ صياغة؛
    (٣) رمز HS 2008 بلا حقيقة خلفه لا يُوسَم؛ (٤) «الطعام 2013» بلا حقيقة لا
    يُوسَم (لا false-positive نثريّ)."""
    import silk_render as R
    from silk_staleness import fact_year, stale_fact_years, is_stale_fact
    # (١) المصدر البنيويّ.
    assert fact_year({"value": 1, "note": "x year=2013", "retrieved_at": "2026"}) == 2013
    assert fact_year({"value": 1, "retrieved_at": "2018-12-31"}) == 2018
    assert not is_stale_fact({"value": 1, "retrieved_at": "2026-01-01"})
    # (٢) الوسم مستقلّ عن الصياغة.
    for s in ["في 2013 بلغ الدخل.", "عام 2013م.", "الدخل 2013 منخفض."]:
        assert R._STALE_TAG in R._tag_stale_years(s, {2013}), s
    # (٣) رمز HS 2008 لا يُوسَم (ليس سنة حقيقة، وليس في القائمة).
    assert R._STALE_TAG not in R._tag_stale_years("البند 2008 للمحضرات.", {2013})
    # (٤) «الطعام 2013» بلا حقيقة متقادِمة => بلا وسم (لا مطابقة داخل كلمة).
    assert R._STALE_TAG not in R._tag_stale_years("استهلاك الطعام 2013.", set())
    # (٥) القائمة تُشتَقّ من حقائق اليمن (2013/2018).
    from tools.canonical_yemen import yemen_research_blob
    ms = yemen_research_blob()["deep_research"]["missions"]
    allf = [f for v in ms.values() for f in v["findings"]]
    assert stale_fact_years(allf) == {2013, 2018}


def _guard_hs_gate_shared_choke_point_fail_safe():
    """LESSONS ٣٥ — تقرير الكويت الحيّ (زبدة الفول السوداني، 2026-07-21):
    بوّابة تأكيد HS كانت موصولة بـ/research وحده خلف صمّامٍ مُطفأ افتراضياً.
    الحارس السلوكي: (١) `gate_enabled` فشل-آمن — مفعّلة بلا أيّ متغيّر env؛
    (٢) `preflight_block` نقطة اختناق واحدة تحجب رمزاً غير مؤكَّد؛ (٣) كلا
    معالجَي `/analyze` و`/research` في api.py يستدعيانها فعلياً (لا نسخة
    مكرَّرة/مسار واحد فقط)."""
    import silk_hs_confirm as C
    saved = os.environ.pop("SILK_HS_CONFIRM_GATE", None)
    try:
        # (١) فشل-آمن: بلا أيّ ضبط => مفعّلة.
        assert C.gate_enabled() is True
        # إطفاءٌ صريح فقط يُعطّلها.
        os.environ["SILK_HS_CONFIRM_GATE"] = "0"
        assert C.gate_enabled() is False
        os.environ["SILK_HS_CONFIRM_GATE"] = "1"
        assert C.gate_enabled() is True
        del os.environ["SILK_HS_CONFIRM_GATE"]
        # (٢) نقطة الاختناق تحجب فعلياً — نفس عيّنة الحادثة الحية.
        blocked = C.preflight_block("زبدة الفول السوداني", "040510")
        assert blocked is not None and blocked["error"] == "hs_confirmation_needed"
        assert C.preflight_block("زبدة الفول السوداني", "040510",
                                 hs_confirmed=True) is None
    finally:
        if saved is None:
            os.environ.pop("SILK_HS_CONFIRM_GATE", None)
        else:
            os.environ["SILK_HS_CONFIRM_GATE"] = saved
    # (٣) كلا المعالجَين يستدعيان نقطةَ الاختناق — لا مسارٌ واحد فقط.
    # يُحتسَب الغلافُ `preflight_resolve` (البوّابة + قياسُ السمة الرقمية،
    # LESSONS ٦٥) لأنه **يستدعي `preflight_block` نفسها** لا يستبدلها —
    # وهذا مُتحقَّقٌ منه بنيوياً أدناه كي لا ينحرف الغلافُ لبوّابةٍ موازية.
    api_src = _read("api.py")
    calls = (api_src.count("preflight_block(")
             + api_src.count("preflight_resolve("))
    assert calls >= 2, (
        "نقطةُ اختناق البوّابة يجب أن تُستدعى من كلا /analyze و/research")
    import inspect
    wrapper = inspect.getsource(C.preflight_resolve)
    assert "preflight_block(" in wrapper, (
        "preflight_resolve لا يستدعي preflight_block — بوّابةٌ موازية")


def _guard_cross_market_checkpoint_leak():
    """LESSONS ٣٦ — تسرّب اليمن↔الكويت: نقاط تفتيش بعثات `/research` كانت
    تُقرأ بمفتاح analysis_id فقط بلا عمود سوق، واستئنافٌ بسوقٍ مختلف يُعيد
    استهلاكها بصمت. الحارس السلوكي: (١) نقطة تفتيش مختومة بسوقٍ (اليمن) لا
    تُعاد لطلبٍ بسوقٍ آخر (الكويت)؛ (٢) صفوفٌ قديمة بلا ختم لا تُحجَب؛
    (٣) بوّابة `/research`'s resume_market_mismatch (٤٠٩) موجودة في api.py
    **قبل** فرع «مكتملة => أعِدها كما هي» (لا إرجاعٌ صامتٌ يتجاهل الطلب)."""
    import silk_storage
    from silk_agents import AgentReport
    import tempfile as _tf
    db = os.path.join(_tf.mkdtemp(), "silk.db")
    yemen_report = AgentReport(agent_name="x", findings=[], failed=False,
                               summary="سوق عدن المركزي / ربوع")
    silk_storage.save_mission_checkpoint(1, "consumer_culture", yemen_report,
                                         path=db, market_iso3="YEM")
    # (١) طلبٌ بسوق آخر لا يستلم الصفّ.
    assert "consumer_culture" not in silk_storage.load_mission_checkpoints(
        1, path=db, market_iso3="KWT")
    assert "consumer_culture" in silk_storage.load_mission_checkpoints(
        1, path=db, market_iso3="YEM")
    # (٢) صفٌّ قديم بلا ختم (market_iso3=None) لا يُحجَب.
    old_report = AgentReport(agent_name="y", findings=[], failed=False, summary="s")
    silk_storage.save_mission_checkpoint(2, "tradeflow", old_report, path=db)
    assert "tradeflow" in silk_storage.load_mission_checkpoints(
        2, path=db, market_iso3="KWT")
    # (٣) بوّابة API تسبق فرع الإعادة الصامتة لتشغيلةٍ مكتملة.
    api_src = _read("api.py")
    assert "resume_market_mismatch" in api_src
    gate_idx = api_src.index("resume_market_mismatch")
    completed_shortcut_idx = api_src.index(
        'if run_row.get("status") == "completed"')
    assert gate_idx < completed_shortcut_idx, (
        "بوّابة تعارض السوق يجب أن تسبق فرع «مكتملة => أعِدها كما هي»")


def _guard_golden_contract_test_exists_and_covers_both_paths():
    """LESSONS ٣٧ — الاختبار الذهبي موجودٌ فعلياً ويفحص كِلا مسارَي الدخول
    على نفس سيناريو الحادثة (زبدة الفول السوداني/الكويت)، لا مساراً واحداً."""
    assert _exists("tools/canonical_kuwait_peanut_butter.py")
    assert _exists("tests/test_golden_deep_research_contract.py")
    golden_src = _read("tests/test_golden_deep_research_contract.py")
    assert '"/analyze"' in golden_src and '"/research"' in golden_src
    assert "resume_market_mismatch" in golden_src
    smoke_src = _read("tools/post_deploy_smoke.py")
    assert "hs_confirmation_needed" in smoke_src, (
        "فحص الدخان بعد النشر يجب أن يثبت بوّابة HS حياً (Wave 3.2)")


def _guard_general_hs_classifier_no_lookup_table_ceiling():
    """LESSONS ٣٩ — عائلة `lookup-table-ceiling`: بذرة CSV تلميحٌ ابتدائي لا
    الحاكم النهائي. الحارس السلوكي: (١) بوّابة سلامة الفصل ترفض رمزاً خارج
    بنية WCO الحقيقية بمعزلٍ عن ادّعاء أيّ نموذج؛ (٢) منتجٌ محسومٌ جيداً
    («تمور») تلقائيٌّ بلا أيّ نداء كلود؛ (٣) منتجٌ مُعلَّم (زبدة الفول
    السوداني) لا يمرّ تلقائياً بلا كلود؛ (٤) نقطة الاختناق `preflight_block`
    تُلحِق `candidates` فعلياً بردّ الحجب — لا رفضٌ عارٍ بلا توجيه."""
    import silk_hs_classifier as hsc
    from silk_hs_resolver import chapter_valid
    # (١) سلامة الفصل بنيويةٌ بمعزلٍ عن مصدر الادّعاء.
    assert chapter_valid("999999") is False
    assert hsc._validated_candidate("أيّ منتج", "999999") is None
    # (٢) لا هدر — منتجٌ واثقٌ لا يستدعي كلود إطلاقاً.
    from unittest.mock import patch
    with patch("silk_ai_judge._call") as mock_call:
        r = hsc.classify_general("تمور", allow_claude=True)
    assert r["tier"] == "auto" and r["hs6"] == "080410"
    assert mock_call.called is False
    # (٣) منتجٌ مُعلَّم — الرمز اللفظي الخاطئ (040510 زبدة ألبان) **لا يفوز
    # أبداً** (القاعدة الدائمة). بعد إتاحة الرمز الصحيح 200811 في البذرة
    # (طلب المالك 2026-07-23) صار الحسم الحتمي يُنتج **العائلة الصحيحة**
    # تلقائياً — تصحيحٌ يقوّي القاعدة (لا فئةً مجاورةً خاطئةً بثقة).
    r2 = hsc.classify_general("زبدة الفول السوداني", hs_code="040510",
                              allow_claude=False)
    assert r2["hs6"] != "040510"
    assert r2["hs6"] == "200811"
    # (٤) preflight_block يُلحِق مرشّحين فعليّين بردّ الحجب.
    from silk_hs_confirm import preflight_block
    with patch.dict(os.environ, {"SILK_HS_CONFIRM_GATE": "1"}):
        blocked = preflight_block("زبدة الفول السوداني", "040510",
                                  allow_claude=False)
    assert blocked is not None and blocked.get("candidates")


def _guard_watchdog_owner_only_no_client_contamination():
    """LESSONS ٣٨ — الحارس («كاميرا مراقبة»، طلب المُشرِف): مراقبةٌ دائمة
    مملوكة للمالك حصراً بلا أيّ تلوّث لسطح العميل. الحارس السلوكي:
    (١) نقطة استدعاءٍ واحدة مشتركة يُستدعاها كلا `/analyze` و`/research`
    (نفس معيار البند ٣٥: عدّ استدعاءات `_attach_watchdog(` ≥ ٣ — التعريف
    + نداءان)؛ (٢) `silk_render.py`/`silk_reports.py` (طبقتا العرض/التصدير
    التي يراها العميل) لا تستوردان `silk_watchdog` إطلاقاً؛ (٣) `observe()`
    لا يعدّل نتيجة التحليل الممرَّرة إليه؛ (٤) عطلٌ داخلي في الحارس لا يرفع
    استثناءً أبداً — يُعاد سجلٌّ يحمل `self_error` بدل إسقاط التحليل."""
    import inspect
    api_src = _read("api.py")
    assert api_src.count("_attach_watchdog(") >= 3, (
        "_attach_watchdog يجب أن تُستدعى من كلا /analyze و/research")
    import silk_render
    import silk_reports
    assert "silk_watchdog" not in inspect.getsource(silk_render)
    assert "silk_watchdog" not in inspect.getsource(silk_reports)
    import silk_watchdog
    result = {"product": "x", "view": {"deep_research": {}},
             "data_economics": {}, "market": {}}
    before = dict(result)
    silk_watchdog.observe(result, "research", analysis_id=None)
    assert result == before, "الحارس عدَّل نتيجة التحليل — خرق مبدأ عدم التلوّث"
    rec = silk_watchdog.observe(object(), "research", analysis_id=999)
    assert rec is not None and rec.get("self_error")


def _guard_ui_tier_consumption_single_choke_point():
    """LESSONS ٤٠ — بلاغ «UI-ONLY FIX» (المُشرِف): نقطة اختناق التصنيف
    (`res.tier` من `/classify_hs`) لها موقعُ استهلاكٍ واحدٌ في الواجهة، لا
    مسارٌ ثانٍ يثق بـhs6 خامًا. الحارس السلوكي: (١) شارة «✓ صُنّف تلقائياً»
    نصٌّ حرفيٌّ ظهورهُ الوحيد داخل `ensureHs` مشروطًا بـ`tier==="auto"`؛
    (٢) معالجا نقر صفّ الفهرس (`#pDrop`) وتأكيد استخلاص الصورة (`#intakeGo`)
    يمرّان عبر `ensureHs` بدل ضبط الحسم مباشرةً؛ (٣) نصّ الشارة المشترك
    (`resolvedAs`) لم يعد يحمل ادّعاء «صُنّف تلقائياً» بذاته — وإلا يظهر على
    أيّ تأكيدٍ يدويّ (اختيار مرشّح، إدخال يدويّ) رغم أنه ليس تلقائيًا فعلاً."""
    html = _read("web/index.html")
    badge = "✓ صُنّف تلقائياً"
    assert html.count(badge) == 1, (
        f"شارة «{badge}» ظهرت {html.count(badge)} مرّة — يجب أن تكون نقطة "
        "انطلاقٍ واحدة فقط داخل ensureHs")
    ensure_hs_start = html.index("function ensureHs(")
    ensure_hs_body = html[ensure_hs_start:html.index("function _pct(", ensure_hs_start)]
    assert badge in ensure_hs_body and 'res.tier==="auto"' in ensure_hs_body
    pdrop_start = html.index('$("#pDrop").addEventListener("click"')
    assert "ensureHs(function(){})" in html[pdrop_start:pdrop_start + 1000]
    intake_go_start = html.index('$("#intakeGo").addEventListener("click"')
    assert "ensureHs(function(){})" in html[intake_go_start:intake_go_start + 1000]
    # نصّ الشارة المشتركة نفسه بلا ادّعاء «تلقائي» — وإلا تظهر على أيّ تأكيدٍ
    # يدويّ (اختيار مرشّح/إدخال يدويّ) عبر إعادة استعمال t("resolvedAs").
    resolved_as_start = html.index("resolvedAs:{")
    resolved_as_line = html[resolved_as_start:resolved_as_start + 120]
    assert "صُنّف تلقائياً" not in resolved_as_line, (
        "resolvedAs المشتركة تحمل ادّعاء «صُنّف تلقائياً» — تُعيد ظهور الشارة "
        "على مساراتٍ يدويةٍ غير محسومة (نفس عائلة الحادثة)")


def _guard_active_resolution_beats_rejected_and_short_root_collision():
    """LESSONS ٤١ — «ONE FIX» (المُشرِف): رفضٌ بلا بديلٍ صحيحٍ مأزقٌ لا حَل؛
    التاجر لا يعرف رموز HS ولا يجوز أن يُطلَب منه ذلك. الحارس السلوكي:
    (١) مرشّح كلود المصادَق يتصدّر على مرشّحٍ حتميٍّ مرفوضٍ (تداخلٌ دون
    العتبة) رغم بقاء الأخير «مُتحقَّقاً» لمجرّد وجوده في بذرتنا الجزئية —
    نفس بلاغ «زبدة الفول السوداني»، منتجٌ مختلف؛ (٢) احتواء جذرٍ من حرفين
    («بن» داخل «بنكهة»/«جبن») لا يُحتسَب تداخلاً حقيقياً — نواة المطابقة
    ترفض التصادف اللفظي القصير بمعزلٍ عن تدفّق المصنِّف بأكمله."""
    import silk_hs_classifier as hsc
    from silk_hs_confirm import _covered
    # (١) الترتيب: مرشّحٌ حتميٌّ مرفوضٌ (متحقَّق، تداخلٌ ضعيف) لا يتصدّر على
    # مرشّح كلود (غير متحقَّق لكنه عابرٌ للعتبة وأعلى تداخلاً) — نفس السيناريو
    # الذي كان يُبقي الرمز المرفوض معروضاً كخيارٍ أساسيّ بلا بديل.
    rejected = {"hs6": "040510", "overlap": 0.33, "verified": True,
               "model_confidence": 0.5, "source": "deterministic"}
    resolved = {"hs6": "200811", "overlap": 0.6, "verified": False,
               "model_confidence": 0.9, "source": "llm"}
    ordered = sorted([rejected, resolved], key=hsc._rank_key, reverse=True)
    assert ordered[0]["hs6"] == "200811", (
        "المرشّح المرفوض تصدّر على المرشّح المصادَق من كلود — التاجر يبقى "
        "بين تأكيد رمزٍ خاطئ وإدخال رمزٍ يجهله")
    # (٢) نواة التداخل: احتواء جذرٍ قصيرٍ (حرفان) لا يُعَدّ تطابقاً — التطابق
    # التامّ يبقى بلا قيدٍ على الطول.
    assert _covered("بنكهه", ["بن", "غير", "محمص"]) is False
    assert _covered("زبده", ["زبده"]) is True


def _guard_dza_quality_gate_six_findings():
    """LESSONS ٤٢ — «تحليل #1» (زبدة الفول السوداني/الجزائر DZA، 2026-07-21):
    ستّ نتائج فشل بوّابة الجودة معاً على تشغيلة واحدة (Markdown/تنسيق شارد،
    ثقة خام، تكرار رقم مفتاحي ×٢، عمود سعر مضلِّل، سقف الملحق التقني). رمز
    HS الخاطئ خارج نطاق هذا الحارس عمداً (يُصلَح عبر مسار مصنِّف HS العام).
    الحارس السلوكي: يعيد بناء المدوّنة الحقيقية الشكل (tools/canonical_
    dza_peanut_butter.py) ويؤكّد أن الحكم لم يعد FAIL بعد الإصلاح، وأن
    حارسي الانحدار الحقيقيين (raw_confidence/currency_label_mismatch) صفر."""
    from tools.canonical_dza_peanut_butter import dza_research_blob
    import silk_render
    import silk_quality_gate as QG
    view = silk_render.build_view(dza_research_blob())
    out = QG.run_quality_gate(view)
    assert out["verdict"] != "FAIL", f"لا يزال FAIL: {out['findings']}"
    checks = {f["check"] for f in out["findings"]}
    assert "raw_confidence" not in checks
    assert "currency_label_mismatch" not in checks
    fired = checks & QG._REGRESSION_GUARD_FIRED
    assert fired == set(), f"حارس انحدار أُطلِق رغم الإصلاح: {fired}"


def _guard_hs_classifier_valve_fail_safe_default():
    """LESSONS ٤٣ — بلاغ حيّ متكرّر (المالك): المُصنِّف العام مُصلَحٌ ومُختبَرٌ
    ليتعرَّف على الرمز الصحيح لمنتجٍ متعدِّد الصفات، لكنه كان خلف صمّامٍ
    `SILK_HS_CLASSIFIER` مُطفأٍ افتراضياً — فلا يعمل أبداً في الإنتاج ما لم
    يُضبَط صراحةً. الحارس السلوكي: (١) الصمّام مفعَّلٌ حين المتغيّر غير
    مضبوط إطلاقاً؛ (٢) يُطفَأ فقط بقيمةٍ صريحة (0/false/no/off)؛ (٣) مع
    الصمّام الافتراضي وحده (بلا أيّ ضبطٍ إضافي)، محاكاة تصنيف منتجٍ متعدِّد
    الصفات تحسم تلقائياً للفصل الصحيح لا الصفة الثانوية العارضة."""
    import os
    from unittest.mock import patch
    import silk_hs_classifier as hsc
    os.environ.pop("SILK_HS_CLASSIFIER", None)
    assert hsc.enabled() is True, "الصمّام يجب أن يكون فشلاً-آمناً (مفعَّلاً) دون ضبط"
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "0"}):
        assert hsc.enabled() is False
    fake = ('{"candidates":[{"hs6":"200811","description_ar":'
           '"فول سوداني محضّر أو محفوظ","reason_ar":'
           '"زبدة الفول السوداني محضّرةٌ من الفول السوداني","confidence":0.92}]}')
    with patch("silk_ai_judge.available", return_value=True), \
         patch("silk_ai_judge._call", return_value=fake), \
         patch("silk_usage.try_reserve_paid_calls", return_value=True), \
         patch("silk_usage.try_reserve_usd", return_value=True):
        r = hsc.classify_general("زبدة الفول السوداني", hs_code="040510",
                                 allow_claude=True)
    assert r["tier"] == "auto", f"لم يُحسَم تلقائياً بالإعدادات الافتراضية: {r}"
    assert r["hs6"] != "040510"
    # (٤) الصمّام مرئيٌّ عن بُعد من /health (نفس نمط persist_guard) — لا
    # اعتماد على قراءة الشيفرة لمعرفة حالته الفعلية على النشر الحيّ.
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import api
    with patch.dict(os.environ, {"SILK_API_KEY": "", "ANTHROPIC_API_KEY": "k"}):
        health = TestClient(api.create_app()).get("/health").json()
    assert health["hs_classifier"]["enabled"] is True
    with patch.dict(os.environ, {"SILK_HS_CLASSIFIER": "0",
                                 "ANTHROPIC_API_KEY": "k"}):
        health_off = TestClient(api.create_app()).get("/health").json()
    assert health_off["hs_classifier"]["enabled"] is False
    assert any("SILK_HS_CLASSIFIER" in w
              for w in (health_off.get("warnings") or [])), (
        "تعطيلٌ صريحٌ للصمّام مع مفتاح كلود متاح يجب أن يظهر تحذيراً في /health")


def _guard_verdict_tone_recognizes_arabic_labels():
    """LESSONS ٤٤ — Master Prompt Part 2 §B: بوابة اتساق الحكم عند التسليم
    كشفت أنّ `silk_render._verdict_tone` كانت تتعرّف على الرموز الإنجليزية
    فقط (GO/WATCH/CONDITIONAL/NO-GO)، فأيّ مسارٍ يضع التسمية العربية مباشرةً
    (`"دخول مشروط"` لا `"CONDITIONAL-GO"`) كان ينهار إلى tone="unknown"
    فتعرض الشارة «تعذّر إصدار توصية» بينما جدول/متن التقرير يذكران التسمية
    الصحيحة — تناقضٌ شارة/متن. الحارس السلوكي: التسمية العربية والرمز
    الإنجليزي المطابق يُنتِجان نفس الـtone؛ وبوابة اتساق التسليم (شارة/جدول/
    سطر القرار) تمرّ فعلياً على مدوّنة الكويت القانونية بلا رفعٍ."""
    from silk_render import _verdict_tone
    assert _verdict_tone("دخول مشروط") == _verdict_tone("CONDITIONAL-GO") == "conditional"
    assert _verdict_tone("مراقبة السوق") == _verdict_tone("WATCH") == "watch"
    assert _verdict_tone("عدم الدخول حالياً") == _verdict_tone("NO-GO") == "nogo"
    assert _verdict_tone("التوصية بالدخول") == _verdict_tone("GO") == "go"

    from tools.canonical_kuwait_peanut_butter import kuwait_research_blob
    from silk_render import build_view
    from silk_reports import render_docx, render_client_docx
    import os
    import tempfile
    os.environ["SILK_HERMETIC"] = "1"
    view = build_view(kuwait_research_blob())
    tmp = tempfile.mkdtemp()
    render_docx(view, os.path.join(tmp, "r.docx"))
    render_client_docx(view, os.path.join(tmp, "c.docx"))


def _guard_price_fix_scoped_to_table_window():
    """LESSONS ٤٥ — دالة الإصلاح `silk_render._fix_price_column_currency_
    label` تقتصر على نافذة الجدول نفسه (لا كامل المستند) عند البحث عن
    عملةٍ أخرى، مطابقةً لدالة الفحص الشقيقة (اللائحة ٤٢). حارسٌ مضاد: تناقضٌ
    حقيقي داخل نفس الجدول يبقى مُصلَحاً بالعملة الصحيحة."""
    from silk_render import _fix_price_column_currency_label
    unrelated_euro_elsewhere = (
        "| المنتج | السعر/كجم بالدولار |\n| --- | --- |\n| صنف | 6.0$ |\n\n"
        "## قسمٌ آخر\nخطر صرف العملة: اليورو هو عملة السوق نفسها.")
    out = _fix_price_column_currency_label(unrelated_euro_elsewhere)
    assert "السعر/كجم بالدولار" in out and "السعر/كجم باليورو" not in out

    same_table_mismatch = (
        "| المنتج | السعر/كجم بالدولار |\n| --- | --- |\n| صنف | 9.14€ |")
    out2 = _fix_price_column_currency_label(same_table_mismatch)
    assert "السعر/كجم باليورو" in out2


def _guard_quality_gate_is_client_export_delivery_condition():
    """LESSONS ٤٦ — حزمة الفكس v2.1: بوابة الجودة شرط تسليم للعميل (FAIL =>
    409) + عائلة فحوصات كاتب/عرض بنيوية تُفشِل على golden-bad. حارسٌ سلوكي:
    الفحوصات الجديدة تُطلِق فعلياً على مدخلات تُعيد إنتاج العطل، والدوال
    الحاجبة موجودة في api.py."""
    import silk_quality_gate as qg

    sections = "\n".join(
        f"## {i}. {s}\nنصّ القسم بجملة تنتهي بنقطة."
        for i, s in enumerate((
            "الخلاصة التنفيذية", "منهجية البحث ونطاقه",
            "نظرة عامة على السوق وحجمه", "ديناميكيات السوق",
            "تحليل المستهلك والطلب", "المشهد التنافسي",
            "التنظيم والوصول للسوق", "اللوجستيات وسلسلة الإمداد",
            "تقييم المخاطر", "التوصيات الاستراتيجية", "الملاحق"), 1))

    def _checks(text):
        return {f["check"] for f in qg.run_quality_gate(
            {"deep_research": {"report": {"text": text},
                              "missions": {}, "analyst": {},
                              "verdict": {"verdict": "WATCH"}}})["findings"]}

    # عيّنات golden-bad تُعيد إنتاج العطل الموصوف — كل فحص جديد يُطلِق.
    assert "hhi_false_precision" in _checks(
        sections + "\n\nمؤشر التركّز HHI = 2184.7 هنا.")
    assert "near_duplicate_figure" in _checks(
        sections + "\n\nالواردات 6,733,369 دولاراً وفي جدول 6,733,376 دولاراً.")
    assert "supplier_rank_gap" in _checks(
        sections + "\n\n#1 تونس، #2 الجزائر، #5 إيران، #6 المغرب.")
    assert "lpi_invalid_edition_year" in _checks(
        sections + "\n\nمؤشر LPI 3.2 لعام 2022 مرتفع.")
    # الدوال الحاجبة موجودة في مسار التصدير + الحارس + المُصدِّر.
    _needles("api.py", "def _block_client_export_if_gate_failed")()
    _needles("silk_export_gate.py", "def evaluate", "def is_blocked")()
    _needles("silk_watchdog.py", "def record_blocked_export")()
    _needles("silk_reports.py", "def _client_references_section")()


# ── حُرّاس برنامج إصلاح جودة التقارير (WP-1…WP-7، صفوف 47-53) ────────────────

def _guard_wp1_verdict_determinism():
    """صفّ ٤٧ — الحكم الحتمي هو المعروض الوحيد + temperature=0 + سُلَّم ثقة واحد."""
    _needles("silk_narrative.py", "def authoritative_verdict")()
    _needles("silk_llm_provider.py", "def _supports_sampling_params",
             "def _scrub_sampling_params", '["temperature"] = 0')()
    _needles("tests/test_wp1_verdict_determinism.py",
             "test_sampling_params_present_for_a_still_supported_model",
             "test_sampling_params_absent_for_the_repo_default_model")()
    _needles("silk_style_contract.py", "def confidence_band_label")()
    _needles("tests/test_wp1_verdict_determinism.py",
             "test_three_consecutive_renders_are_byte_identical")()


def _guard_wp2_no_raw_internal_output():
    """صفّ ٤٨ — لا نائب/سقالة/بتر يصل العميل؛ الحجب لا التسليم المشوَّه."""
    _needles("silk_reports.py", "def _client_prose",
             "def _client_missing_narrative_heads")()
    _needles("silk_ai_judge.py", "def rephrase_client_sections")()
    _needles("silk_quality_gate.py", "_check_client_scaffold_leak",
             "_check_placeholder_leak")()
    _needles("tests/test_wp2_client_output_hygiene.py",
             "test_gate_fails_on_literal_so_what_in_client_text")()


def _guard_wp3_evidence_integrity():
    """صفّ ٤٩ — شارة واعية بالمنشأ + مصالحة رقمية + تفريد مصادر مُطبَّع."""
    _needles("silk_narrative.py", "def evidence_badge_for",
             "RECONCILED_OUT_TAG")()
    _needles("silk_render.py", "def _reconcile_numeric_conflicts")()
    _needles("tests/test_wp3_evidence_integrity.py",
             "test_near_duplicate_values_reconcile_to_one_canonical")()


def _guard_wp4_gaps_consistency():
    """صفّ ٥٠ — مصدر واحد لمدخلات الفجوات الأربعة + حارس تناقض الختام."""
    _needles("silk_reports.py", "def _client_gap_inputs")()
    _needles("silk_quality_gate.py", "_check_gaps_closing_contradiction")()
    _needles("tests/test_wp4_gaps_consistency.py",
             "test_gate_fails_on_closing_contradiction")()


def _guard_wp5_rtl_bracket_isolation():
    """صفّ ٥١ — عزل RLM قبل _finalize_rtl + فحص اتجاه الأقواس على الـPDF.

    الفحصُ صار **هندسياً** (تدقيق 2026-08-27، الصفّ ٢٠١): المقياسُ النصّي
    القديم كان مُعاكِسَ الإشارة. الحارسُ يقفل الاثنين معاً كي لا يُستبدَل
    أحدُهما بالآخر صامتاً."""
    _needles("silk_reports.py", "def _bidi_isolate_brackets",
             "def count_suspicious_brackets", "def _pdf_bracket_check",
             "def bracket_orientation_counts")()
    _needles("tools/rtl_calibration.py", "def build_bracket_fixture")()
    _needles("tests/test_wp5_rtl_brackets.py",
             "test_pdf_bracket_check_fails_export_above_threshold")()


def _guard_wp6_injector_adversarial_locks():
    """صفّ ٥٢ — حاقنا §D-1/§D-2 مقفولان بجُمل التقارير المُسلَّمة."""
    _needles("silk_render.py", "def _already_explained_nearby",
             "def _year_in_growth_span")()
    _needles("tests/test_wp6_injector_hardening.py",
             "test_delivered_sentence_growth_span_year_not_tagged_stale",
             "test_delivered_sentence_dash_explained_cagr_not_redefined")()


def _guard_wp7_delivery_gate_hardening():
    """صفّ ٥٣ — تجاوز بسلطة مالك منفصلة + بوابة نصّ المُنتَج النهائي."""
    _needles("api.py", "owner_override_required", "X-Owner-Key")()
    _needles("silk_watchdog.py", "def record_override",
             "def override_records_for")()
    _needles("silk_quality_gate.py", "def run_client_artifact_text_gate")()
    _needles("tests/test_wp7_delivery_gate_hardening.py",
             "test_artifact_text_gate_catches_all_leak_classes")()


def _guard_zero_confidence_finding_declared_gap():
    """LESSONS ٥٤ — بند بعثة قيمته غير فارغة بثقة 0.0 (خرق حارس المراقبة الحي
    على demand_trends): ادعاء بثقة صفرية — مصرَّحاً بها أو موروثة من نقطة فجوة
    مستشهَد بها — يُعلَن فجوة في gaps لا يُشحَن بنداً أبداً."""
    import json as _json

    import silk_llm_runtime as _rt
    from silk_data_layer import DataPoint as _DP
    reg = {"gap1": _DP(None, "FAOSTAT", 0.0, "401 — فجوة معلنة", "2026-07-23")}
    text = _json.dumps({"findings": [
        {"claim": "ادعاء صفري الثقة", "datapoint_ids": ["gap1"],
         "confidence": 0.0}], "gaps": [], "summary": ""}, ensure_ascii=False)
    out = _rt._parse_output(text, reg)
    assert out["findings"] == [], "بند بثقة 0.0 شُحن بدل إعلانه فجوة"
    assert any("ادعاء صفري الثقة" in g for g in out["gaps"]), \
        "الادعاء الصفري لم يُعلَن فجوة"


def _guard_coverage_gate_year_fallback():
    """LESSON ٥٦ — بوّابة «خارج التغطية» كانت تفشل مفتوحةً دوماً (استطلاع سنة
    اليوم-١ بلا سُلَّم fallback، وكومتريد متأخّر). الحارس (قراءة مصدر + سلوك):
    السُّلَّم + المُحلِّل + السنة المشتركة موجودة، والبوّابة تستعملها، والأقفال قائمة."""
    src = _read("silk_market_ranker.py")
    for n in ("DEFAULT_STUDY_YEAR", "def coverage_year_ladder",
              "def world_import_totals_resolved"):
        assert n in src, f"علامة إنفاذ سُلَّم التغطية مفقودة: {n}"
    api = _read("api.py")
    assert "world_import_totals_resolved" in api, "البوّابة لا تستعمل السُّلَّم"
    # سلوك: السُّلَّم يبدأ من سنة اليوم-١ ويضمن سنة الدراسة في الذيل.
    import datetime as _dt
    import silk_market_ranker as _R
    ladder = _R.coverage_year_ladder()
    assert ladder[0] == _dt.date.today().year - 1, ladder
    assert _R.DEFAULT_STUDY_YEAR in ladder, ladder
    lock = _read("tests/test_out_of_coverage_guard.py")
    for fn in ("test_coverage_gate_closes_when_current_year_empty_but_study_year_full",
               "test_world_import_totals_resolved_ladders_to_first_nonempty_year"):
        assert f"def {fn}" in lock, f"قفل سُلَّم التغطية مفقود: {fn}"


def _guard_sanitizer_obfuscation_variants():
    """LESSON ٥٧ — سبع صيغ تشويش أكّد المشرف نفاذها بالتنفيذ المباشر. الحارس
    السلوكي يبني السلاسل السبع الحرفية ويؤكّد تحييد كلٍّ (المسار العام أو
    مسار العميل) — القفل بالسلسلة الحرفية (silk-operations §4). الصيغة السابعة
    (عدّ نداءات الأدوات العربية) أُعيدت في متابعة #7 المستقلّة (قرار المالك
    2026-07-23): تِلِمتري مشروع يُقرأ من الملخّص الخام، لكنه على أسطح العميل
    سباكةٌ تُجرَّد — الفكس يوفّق بينهما (تتبّع من الخام + تجريد للعرض)."""
    import silk_render as _SR
    from silk_reports import (_client_forbidden_hits, _client_redact_text,
                              _client_sanitize)

    def _gen(s):
        return _SR._strip_internal_plumbing(s)

    def _client_clean(s):
        return not _client_forbidden_hits(_client_redact_text(_client_sanitize(s)))

    # (١) stop_reason مباعَد/عارٍ بلا قيمة — المسار العام.
    assert "stop_reason" not in _gen("التوليد stop_reason =  انتهى")
    # (٢) اسم مزوّد لاتيني مباعَد «S e r p A p i» — مسار العميل.
    assert _client_clean("مبنيّ على S e r p A p i التجارية")
    # (٣) درجة ثقة بأرقام عربية-هندية «ثقة=٠٫٦٤» — المسار العام.
    o3 = _gen("التقييم ثقة=٠٫٦٤ للمصدر")
    assert "٠٫٦٤" not in o3 and "ثقة=" not in o3, o3
    # (٤) اسم مزوّد عربي مُشكَّل «إكْسبِلي» — مسار العميل.
    assert _client_clean("المصدر إكْسبِلي غير متاح")
    # (٥) «سجلات الخادم» بلا شدّة — المسار العام.
    assert "سجلات الخادم" not in _gen("خطأ داخلي راجع سجلات الخادم الآن")
    # (٦) بادئة مفتاح بعثة مرقّمة «m3_» — المسار العام.
    assert "m3_" not in _gen("أنتجت m3_pricing_scout النتيجة")
    # (٧) عدّ نداءات أدوات بأرقام عربية «نداءات أدوات: ٢» — المسار العام
    # (أُعيدت في متابعة #7 المستقلّة، قرار المالك 2026-07-23).
    assert "نداءات أدوات" not in _gen("الملخّص | نداءات أدوات: ٢")


def _guard_wave2_med_hardening():
    """LESSON ٥٩ — خمسة إصلاحات MED من تدقيق v2 (الموجة ٢). الحارس يؤكّد نقاط
    الإنفاذ الخمس (قراءة مصدر) + وجود ملف الأقفال السلوكية."""
    st = _read("silk_storage.py")
    assert "def _reconcile_leaked_usd" in st, "#3 مُصالِح الحجز المتسرّب غائب"
    assert "def reconcile_failed_run_usd" in st, "#3 مصالحة الفشل الرشيق غائبة"
    assert "status = 'failed'" in st, "#3 المكنَس لا يمسح صفوف 'failed'"
    api = _read("api.py")
    assert api.count("reconcile_failed_run_usd(analysis_id)") >= 2, (
        "#3 أحد مساري فشل /research لا يُصالِح")
    assert "begin_data_counter()" in api and "record_usd" in api, "#6 قياس الرؤية غائب"
    assert "البند #5" in api and "أداة اختبار المفاتيح قبل ضبط" in api, "#5 غير موثَّق"
    assert 'SILK_GMAPS_ENRICH_GRACE_S", "25"' in api, "#4 المهلة الآمنة غائبة"
    assert '"processing": processing' in api, "#4 علم processing غائب"
    html = _read("web/index.html")
    assert "function _expBusy(" in html and "if(S.exportBusy){" in html, (
        "#7 صمّام تعطيل التصدير/حارس النقر المزدوج غائب")
    assert _exists("tests/test_wave2_med_fixes.py"), "ملف أقفال الموجة ٢ مفقود"


def _guard_composite_source_id_attribution():
    """LESSONS ٦٠ — إسنادٌ مركّب (بلاغ قطر): معرّفُ المصدر ذرّيّ، الإسنادُ
    المتعدّد قائمةٌ لا سلسلةٌ مدموجة؛ المراجع تُسطّح فيُسنِد كلٌّ لرابطه."""
    from silk_data_layer import (atomic_source_ids, is_atomic_source_id,
                                 public_source_url)
    assert not is_atomic_source_id("IMF WEO، World Bank")   # فاصلُ دمجٍ مرفوض
    assert is_atomic_source_id("WITS/WTO Tariff")           # «/» مشروع
    assert atomic_source_ids("A", ("A", "B")) == ["A", "B"]
    # أمانةُ GAFTA لها رابطٌ ذرّيّ مستقلّ (كانت تعيش داخل مركّبٍ بلا رابط).
    assert public_source_url("GAFTA secretariat") == "https://www.lasportal.org"
    assert public_source_url("GCC secretariat") != public_source_url(
        "GAFTA secretariat")
    _needles("silk_llm_runtime.py", "source_ids=tuple(pub_sources)")()
    _needles("silk_evals.py", "listed-but-unused", "معرّفُ مصدرٍ **مركّب**")()
    _needles("tests/test_hf_attribution_truncation_plausibility.py",
             "def test_three_source_finding_yields_three_atomic_references")()


def _guard_renderer_truncation_and_empty_parens():
    """LESSONS ٦١ — بترٌ داخل رقمٍ + قوسٌ فارغ (بلاغ قطر): القصُّ لا ينتهي داخل
    رقم، وحذفُ الاستشهاد لا يترك «()»."""
    import re as _re
    from silk_reports import _trim_sentence, _client_sanitize
    from silk_render import _strip_internal_plumbing
    out = _trim_sentence("تعافٍ جزئيّ إلى 7.12 مليون دولار مؤكَّد", 22)
    assert not _re.search(r"[0-9٠-٩][.،]\s*$", out), out
    assert _client_sanitize("قيمة (/) مؤكَّدة") == "قيمة مؤكَّدة"
    assert "()" not in _strip_internal_plumbing("المتاجر (dp3) كارفور")
    _needles("silk_render.py", "_DP_GROUP_RE", "_EMPTY_CITATION_GROUP_RE")()
    _needles("tests/test_hf_attribution_truncation_plausibility.py",
             "def test_trim_sentence_never_ends_inside_a_number")()


def _guard_cross_source_plausibility():
    """LESSONS ٦٢ — مقدارٌ غيرُ مُصالَح (بلاغ قطر): حارسُ معقوليةٍ يقارن المقاديرَ
    بمرتكزات التشغيلة ويُوسَم/يُتحفَّظ عليه، ويُسجَّل في المانيفست."""
    import silk_plausibility as P
    result = {"deep_research": {"missions": {
        "trade_flow": {"findings": [{"value": 7_000_000.0, "source": "UN Comtrade",
                                    "note": "إجمالي استيراد قطر من العالم USD"}]},
        "consumer_culture": {"findings": [{"value": "497 مليون دولار",
            "source": "ويب", "note": "حجم سوق الفول السوداني الكامل"}]}}}}
    flags = P.check_magnitudes(result)
    assert flags and flags[0]["detail"]["import_ratio"] > 20
    assert P.check_magnitudes({"deep_research": {"missions": {}}}) == []  # فشلٌ آمن
    _needles("silk_render.py", "silk_plausibility.annotate")()
    _needles("silk_evals.py", "def _plausibility_reconciled")()
    _needles("tests/test_hf_attribution_truncation_plausibility.py",
             "def test_plausibility_flags_implausible_market_size")()


def _guard_ask_what_the_product_answers():
    """LESSONS ٦٥ — الحوارُ كان يسأل عن رقمٍ يُجيب عنه المنتجُ نفسُه (نسبةُ
    دهن). الحارس **سلوكيّ**: يقيس فعلاً على الوصف الرسميّ الحقيقي، ويتحقّق
    أنّ نقطةَ الاختناق موصولةٌ بمسارَي الدخول معاً (لا إصلاحَ نصفيّ)."""
    import silk_hs_attributes as A
    # الترويسةُ التي أنتجت البلاغ — بنودُها من مرجعنا الرسميّ، بلا نموذج.
    codes = [c for c in sorted(
        __import__("silk_hs_resolver").load_hs_reference())
        if c.startswith("0401") and A.band_of(c)]
    assert len(codes) >= 3, "لم تُقرأ نطاقاتُ الترويسة من الوصف الرسميّ"
    disc = A.discriminator([{"hs6": c} for c in codes])
    assert disc and disc["dimension"] == "fat" and disc["unit"] == "%"
    # الصمّامُ مُطفأٌ افتراضياً (D1/اللائحة ٧٠) — يُفعَّل هنا صراحةً لأنّ هذا
    # الحارسَ يختبر **سلوكَ الميزة**، لا افتراضَها (ذاك حارسُ اللائحة ٧٠).
    _saved = os.environ.get("SILK_HS_ATTRIBUTE_RESOLVE")
    os.environ["SILK_HS_ATTRIBUTE_RESOLVE"] = "1"
    try:
        # (أ) قياسٌ من بطاقة العبوة يحسم بلا أيّ سؤال، وموسومٌ بمصدره.
        got = A.resolve_by_attribute(
            "منتجٌ من هذه الترويسة", [{"hs6": c} for c in codes],
            allow_web=False,
            label_attributes=[{"name": disc["label_ar"], "value": 3.5,
                               "unit": "%"}])
        assert got["hs6"] and got["resolved_from"] == "image"
        assert "صورة العبوة" in got["note_ar"]
        # (ب) بلا قياسٍ لا يُحسَم رمزٌ أبداً، والحوارُ يحمل ما نقص وحدودَ البنود.
        gap = A.resolve_by_attribute(
            "منتجٌ من هذه الترويسة", [{"hs6": c} for c in codes],
            allow_web=False)
        assert gap["hs6"] is None and gap["missing_ar"] and gap["bands_ar"]
    finally:
        if _saved is None:
            os.environ.pop("SILK_HS_ATTRIBUTE_RESOLVE", None)
        else:
            os.environ["SILK_HS_ATTRIBUTE_RESOLVE"] = _saved
    # (ج) نقطةُ اختناقٍ واحدة موصولةٌ بكِلا مسارَي الإنفاق + بوّابةِ الالتباس.
    src = _read("api.py")
    assert src.count("preflight_resolve") >= 3, (
        "نقطةُ القياس غير موصولةٍ بمسارَي /analyze و/research معاً")
    _needles("api.py", "resolve_or_probe", "attribute_probe",
             "label_attributes", "hs_provenance")()
    _needles("silk_hs_confirm.py", "def resolve_or_probe",
             "def preflight_resolve")()
    _needles("silk_render.py", "hs_provenance",
             "الرمز محدَّد من صورة العبوة", "الرمز محدَّد من مصدر ويب")()
    _needles("web/index.html", "attribute_probe", "label_attributes",
             'd.error==="hs_ambiguous"')()
    # (د) عائلةُ اللائحة ١٢ (الحدود تناقض المتن): المصالحةُ اللفظية
    # (`revalidate`) لا تعمل على رمزٍ حُسِم بقياس — وإلا ظهر «المُحلِّل يعيد
    # رمزاً آخر» بجوار «الرمز محدَّد من صورة العبوة» في نفس التقرير.
    assert ('if not (isinstance(hs_provenance, dict) '
            'and hs_provenance.get("hs6")):') in src, (
        "المصالحةُ اللفظية تعمل على رمزٍ مقيس — تناقضٌ محتوم")


def _guard_band_boundary_strictness_and_second_axis():
    """LESSONS ٦٦ — عيبان يُصدِران **رمزاً خاطئاً بوسمِ مصدرٍ واثق** (اختلاقٌ
    لا فجوة): (أ) تسطيحُ صرامةِ الحدّ («less than 6» تُعامَل كـ«not exceeding
    6») فتُبتلَع قيمةُ الحدّ؛ (ب) ترويسةٌ تنقسم بمحورين (لونُ الشاي × وزنُ
    التعبئة) يحسمها قياسٌ واحد. الحارس **سلوكيّ** على المرجع الحقيقيّ."""
    import silk_hs_attributes as A
    FAKE = "000000"                       # ليس في المرجع => يُقرأ الوصفُ الحرّ
    assert A.band_of(FAKE, "x") is None   # صيد ٣: أُسقطت `or True` المفرغة
    inc = A.band_of(FAKE, "of a fat content, not exceeding 6%")
    strict = A.band_of(FAKE, "of a fat content, less than 6%")
    assert inc and strict, "لم تُقرأ الحدود من العبارة"
    assert inc["hi"] == strict["hi"] == 6.0
    assert inc["hi_inclusive"] is True and strict["hi_inclusive"] is False, (
        "صرامةُ الحدّ مُسطَّحة — «less than» تُعامَل معاملةَ «not exceeding»")
    assert A._contains(inc, 6.0) is True and A._contains(strict, 6.0) is False
    lo_inc = A.band_of(FAKE, "of a fat content, at least 1%")
    assert lo_inc and lo_inc["lo_inclusive"] is True, "حدٌّ أدنى شاملٌ مفقود"
    # (ب) المحورُ الثاني: ترويسةٌ تنقسم بلونٍ ووزنٍ معاً لا تُحسَم بالوزن وحده.
    import collections
    from silk_hs_resolver import load_hs_reference
    heads = collections.defaultdict(list)
    for code in load_hs_reference():
        b = A.band_of(code)
        if b:
            heads[code[:4]].append(b)
    multi = {h: bs for h, bs in heads.items() if len(bs) >= 2}
    assert len(multi) >= 40, "المرجعُ لم يُقرأ — الحارس بلا عيّنة"
    accepted = refused = 0
    for head, bands in multi.items():
        d = A.discriminator([{"hs6": b["hs6"]} for b in bands])
        if d is None:
            refused += 1
            continue
        accepted += 1
        assert len({b["axis"] for b in d["bands"]}) == 1, (
            f"{head}: قُبِلت رغم محورٍ غيرِ رقميٍّ إضافي")
        for prev, nxt in zip(d["bands"], d["bands"][1:]):
            assert prev["hi"] == nxt["lo"], f"{head}: فجوةٌ/تداخل"
            assert bool(prev["hi_inclusive"]) != bool(nxt["lo_inclusive"]), (
                f"{head}: حدٌّ مزدوجُ التغطية أو مكشوف")
    assert accepted >= 5 and refused >= 5, (
        f"توازنُ الحارس مختلّ (مقبولة {accepted}، مرفوضة {refused})")
    _needles("tests/test_hs_attribute_autoresolve.py",
             "def test_bound_strictness_comes_from_the_matched_phrase",
             "def test_property_every_multiband_heading_is_either_clean_or_refused",
             "def test_second_axis_heading_is_refused_not_resolved")()


def _guard_dimension_terms_not_frozen_in_code():
    """LESSONS ٦٧ — عودةُ عائلة الدرس ٣٠ (كلمةُ نطاقٍ حرفيةٌ مجمَّدةٌ في قالبٍ
    قابلٍ لإعادة الاستعمال): مصطلحُ البُعد كان مكتوباً في استعلام الويب،
    فيعمل على الألبان ويُخرِس كلَّ ترويسةٍ أخرى. الحارس: المعجمُ من ملفٍ،
    وصفرُ مصطلحٍ عربيٍّ في المنطق، وصفرُ مصطلحٍ في بناء الاستعلام."""
    import inspect
    import silk_hs_attributes as A
    lex = A.load_dimensions()
    assert len(lex) >= 8, "معجمُ الأبعاد لم يُقرأ من الملفّ"
    assert _exists("data/measurement_dimensions.csv")
    body = _read("silk_hs_attributes.py")
    body = re.sub(r'"""(?:.|\n)*?"""', "", body)
    body = "\n".join(ln.split("#", 1)[0] for ln in body.splitlines())
    arabic = set()
    for row in lex.values():
        if row["label_ar"]:
            arabic.add(row["label_ar"])
        arabic.update(t for t in row["syn"]
                      if any("\u0600" <= ch <= "\u06ff" for ch in t))
    leaked = sorted(t for t in arabic if t and t in body)
    assert not leaked, f"مصطلحُ بُعدٍ عربيٌّ مجمَّدٌ في المنطق: {leaked}"
    qsrc = inspect.getsource(A.probe_web)
    frozen = sorted(t for dim, row in lex.items()
                    for t in ((row["label_ar"],) + tuple(row["syn"]) + (dim,))
                    if len(t) >= 3 and t in qsrc)
    assert not frozen, f"مصطلحٌ مجمَّدٌ في بناء الاستعلام: {frozen}"
    # وبُعدٌ خارج الملفّ يتدهور لمفتاحه — لا مصطلحٌ مختلَق.
    assert A.dimension_terms("zzz_x") == ("zzz_x", ("zzz_x",))


def _guard_multi_axis_heading_confident_wrong_code():
    """LESSONS ٦٨ — «تطابقٌ رقميٌّ على ترويسةٍ متعدّدةِ المحاور = رمزٌ خاطئ
    بثقة». الترويسةُ قد تنقسم بمحورٍ رقميٍّ **وآخرَ غيرِ رقميّ معاً**
    (0902 = لونُ الشاي أخضر/أسود × وزنُ التعبئة ≤٣كجم/>٣كجم). قياسُ الوزن
    وحده لا يُحدِّد بنداً — يختار أحدَ اثنين يختلفان في اللون أيضاً، فيخرج
    رمزٌ **خاطئ** موسومٌ «الرمز محدَّد من صورة العبوة». اختلاقٌ لا فجوة.

    حارسٌ **سلوكيّ** على المرجع الحقيقيّ لا فحصُ وجود: يبني مجموعاتِ مرشّحين
    فعلية ويؤكّد الرفض. (الصفّ ٦٦ يفحص هذه العائلة ضمن فحصٍ مركّب مع صرامةِ
    الحدّ؛ هذا الصفُّ يفردها بحارسها الخاصّ بأمر المُشرِف — العائلةُ اكتُشفت
    خارج قائمة الفجوات المُسمّاة، فتستحقّ قفلاً لا يذوب في غيره.)"""
    import collections
    import itertools
    import silk_hs_attributes as A
    from silk_hs_resolver import load_hs_reference

    # (١) حادثةُ العائلة بعينها: لونٌ مختلف + وزنٌ مختلف => رفضٌ قاطع.
    ref = load_hs_reference()
    tea = [c for c in ("090210", "090220", "090230", "090240") if c in ref]
    assert len(tea) == 4, f"مرجعُ 0902 ناقص: {tea}"
    green_light, green_heavy, black_light, black_heavy = tea
    assert A.discriminator([{"hs6": green_light}, {"hs6": black_heavy}]) is None, (
        "قُبِل مُميِّزٌ لبندين يختلفان في اللون **والوزن** — وزنٌ يحسم رمزاً "
        "يختلف في محورٍ آخر: رمزٌ خاطئ بوسمِ مصدرٍ واثق")
    assert A.discriminator([{"hs6": green_heavy}, {"hs6": black_light}]) is None
    # (٢) ضابطٌ موجب — نفسُ المحور يمرّ، فالحارسُ ليس رفضاً شاملاً.
    same_axis = A.discriminator([{"hs6": green_light}, {"hs6": green_heavy}])
    assert same_axis is not None, (
        "رُفِض بندان يختلفان بالوزن وحده — الحارسُ يرفض كلَّ شيء (لا قيمة له)")
    assert len({b["axis"] for b in same_axis["bands"]}) == 1

    # (٣) كنسٌ شاملٌ على المرجع كلِّه: **كلُّ** زوجٍ عابرِ المحور يُرفَض.
    by_head = collections.defaultdict(list)
    for code in ref:
        band = A.band_of(code)
        if band is not None:
            by_head[code[:4]].append(band)
    multi = {h: bs for h, bs in by_head.items() if len(bs) >= 2}
    assert len(multi) >= 40, f"عيّنةٌ أضعفُ من المتوقَّع: {len(multi)}"
    cross_pairs = 0
    for head, bands in multi.items():
        by_axis = collections.defaultdict(list)
        for b in bands:
            by_axis[b["axis"]].append(b["hs6"])
        if len(by_axis) < 2:
            continue
        for g1, g2 in itertools.combinations(list(by_axis.values()), 2):
            cross_pairs += 1
            assert A.discriminator([{"hs6": g1[0]}, {"hs6": g2[0]}]) is None, (
                f"{head}: قُبِل زوجٌ عابرُ المحور {g1[0]}/{g2[0]}")
    assert cross_pairs >= 100, (
        f"أزواجٌ عابرةُ المحور أقلُّ من المتوقَّع ({cross_pairs}) — "
        "الكنسُ لم يعمل فعلياً")
    # (٤) وأنّ المقبولَ ما يزال موجوداً (لا انهيارَ تغطيةٍ صامت).
    accepted = sum(
        1 for bs in multi.values()
        if A.discriminator([{"hs6": b["hs6"]} for b in bs]) is not None)
    assert accepted >= 5, f"لم يبقَ مقبولٌ يُذكَر ({accepted})"
    _needles("silk_hs_attributes.py", "def _residual_axis", '"axis"')()


def _guard_client_operator_document_divergence():
    """LESSONS ٦٩ — «اختبارُ عرضٍ أخضرُ بجوار مُسلَّمِ عميلٍ خاطئ؛ أكِّدْ على
    الأثر المُصيَّر». سطرُ إفصاحِ مصدر الرمز كان يظهر في مستند **المشغّل**
    ويغيب عن مستند **العميل** — المُسلَّم الحقيقيّ — لأنّ القالبين يبنيان من
    مصدرين مختلفين (`deep_research` مقابل `limits`). اختبارُ الوحدة على
    `view["limits"]` بقي أخضرَ طوال الوقت.

    الحارس **يفتح ملفّ .docx المُصدَّر فعلاً** — لا يقرأ عرضاً ولا يفحص وجودَ
    رمز."""
    pytest.importorskip("docx")
    from docx import Document
    import silk_render
    import silk_reports
    from canonical_netherlands import netherlands_research_blob

    def _doc_text(path: str) -> str:
        doc = Document(path)
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        return "\n".join(parts)

    url = "https://example-provenance.test/label"
    blob = netherlands_research_blob()
    blob["hs_provenance"] = {
        "hs6": "040120", "resolved_from": "web", "attribute": "fat",
        "label_ar": "نسبة الدهن", "value": 3.5, "unit": "%",
        "source_url": url, "confidence": 0.5}

    saved = os.environ.get("SILK_HERMETIC")
    os.environ["SILK_HERMETIC"] = "1"
    try:
        view = silk_render.build_view(blob)
        out = tempfile.mkdtemp()
        # **كِلا** المُسلَّمين — التباعدُ هو العطل، فلا يكفي فحصُ أحدهما.
        for renderer, label in (("render_client_docx", "العميل"),
                                ("render_docx", "المشغّل")):
            path = getattr(silk_reports, renderer)(
                view, os.path.join(out, f"{renderer}.docx"))
            assert os.path.exists(path), f"{label}: لم يُنتَج ملفّ"
            text = _doc_text(path)
            assert "الرمز محدَّد من مصدر ويب" in text, (
                f"مستند {label}: سطرُ إفصاح مصدر الرمز غائبٌ عن الملفّ "
                "المُصدَّر فعلاً (اختبارُ العرض لا يكشف هذا)")
            assert url in text, f"مستند {label}: الرابطُ المُستشهَد به غائب"
        # والنفيُ المقابل: بلا حسمٍ آليّ لا جملةَ إفصاحٍ مُقحَمة.
        plain = silk_render.build_view(netherlands_research_blob())
        clean_path = silk_reports.render_client_docx(
            plain, os.path.join(out, "plain.docx"))
        assert "الرمز محدَّد" not in _doc_text(clean_path), (
            "جملةُ إفصاحٍ ظهرت على مستندٍ لم يُحسَم رمزُه آلياً")
    finally:
        if saved is None:
            os.environ.pop("SILK_HERMETIC", None)
        else:
            os.environ["SILK_HERMETIC"] = saved
    _needles("silk_reports.py", "def _hs_provenance_sentence")()


def _guard_attribute_resolver_flag_off_by_default():
    """D1 — الصمّامُ **مُطفأٌ افتراضياً**. تفعيلُه عند الدمج يجعل ميزةً لم
    تُجرَّب قطّ بمفتاحٍ حيّ تُصدِر رموزاً جمركية لكلّ مستخدم؛ وتفعيلُه قرارُ
    مالكٍ منفصلٌ بعد الدمج مشروطٌ بإغلاق G8. الحارسُ سلوكيّ: يقرأ الدالّة
    فعلاً في غياب المتغيّر وفي حضوره."""
    import silk_hs_attributes as A
    saved = os.environ.pop("SILK_HS_ATTRIBUTE_RESOLVE", None)
    try:
        assert A.enabled() is False, (
            "الصمّامُ مفعّلٌ افتراضياً — خرقُ D1: ميزةٌ بلا دليلٍ حيّ تُصدِر "
            "رموزاً جمركية لكلّ مستخدم عند الدمج")
        for on in ("1", "true", "yes", "on"):
            os.environ["SILK_HS_ATTRIBUTE_RESOLVE"] = on
            assert A.enabled() is True, f"لم يُفعَّل بـ{on!r}"
        for off in ("0", "false", "no", "off", "", "maybe"):
            os.environ["SILK_HS_ATTRIBUTE_RESOLVE"] = off
            assert A.enabled() is False, f"فُعِّل بقيمةٍ ليست تفعيلاً: {off!r}"
        # ومُطفأً: لا حسمَ إطلاقاً مهما كانت القراءةُ صالحة.
        os.environ.pop("SILK_HS_ATTRIBUTE_RESOLVE", None)
        out = A.resolve_by_attribute(
            "منتجٌ ما", [{"hs6": c} for c in
                        ("040110", "040120", "040140", "040150")],
            label_attributes=[{"name": A.dimension_terms("fat")[0],
                               "value": 3.5, "unit": "%"}],
            allow_web=False)
        assert out["hs6"] is None and out["resolved_from"] is None
    finally:
        if saved is None:
            os.environ.pop("SILK_HS_ATTRIBUTE_RESOLVE", None)
        else:
            os.environ["SILK_HS_ATTRIBUTE_RESOLVE"] = saved


def _guard_cross_basis_edge_refusal():
    """D2 — قراءةٌ بأساسِ نسبةٍ مخالف قربَ حافّة لا تحسم. `g/100ml` كتلة/حجم
    بينما نصّ HS «by weight» كتلة/كتلة؛ الفارقُ ~٣٪ نسبيّاً (~٠٫١٨ عند حدّ
    ٦٫٠) — يكفي لعبور الحدّ، فتُلتَفّ صرامةُ G1 من هذا الباب الواحد."""
    import silk_hs_attributes as A
    saved = os.environ.get("SILK_HS_ATTRIBUTE_RESOLVE")
    os.environ["SILK_HS_ATTRIBUTE_RESOLVE"] = "1"
    try:
        d = A.discriminator([{"hs6": c} for c in
                             ("040110", "040120", "040140", "040150")])
        assert d is not None
        assert A.band_basis(d["bands"][0]) == "mm", "أساسُ النطاق لم يُقرأ"
        for v in (5.9, 6.0, 6.1):          # داخل ٠٫٥ من حدّ ٦٫٠
            assert A.select_by_value(d, v, "g/100ml") is None, (
                f"{v} g/100ml حُسِمت قربَ حافّة رغم مخالفة الأساس")
        assert A.select_by_value(d, 3.5, "g/100ml") == "040120"   # بعيدةٌ
        for same in ("%", "g/100g", "% w/w"):                     # نفسُ الأساس
            assert A.select_by_value(d, 5.9, same) == "040120", same
        # وكلُّ مدخلٍ مخالفِ الأساس في الجدول محروسٌ فعلاً (لا بابَ جديد).
        cross = {u for u in A._UNIT_FAMILY
                 if A.cross_basis_conflict(u, d["bands"])}
        assert cross >= {"g/100ml", "gm/100ml", "mg/100ml", "ml/100ml"}, cross
    finally:
        if saved is None:
            os.environ.pop("SILK_HS_ATTRIBUTE_RESOLVE", None)
        else:
            os.environ["SILK_HS_ATTRIBUTE_RESOLVE"] = saved
    _needles("silk_hs_attributes.py", "def cross_basis_conflict",
             "def near_any_edge", "_UNIT_BASIS", "_EDGE_MARGIN")()


def _dialog_band_numbers(band: dict) -> list[str]:
    """أرقامُ النطاق كما يجب أن تظهر — مشتقّةٌ من **المُحلِّل** لا من المُصيِّر
    المُختبَر، فالتأكيدُ ليس دائرياً."""
    unit = band.get("unit") or ""
    out = []
    for v in (band.get("lo"), band.get("hi")):
        if v is None:
            continue
        out.append(f"{int(v) if float(v).is_integer() else v}{unit}")
    return out


def _guard_dialog_band_text_from_the_official_reference_only():
    """البند ٧٢ — نصُّ الحدّ المعروض مشتقٌّ من المرجع الرسميّ حصراً.

    الحادثة: نثرُ نموذجٍ وقتَ الطلب كان يغلب الوصفَ الرسميّ بالتداخل اللفظيّ،
    فعُرِض على التاجر حدٌّ **يناقض** بندَه (`040110` بوصف «لا تتجاوز 6%»
    وبندُه ≤١٪)، ورمزٌ لا وجودَ له في المرجع (`040190`). الحارسُ سلوكيّ: يمرّ
    نثراً مناقضاً عبر نقطة الاختناق ويقرأ الناتج، ثم يكنس **كلّ** بندٍ ذي
    نطاقٍ في `data/hs_reference.csv` لا عيّنة."""
    import silk_hs_attributes as attrs
    import silk_hs_dialog as dialog
    from silk_hs_resolver import load_hs_reference, official_description

    contradicting = {
        "040110": "نسبة الدهن لا تتجاوز 6%",
        "040120": "نسبة الدهن تتجاوز 6%",
        "040190": "حليب وقشطة أخرى",
    }
    rows = dialog.build_candidates(
        "حليب نادك كامل الدسم", list(contradicting), contradicting)
    shown = {r["hs6"] for r in rows}
    assert "040190" not in shown, "رمزٌ مجهولٌ للمدوّنتين عُرِض على التاجر"
    # والنفيُ المقابل: نقصُ نسختنا من المرجع ليس سقفاً — بندٌ حقيقيٌّ تعرفه
    # البذرةُ وحدها يُعرَض، بلا نصٍّ مُختلَق (اللائحة ٣٩ من طرفها المقابل).
    from silk_hs_resolver import load_hs_codes
    # البذرة القديمة صراحةً: قائمة المطابقة المرحَّلة (hscodes_full) مشتقّةٌ
    # من المرجع الرسمي فلا فجوة فيها — الفجوة الحقيقية (١٣ رمزاً أعاد
    # HS2022 ترقيمها) باقيةٌ في data/hs_codes.csv (docs/DECISIONS.md).
    seed_only = sorted({r["hs_code"]
                        for r in load_hs_codes("data/hs_codes.csv")}
                       - set(load_hs_reference()))
    assert seed_only, "لا فجوةَ بين المدوّنتين — الحارسُ فقد موضوعَه"
    kept = {r["hs6"]: r for r in dialog.build_candidates("—", seed_only)}
    assert set(seed_only) <= set(kept), (
        f"بنودٌ حقيقيةٌ سقطت لنقصِ نسختنا: {set(seed_only) - set(kept)}")
    assert all(kept[c]["description_ar"] == "" for c in seed_only), (
        "نصٌّ غيرُ رسميٍّ سدّ فراغَ الوصف")
    assert {"040110", "040120", "040140", "040150"} <= shown, shown
    by_code = {r["hs6"]: r for r in rows}
    assert "6%" not in by_code["040110"]["band_ar"], (
        "حدُّ 040110 المعروض يناقض بندَه الرسميّ (≤١٪) — عودةُ الحادثة")
    for code, prose in contradicting.items():
        row = by_code.get(code)
        if row is None:
            continue
        assert row["description_ar"] == official_description(code), (
            f"{code}: الوصفُ المعروض ليس الوصفَ الرسميّ حرفياً")
        assert prose not in row["band_ar"], f"{code}: نثرُ نموذجٍ صار حدَّ بند"
        assert prose not in row["description_ar"], f"{code}: نثرٌ صار وصفاً"

    # كنسٌ كامل: كلُّ بندٍ ذي نطاقٍ في المرجع يُصيَّر بأرقام نطاقه هو.
    checked = 0
    for code in load_hs_reference():
        band = attrs.band_of(code)
        if band is None:
            continue
        text = dialog.band_text_ar(code)
        assert text, f"{code}: بندٌ ذو نطاقٍ بلا نصّ حدٍّ معروض"
        for needle in _dialog_band_numbers(band):
            assert needle in text, (
                f"{code}: النصُّ «{text}» لا يحمل حدَّ المرجع {needle}")
        checked += 1
    assert checked >= 380, f"الكنسُ لم يشمل المرجعَ فعلياً: {checked}"
    _needles("silk_hs_dialog.py", "def build_candidates", "def band_text_ar",
             "def official_text", "def in_official_reference")()
    # ولا مُصيِّرَ ثانٍ: كلُّ منتجٍ لقائمة الحوار يمرّ بنقطة الاختناق.
    _needles("silk_hs_classifier.py", "silk_hs_dialog")()
    _needles("silk_hs_confirm.py", "silk_hs_dialog")()


def _guard_dialog_axis_siblings_never_partial():
    """البند ٧٣ — لا تُعرَض مجموعةٌ جزئيةٌ من محورٍ رقميّ.

    الحادثة: سقط `040140`/`040150` من القائمة فلم يجد منتجٌ كامل الدسم خياراً
    صحيحاً أصلاً — فيختار التاجر أقربَ المعروض ويخرج برمزٍ **خاطئ بلا إشارة**.
    السببُ مركّب: فجوةُ بذرةٍ (٨ من ٣٩٣ بنداً فقط قابلةٌ للبلوغ باسمٍ عربيّ)
    مضروبةٌ في اقتطاعٍ صلبٍ إلى ثلاثة في الخادم وفي الواجهة معاً.

    الحارسُ خاصّيّ على **كامل** المرجع: أيُّ عضوٍ من أيّ مجموعةِ محورٍ يُدخَل
    وحدَه يُخرِج المجموعةَ كاملة."""
    import collections
    import silk_hs_attributes as attrs
    import silk_hs_dialog as dialog
    from silk_hs_resolver import load_hs_reference

    groups: dict = collections.defaultdict(list)
    for code in load_hs_reference():
        band = attrs.band_of(code)
        if band is not None:
            groups[(code[:4], band["axis"])].append(code)
    families = {k: sorted(v) for k, v in groups.items() if len(v) >= 2}
    assert len(families) >= 60, f"مجموعاتُ المحاور تبدو مبتورة: {len(families)}"

    covered = 0
    for members in families.values():
        for member in members:
            shown = [r["hs6"] for r in dialog.build_candidates("—", [member])]
            missing = [m for m in members if m not in shown]
            assert not missing, (
                f"{member}: أشقّاءُ المحور غائبون عن الحوار {missing}")
            covered += 1
    assert covered >= 150, f"الكنسُ لم يشمل المجموعاتِ فعلياً: {covered}"
    # ولا اقتطاعَ في الواجهة يُعيد العطلَ بعد إصلاح الخادم.
    _absent("web/index.html", "cands.slice(0,3)", "cands.slice(0, 3)")()
    _needles("web/index.html", "c.band_ar")()
    # وحدُّ النطاق: الإكمالُ يصل الحوارَ ولا يصل المُحلِّلَ الرقميّ — وإلا
    # اتّسعت تغطيةُ الحسم من بابٍ خلفيّ (نهيُ المُشرِف الصريح).
    import silk_hs_attributes as _attrs
    import silk_hs_confirm as confirm
    rows = dialog.build_candidates("—", ["040110"])
    assert {r["hs6"] for r in rows if r["axis_completion"]} == {
        "040120", "040140", "040150"}, rows
    seen: dict = {}
    real = _attrs.resolve_by_attribute
    _attrs.resolve_by_attribute = (
        lambda p, c, **kw: (seen.setdefault("codes",
                                            [x.get("hs6") for x in c]),
                            real(p, c, **kw))[1])
    try:
        confirm.resolve_or_probe("—", rows, allow_web=False)
    finally:
        _attrs.resolve_by_attribute = real
    assert seen["codes"] == ["040110"], (
        f"المُحلِّلُ غُذّي بأشقّاءَ لم يطلبهم المستدعي: {seen['codes']}")


def _guard_dialog_prose_carries_no_product_brand_or_country():
    """البند ٧٤ — نثرُ الحوار وصفٌ رسميٌّ للبند، لا صدىً لِما كتبه التاجر.

    الحادثة: النصُّ المعروض حمل **اسمَ العلامة التجارية** داخل وصفٍ يُقدَّم
    بوصفه رسمياً («… حليب نادك كامل الدسم») — فيبدو الوصفُ مُصادِقاً على
    منتجِ التاجر بينما هو وصفُ بندٍ جمركيّ. عائلةُ اللائحة ٣٠ (لا منتجَ
    مثبَّتٌ في القوالب) من الطرف المقابل: لا منتجَ **مُقحَمٌ** في النثر."""
    import silk_hs_dialog as dialog

    product = "حليب نادك كامل الدسم"
    for prose, banned in (
            (f"وصفٌ عامّ لـ{product} من هولندا", ("نادك", "هولندا")),
            ("عبوة نادك المستوردة من هولندا وألمانيا",
             ("نادك", "هولندا", "ألمانيا")),
            ("Nadec milk from Netherlands", ("Netherlands",)),
    ):
        out = dialog.sanitize_prose(prose, product)
        for token in banned:
            assert token not in out, (
                f"«{token}» نجا في نثر الحوار: {out!r} — عودةُ الحادثة")

    rows = dialog.build_candidates(
        product, ["040110", "040120"],
        {"040110": f"يناسب {product}", "040120": "قشطة من هولندا"})
    assert rows, "نقطةُ الاختناق لم تُخرِج شيئاً"
    for row in rows:
        for token in ("نادك", "هولندا"):
            assert token not in row["reason_ar"], (
                f"{row['hs6']}: «{token}» وصل نثرَ الحوار عبر نقطة الاختناق")
    _needles("silk_hs_dialog.py", "def sanitize_prose", "_AR_CLITICS",
             "def _country_terms")()


def _guard_borrowed_visual_identity():
    """LESSONS ٩٣ — لوحة المصانع كانت تعمل بألوان Stripe الحرفية
    (`--pri:#635BFF`، `--ink:#1A1F36`، `--line:#E3E8EE`) وحارسُ الألوان أخضرُ
    طوال الوقت: كان يسأل «هل تطابق الصفحةُ `config/branding.yaml`؟» ولا يسأل
    قطّ «من أين جاءت هذه القيم؟». فكفى أن تُكتَب ألوانُ طرفٍ ثالث في ملفّ
    الهوية لتصير «هويتنا» ميكانيكياً — المطابقةُ آليةُ **مزامنة** لا آليةُ
    **مِلكية**.

    الحارس السلوكي (لا يعتمد على نصّ الحارس الآخر):
      (١) لا لونَ من لوحة طرفٍ ثالث معروفة في أيّ صفحة ويب — بالاسم؛
      (٢) ولا في `config/branding.yaml` نفسه، وإلا عادت الثغرة من مصدرها؛
      (٣) وكلّ مفتاح `dashboard_*` في الملف حاضرٌ فعلاً في صفحة الداشبورد
          (المزامنة تبقى قائمة إلى جانب المِلكية)."""
    root = pathlib.Path(__file__).resolve().parent.parent
    # لوحة Stripe الحرفية — القيم التي شُحنت فعلاً في الحادثة.
    third_party = ("#635BFF", "#4F46E5", "#1A1F36", "#E3E8EE", "#D9D6FE",
                   "#F4F3FF")
    for page in ("platform.html", "platform-landing.html", "checkout.html",
                 "reset-password.html", "index.html"):
        text = (root / "web" / page).read_text(encoding="utf-8")
        for hexv in third_party:
            assert hexv not in text, (
                f"{page}: لون طرفٍ ثالث ({hexv}) عاد إلى المنتج — "
                "الهوية المستعارة (الدرس ٩٣)")
    brand = (root / "config" / "branding.yaml").read_text(encoding="utf-8")
    brand_values = []
    for line in brand.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            brand_values.append(line.split(":", 1)[1].strip().upper())
    for hexv in third_party:
        assert hexv.lstrip("#") not in brand_values, (
            f"branding.yaml: {hexv} صار قيمةَ هوية رسمية — "
            "الثغرة تعود من مصدرها لا من الصفحة (الدرس ٩٣)")
    # المزامنة باقية: كلّ درجة داشبورد معلَنة في الملف موجودة في الصفحة.
    page = (root / "web" / "platform.html").read_text(encoding="utf-8")
    keys = [ln.split(":", 1) for ln in brand.splitlines()
            if ln.strip().startswith("dashboard_")]
    assert keys, "مفاتيح dashboard_* اختفت من ملفّ الهوية"
    for k, v in keys:
        v = v.split("#", 1)[0].strip()
        assert f"#{v}" in page, (
            f"{k.strip()} ({v}) في ملفّ الهوية ولا أثر له في الصفحة")


def _guard_gate_passes_synthetic_but_silent_on_real():
    """LESSONS ٧٥ — بوّابةُ A3 (TAM أصغر من تدفّق دولةٍ واحدة) شُحنت في PR A
    باختباراتٍ تركيبية خضراء ثم **لم تُطلِق على تحليل ٧ الحيّ** — الحالة التي
    بُنيت لها بالضبط: الكاتبُ كتب TAM بصيغة رمز `$` (`2,090,000$`) بينما اشترط
    التطابقُ لفظَ «دولار». الحارس السلوكي على مدوّنة تحليل ٧ الحقيقية الشكل
    (`tools/canonical_nadec_yemen_dairy.py`، مُمرَّرة عبر `build_view`):
      (١) البوّابات الثلاث تُطلِق فعلاً (A3 صيغة `$` + سردُ المرآة + تصعيدُ
          التقادُم) والحكمُ الكلّي FAIL؛
      (٢) المستخلِص يلتقط صيغة الرمز `$` (سبب الصمت القديم)؛
      (٣) العيّنة النظيفة (الكويت) لا تُطلِق أياً منها (لا إيجابٌ كاذب)."""
    import silk_render as R
    import silk_quality_gate as QG
    from tools.canonical_nadec_yemen_dairy import nadec_yemen_research_blob
    from tools.canonical_kuwait_peanut_butter import kuwait_research_blob
    view = R.build_view(nadec_yemen_research_blob())
    dr = view["deep_research"]
    # (١) البوّابات الأربع تُطلِق + FAIL كلّي (بلاغ المالك: قلبُ إشارة CAGR
    # بسنة الأساس المرصودة أُضيف بعد مِجَسّ /trend الحيّ — أساس 2018 نموّ مقابل
    # أساس 2019 انكماش على نفس سلسلة 040110).
    assert QG._check_tam_below_single_country_flow(dr)
    assert QG._check_mirror_divergence_contraction_narrative(dr)
    assert QG._check_stale_year_driving_conclusion(dr)
    assert QG._check_cagr_sign_flips_under_base_year(dr)
    out = QG.run_quality_gate(view)
    assert out["verdict"] == QG.FAIL
    fired = {f["check"] for f in out["findings"]}
    assert {"tam_below_single_country_flow",
            "mirror_divergence_contraction_narrative",
            "stale_year_driving_conclusion",
            "cagr_sign_flips_under_base_year"} <= fired
    # (٢) صيغةُ الرمز `$` محفوظةٌ بعد التطهير + المستخلِص يلتقطها.
    txt = (dr.get("report") or {}).get("text") or ""
    assert "2,090,000$" in txt
    assert 2_090_000 in [round(v) for _, _, v in QG._iter_usd_amounts(txt)]
    # (٣) العيّنة النظيفة لا تُطلِق أياً من البوّابات الثلاث.
    kdr = R.build_view(kuwait_research_blob())["deep_research"]
    assert not QG._check_tam_below_single_country_flow(kdr)
    assert not QG._check_mirror_divergence_contraction_narrative(kdr)
    assert not QG._check_stale_year_driving_conclusion(kdr)
    # (٤) الثلاث بنودُ فشلٍ حاجبة + قفلُ الانحدار موجود.
    for c in ("tam_below_single_country_flow",
              "mirror_divergence_contraction_narrative",
              "stale_year_driving_conclusion",
              "cagr_sign_flips_under_base_year"):
        assert c in QG.FAIL_TRIGGER_CHECKS
    assert _exists("tests/test_gate_regression_locks_analysis7.py")
    assert _exists("tools/canonical_nadec_yemen_dairy.py")


def _guard_paid_limit_lock_is_load_bearing():
    """LESSONS ٧٦ — اختبارُ تزامنٍ اجتاز شيفرةً **غير ذرّية** فبدا حارساً وهو خامل.

    الحادثة وقعت على مسار إعادة تنشيط المستخدم (بوّابة المقاعد، PR-2): فحصٌ
    ثمّ تحديث بلا قفلٍ فوري، فطلبان متوازيان يمرّان معاً ويكتبان ⇒ تجاوزُ سقفٍ
    مدفوع. التقطته المراجعة الذاتية (§58)، لكن **اختبارَ الحاجز الأوّل اجتاز
    النسخة المعطوبة**: القسمُ الحرج أقصر من ميلي ثانية فتسلسلَ الخيطان بحكم GIL.

    **المقاعد نفسها حُذفت نهائياً بقرار المالك 2026-08-19** (حسابٌ واحد لكل
    مصنع، حارسها `tests/test_platform_seats_deletion_guard.py`) — فمرساة هذا
    البند انتقلت إلى المسار المدفوع الباقي: الخصم المقيس. **القاعدة لم تتغيّر**:
    كل مسارٍ يستهلك حدّاً مدفوعاً (حصّة/رصيد) يفتح معاملة كتابة فورية **قبل**
    فحصه، ويُوسَّع نافذةُ فحصه في الاختبار وإلا اجتاز كودٌ غير ذرّي بصمت.
    The seats died; the rule and its widened-window discipline did not.
    """
    # **الشكل التنفيذي وحده يُحتسَب** — ذكرُ «BEGIN IMMEDIATE» في شرحٍ ليس قفلاً.
    _LOCK = 'conn.execute("BEGIN IMMEDIATE")'
    bill = _read("silk_platform/billing.py")
    assert _LOCK in bill, (
        "silk_platform/billing.py: فحص الخمول والخصم يجب أن يتشاركا معاملة كتابة "
        "فورية فعلية — بلا ذلك تخصم نقرتان متزامنتان مرّتين على مفتاح واحد")

    tests = _read("tests/test_platform_concurrency.py")
    assert "def _widen_charge_check_window" in tests, (
        "tests/test_platform_concurrency.py: _widen_charge_check_window محذوف — "
        "بدونه يجتاز كودٌ غير ذرّي اختبارَ التزامن (أخضر فارغ)")
    name = "test_concurrent_metered_charges_on_one_key_charge_exactly_once"
    assert name in tests, f"اختبار قفل حدٍّ مدفوع مفقود: {name}"
    body = tests.split(f"def {name}(")[1].split("\ndef ")[0]
    assert "_widen_charge_check_window" in body, (
        f"{name}: لا يُوسِّع نافذة الفحص ⇒ قد يجتاز شيفرةً غير ذرّية")
    # وحدةُ المقاعد يجب ألا تعود من الباب الخلفي عبر هذا الحارس.
    # (المرساة من جذر المستودع لا من مجلّد العمل — فحصٌ نسبيّ كان يمرّ من
    #  `/tmp` مهما كان الملفّ موجوداً: حارسٌ خامل. ملاحظة مراجعة §58.)
    assert not _exists("silk_platform/users.py"), (
        "silk_platform/users.py عادت — المقاعد محذوفة بقرار مالك 2026-08-19")


def _guard_readiness_names_the_offending_variable():
    """LESSONS ٧٧ — أداةُ تشخيصٍ أبلغت بالفشل وحجبت سببَه.

    `readiness()` شُحن في #197 لينهي «الدخول مستحيلٌ بلا تفسير»، ثم ضبط المالك
    البوّابةَ وظلّ الدخول يُرفَض: كلمتُه خالفت السياسة، فرفع التلبيد، فابتلعه
    الإقلاع صواباً، فبقيت القاعدة بصفر مستخدمين — والجهوزيّة قالت `seeded:false`
    مع `seed_gate_set:true` **بلا سبب**، فصمتت عند السؤال الوحيد المهم.

    الحارس يحمي ثلاثة أشياء معاً:
      (١) الحقلُ `seed_error` قائمٌ في الجهوزيّة (لا عودةَ إلى «فشلٌ بلا سبب»)؛
      (٢) الرفضُ يقع **قبل** المحاولة (`seed_problem()` في `maybe_seed`) كي
          تسمّي الرسالةُ المتغيّرَ المخالف بعينه لا الكلمةَ السليمة؛
      (٣) لا قيمةَ كلمةِ مرورٍ في أيّ مخرَج — تُنشَر الأسماءُ والقواعد فقط.
    """
    src = _read("silk_platform/bootstrap.py")
    for needle in ("def seed_problem", '"seed_error"', "validate_policy"):
        assert needle in src, (
            f"silk_platform/bootstrap.py: {needle} محذوف — الجهوزيّة تعود "
            "تُبلِّغ بالفشل بلا سببه، وهو العجزُ الذي وُجدت لإلغائه")
    # الرفضُ المسبق: `seed_problem()` مستدعًى داخل `maybe_seed` نفسه، لا في
    # الجهوزيّة وحدها — فبلا ذلك يعود السجلّ إلى «فشل» بلا اسم متغيّر.
    body = src.split("def maybe_seed(")[1]
    assert "seed_problem()" in body, (
        "silk_platform/bootstrap.py: `maybe_seed` لا يرفض مسبقاً ⇒ رسالةُ "
        "السجلّ تعود بلا اسم المتغيّر المخالف")
    # لا تُطبَع قيمةُ أيّ متغيّر بذر — الأسماءُ فقط (`/health` عامّة).
    assert "os.environ.get(env" in src or "_IDENTITY_ENV" in src, (
        "silk_platform/bootstrap.py: أسماءُ متغيّرات البذر لم تبقَ بياناتٍ "
        "واحدةَ المصدر")
    tests = _read("tests/test_platform_bootstrap.py")
    for name in ("test_a_policy_violating_seed_password_is_named_in_readiness",
                 "test_readiness_never_leaks_the_seed_password_value",
                 "test_a_bad_optional_password_names_that_variable_not_the_admin",
                 "test_the_policy_refusal_logs_the_variable_name_and_not_its_value",
                 "test_the_platform_prefix_leads_to_the_page_not_a_bare_404"):
        assert f"def {name}" in tests, f"قفلُ تشخيصٍ مفقود: {name}"
    # والبادئة تقود إلى الصفحة — المالك فتح `/platform` فرأى 404 بصيغة JSON.
    # **يُفحَص تسجيلُ المسار نفسه** لا اسمُ الدالّة: الفحص الأوّل كان على «def
    # platform_root»، فتعطيلُ المعالج بإعادة تسميته `platform_root_DISABLED`
    # يُبقي النصَّ الفرعيّ حاضراً ⇒ يجتاز الحارسُ مساراً محذوفاً. نفسُ ثقب
    # النصّ الفرعيّ المعروف، أُغلق هنا بفحص المُزخرِف والهدف معاً.
    api_src = _read("silk_platform/api.py")
    assert "@app.get(_PREFIX)\n" in api_src, (
        "silk_platform/api.py: لا مسارَ مسجَّلاً على البادئة المجرّدة ⇒ "
        "`/platform` يعود 404 بصيغة JSON فيتكرّر لبسُ المالك")
    assert 'RedirectResponse("/platform.html"' in api_src, (
        "silk_platform/api.py: البادئة لا تُحوِّل إلى الصفحة فعلاً")


def _guard_platform_studies_run_the_deep_engine():
    """LESSONS ٧٨ — سطحُ منتجٍ بِيع «دراسةً» وهو موصولٌ بالمسار السريع.

    شكوى المالك (2026-08-18): دراسة المنصّة تكتمل في ٦–٨ ثوانٍ («المدة: 8 ث»)
    بينما المحرّك الحقيقي يحتاج ~١٥ دقيقة — الجسر كان يشغّل `analyze` داخل
    `block_ai_extras()` فلا بعثة واحدة تُطلَق. الحارس يحمي أربعة أشياء معاً:
      (١) الافتراضي `deep` — `study_mode` لا يعود `quick` إلا بضبطٍ صريح؛
      (٢) لا تدهور صامتاً: غيابُ البوّابة يرفع `DeepRunRefused` بسببٍ معلَن،
          لا سقوطاً إلى `analyze` السريع؛
      (٣) بوّابة الإطلاق ترفض قبل المطالبة والحصّة (`engine_not_ready`)؛
      (٤) الجذر يسجّل البوّابة وقت الإقلاع (مسارٌ واحد لا خطّ أنابيب موازٍ).
    """
    bridge = _read("silk_platform/engine_bridge.py")
    for needle in ("def study_mode", 'return "quick" if raw == "quick" else "deep"',
                   "class DeepRunRefused", "def _run_engine_deep",
                   "raise DeepRunRefused"):
        assert needle in bridge, (
            f"silk_platform/engine_bridge.py: {needle} محذوف — دراسة المنصّة "
            "تعود «٨ ثوانٍ» بلا محرّك حقيقي (LESSONS ٧٨)")
    # لا سقوط صامتاً: الفرع العميق لا يستدعي analyze إطلاقاً.
    deep_body = bridge.split("def _run_engine_deep(")[1].split("\ndef ")[0]
    assert "silk_engine" not in deep_body and "analyze(" not in deep_body, (
        "الفرع العميق يلمس analyze — عودة التدهور الصامت (LESSONS ٧٨)")
    papi = _read("silk_platform/api.py")
    assert '"error": "engine_not_ready"' in papi, (
        "بوّابة engine_not_ready محذوفة من مسار الإطلاق (LESSONS ٧٨)")
    root = _read("api.py")
    assert "silk_research_gateway.register" in root, (
        "api.create_app لا يسجّل بوّابة البحث العميق — الجسر بلا محرّك "
        "(LESSONS ٧٨)")


def _guard_refused_launch_hands_back_a_way_out():
    """LESSONS ٧٩ — بوّابةٌ ترفض يجب أن تُسلّم مخرجاً، ورفضٌ صامت ممنوع.

    شكوى المالك (2026-08-19) بعد شحن المسار العميق بيومين: «المحرّك لا يعمل».
    إعادةُ إنتاج محلية بمنتجه («حليب»/عُمان): الإطلاق ينجح ثم يرتدّ في ٠٫٦ث
    ببوّابة تمايز البند الجمركي «اختر البند المطابق أدناه» — والمرشّحون
    يُفقَدون عند حدّ الجسر فلا «أدناه» في أي شاشة، والاختيارُ اليدوي يُرفَض
    ثانيةً لأن `hs_confirmed` لم يكن يُمرَّر. الحارس يحمي أربعة أشياء:
      (١) الجسر يستخرج المرشّحين من حمولة الرفض ويحفظهم على الصفّ؛
      (٢) الاختيار يُمرَّر تأكيداً صريحاً حتى `ResearchRequest`؛
      (٣) كل رفض إطلاقٍ يترك أثراً مقروءاً (`_refuse_launch`)؛
      (٤) الواجهة تعرض المرشّحين فعلاً (زرّ الاختيار موجود).
    """
    bridge = _read("silk_platform/engine_bridge.py")
    # ورمزُ المحاولة: كلُّ إنهاءٍ مملوكٌ لصاحبه، فلا يكتب خيطٌ مكنوس على
    # إطلاقةٍ جديدة (ملاحظة المراجعة الذاتية §58 على هذه الموجة نفسها).
    assert "AND (? IS NULL OR run_token = ?)" in bridge, (
        "إنهاءُ التشغيلة غير مقيَّد برمز محاولته — خيطُ تشغيلةٍ مكنوسة يكتب "
        "نتيجتَه على إطلاقةٍ جديدة (LESSONS ٧٩)")
    for needle in ("def _detail_candidates", "hs_candidates = ?",
                   "def _empty_reason", "candidates=_detail_candidates"):
        assert needle in bridge, (
            f"silk_platform/engine_bridge.py: {needle} محذوف — الرفض يعود "
            "نصّاً بلا مخرج (LESSONS ٧٩)")
    papi = _read("silk_platform/api.py")
    assert "def _refuse_launch" in papi, (
        "رفضُ الإطلاق عاد صامتاً بلا أثرٍ على الصفّ (LESSONS ٧٩)")
    assert "hs_confirmed=bool(study.get(" in papi, (
        "اختيارُ المصنع لبنده لا يُمرَّر للجسر — الحلقة تُغلق عليه ثانيةً "
        "(LESSONS ٧٩)")
    root = _read("api.py")
    assert "hs_confirmed=bool(hs_confirmed)" in root, (
        "المغلقة لا تمرّر التأكيد إلى ResearchRequest (LESSONS ٧٩)")
    page = _read("web/platform.html")
    # قرارُ المالك (2026-08-29) بدّل **شكلَ المخرج** لا القاعدة: لا قائمةَ
    # مرشّحين تُعرَض على المصنع ولا رقمَ ثقة؛ المخرجُ كتابةُ الرمز أو رفعُ
    # صورةٍ تُحسَمه. القاعدةُ («رفضٌ بلا مخرجٍ طريقٌ مسدود») تُحرَس على
    # المخرج الجديد، ويُمنَع رجوعُ القديم صراحةً كي لا يُعاد بناؤه سهواً.
    for needle in ("function classifyImageBtn(p)",
                   '"/products/" + p.id + "/classify-image"',
                   "أدخل رمز HS"):
        assert needle in page, (
            f"web/platform.html: {needle} محذوف — رفضُ البند بلا مخرج "
            "(LESSONS ٧٩)")
    for gone in ("function hsPickBtn", 'name="hs_pick"'):
        assert gone not in page, (
            f"web/platform.html: {gone} عاد — المصنع لا يُعرَض عليه خيارٌ "
            "ليختار (قرار المالك 2026-08-29)")


def _guard_golden_set_is_load_bearing():
    """LESSONS ٨٠ — المجموعة الذهبية حارسٌ حاجب لا زينة.

    (١) الأداة تحمل الحالات الخمس وبصمة المؤشرات الخمسة ووسم BLOCKING؛
    (٢) خطوط الأساس الخمسة ملتزَمة فعلاً؛
    (٣) اختبار المطابقة الحيّ موجود فلا يمكن حذف المقارنة بصمت.
    """
    tool = _read("tools/golden_set.py")
    for needle in ("def snapshot", "def compare_case", "GOLDEN_CASES",
                   "unsupported_report_numbers", "BLOCKING: verdict changed"):
        assert needle in tool, (
            f"tools/golden_set.py: {needle} محذوف — المجموعة الذهبية بلا "
            "مقارنة حاجبة (LESSONS ٨٠)")
    import re as _re
    keys = _re.findall(r'^\s{4}"([a-z_]+)":', tool, _re.M)
    assert len(keys) == 5, f"عدد حالات المجموعة الذهبية ≠ ٥: {keys}"
    for key in keys:
        assert _exists(f"evals/golden_set/{key}.json"), (
            f"خط أساس المجموعة الذهبية مفقود: evals/golden_set/{key}.json "
            "(LESSONS ٨٠)")
    tests = _read("tests/test_golden_set.py")
    assert "test_current_generation_matches_committed_baselines" in tests, (
        "اختبار مطابقة المجموعة الذهبية محذوف (LESSONS ٨٠)")


def _guard_gap_recovery_layer_contracts():
    """LESSONS ٨١ — طبقة سد الفجوات: قيود الأمر التنفيذي محروسة بنيوياً.

    (١) الصمّام مُطفأ افتراضياً (`"0"` هو الافتراضي)؛
    (٢) OPS يُسجَّل للمشغّل ويُحذف من مسار العميل؛
    (٣) النداء في api.py محاط بـtry/except (لا حجب)؛
    (٤) السقوف الثلاثة موجودة بأسمائها.
    """
    src = _read("silk_gap_recovery.py")
    assert 'os.environ.get(FLAG, "0")' in src, (
        "صمّام طبقة سد الفجوات لم يعد مُطفأً افتراضياً (LESSONS ٨١/٧٠)")
    for needle in ("record_service_failure", "SILK_GAP_MAX_ATTEMPTS",
                   "SILK_GAP_MAX_WEB_SEARCH", "SILK_GAP_TIMEOUT_S",
                   "def classify", "FALLBACK_ROUTES"):
        assert needle in src, (
            f"silk_gap_recovery.py: {needle} محذوف (LESSONS ٨١)")
    api = _read("api.py")
    assert "silk_gap_recovery.recover(" in api, (
        "طبقة سد الفجوات غير موصولة بمسار /research (LESSONS ٨١)")
    tests = _read("tests/test_gap_recovery.py")
    assert "test_disabled_by_default_and_output_is_untouched" in tests, (
        "اختبار الإطفاء=ناتج مطابق محذوف (LESSONS ٨١)")


def _guard_source_contract_and_vintage_tiers():
    """LESSONS ٨٢ — عقد المصدر الإضافي + القِدم بطبقتين.

    (١) حقول DataPoint الأربعة الجديدة بقيم افتراضية؛
    (٢) الرابط من السجلّ العمومي حصراً (datapoint_provenance)؛
    (٣) طبقتا القِدم 3/7 مع توافق SILK_STALE_DATA_YEARS؛
    (٤) الفحصان الجديدان خارج FAIL_TRIGGER_CHECKS (لا حجب — قرار مالك).
    """
    dl = _read("silk_data_layer.py")
    for needle in ('unit: str = ""', 'url: str = ""',
                   'reference_period: str = ""', 'retrieval_method: str = ""',
                   "def fact_to_datapoint", "def datapoint_provenance",
                   "def classify_gap_class"):
        assert needle in dl, f"silk_data_layer.py: {needle} محذوف (LESSONS ٨٢)"
    st = _read("silk_staleness.py")
    for needle in ("def vintage_tier", "def vintage_caveat",
                   "SILK_VINTAGE_WARN_YEARS", "SILK_VINTAGE_HARD_YEARS",
                   "SILK_STALE_DATA_YEARS"):
        assert needle in st, f"silk_staleness.py: {needle} محذوف (LESSONS ٨٢)"
    qg = _read("silk_quality_gate.py")
    for needle in ("def _check_source_contract_completeness",
                   "def _check_vintage_expired_facts"):
        assert needle in qg, f"silk_quality_gate.py: {needle} محذوف (LESSONS ٨٢)"
    import silk_quality_gate as _Q
    assert "source_contract_incomplete" not in _Q.FAIL_TRIGGER_CHECKS
    assert "vintage_expired_facts_present" not in _Q.FAIL_TRIGGER_CHECKS


def _guard_canonical_economics_arithmetic():
    """LESSONS ٨٣ — الحساب الموحّد: مقياس HHI الواحد + المعادلة الواحدة."""
    ec = _read("silk_economics.py")
    for needle in ("def hhi", "def hhi_from_fractions", "def landed_cost",
                   "HHI_HIGH_CONCENTRATION = 2_500", "HHI_SCALE_MAX = 10_000"):
        assert needle in ec, f"silk_economics.py: {needle} محذوف (LESSONS ٨٣)"
    corr = _read("correlation.py")
    assert "from silk_economics import landed_cost" in corr, (
        "correlation.py انفصل عن المعادلة القانونية (LESSONS ٨٣)")
    # الموجة 2ب: مواقع النداء تحوّلت للمقياس الموحّد — لا عودة للازدواجية.
    rs = _read("silk_research.py")
    assert "from silk_economics import hhi" in rs and ">0.25" not in rs, (
        "silk_research عاد لمقياس 0–1 (LESSONS ٨٣/الموجة 2ب)")
    dc = _read("silk_decision.py")
    assert "hhi_is_high" in dc and "HHI_HIGH_CONCENTRATION" in dc, (
        "silk_decision عاد لعتبات 0–1 (LESSONS ٨٣/الموجة 2ب)")
    qg = _read("silk_quality_gate.py")
    for needle in ("def _check_hhi_scale", "def _check_cagr_recompute"):
        assert needle in qg, f"silk_quality_gate.py: {needle} محذوف (LESSONS ٨٣)"


def _guard_economics_engine_contracts():
    """LESSONS ٨٤ — المحرك الاقتصادي: تطبيع إلزامي، ثوابت بمصادرها،
    حلّ عكسي معلمَن، سؤال الإزاحة، وكل الفحوص تحذيرية."""
    ec = _read("silk_economics.py")
    for needle in ("class NormalizedPrice", "CONVERSION_REGISTRY",
                   "def convert_amount", "def normalize_price",
                   "def margin_waterfall", "def reverse_solve_max_exw",
                   "def economics_view", "PARAM_TAG"):
        assert needle in ec, f"silk_economics.py: {needle} محذوف (LESSONS ٨٤)"
    rep = _read("silk_reports.py")
    for needle in ("ECONOMICS_HEADING", "def _economics_md_lines",
                   "def _docx_economics_section"):
        assert needle in rep, f"silk_reports.py: {needle} محذوف (LESSONS ٨٤)"
    aj = _read("silk_ai_judge.py")
    assert "سؤال الإزاحة" in aj and "أقصى سعر مصنع قابل للمنافسة" in aj, (
        "كتلة الاقتصاد/سؤال الإزاحة محذوفة من برومبت الكاتب (LESSONS ٨٤)")
    import silk_quality_gate as _Q
    for name in ("economics_missing_despite_inputs",
                 "price_comparability_gaps", "generic_conversion_refusal"):
        assert name not in _Q.FAIL_TRIGGER_CHECKS, (
            f"فحص الموجة ٣ {name} صار حاجباً بلا قرار مالك (LESSONS ٨٤)")


def _guard_classification_derivation_and_lock():
    """LESSONS ٨٥ — سجلّ اشتقاق التصنيف الدائم + قفل اتساق الرمز."""
    rn = _read("silk_render.py")
    for needle in ("def _hs_derivation", '"hs_derivation"',
                   "substitution_note"):
        assert needle in rn, f"silk_render.py: {needle} محذوف (LESSONS ٨٥)"
    qg = _read("silk_quality_gate.py")
    for needle in ("def _check_hs_consistency_lock",
                   "def _check_spec_evidence_coherence"):
        assert needle in qg, f"silk_quality_gate.py: {needle} محذوف (LESSONS ٨٥)"
    import silk_quality_gate as _Q
    for name in ("hs_consistency_lock", "spec_evidence_coherence"):
        assert name not in _Q.FAIL_TRIGGER_CHECKS, (
            f"فحص الموجة ٤ {name} صار حاجباً بلا قرار مالك (LESSONS ٨٥)")


def _guard_verdict_structure_and_timeline():
    """LESSONS ٨٦ — القاعدة قبل الحكم + الحجة المضادة + جدول النفاذ."""
    dc = _read("silk_decision.py")
    for needle in ("def decision_rule_text", "def counter_case",
                   '"decision_rule": decision_rule_text()',
                   'out["counter_case"] = counter_case(out)'):
        assert needle in dc, f"silk_decision.py: {needle} محذوف (LESSONS ٨٦)"
    rep = _read("silk_reports.py")
    assert rep.count('ed.get("decision_rule")') >= 2, (
        "عرض القاعدة قبل الحكم اختفى من md/docx (LESSONS ٨٦)")
    assert "الحجة المضادة" in rep, "عرض الحجة المضادة محذوف (LESSONS ٨٦)"
    ra = _read("silk_requirements_agent.py")
    assert "def access_timeline" in ra, (
        "silk_requirements_agent.access_timeline محذوف (LESSONS ٨٦)")
    qg = _read("silk_quality_gate.py")
    assert "def _check_access_timeline_presence" in qg
    import silk_quality_gate as _Q
    assert "access_timeline_missing" not in _Q.FAIL_TRIGGER_CHECKS


def _guard_epistemic_register_and_failure_record():
    """LESSONS ٨٧ — طبقات الأدلة نحوياً + سجل الفشل الموحّد."""
    sc = _read("silk_style_contract.py")
    for needle in ("EPISTEMIC_VERB_RULE", "PARAMETER_VERBS",
                   "OBSERVED_VERBS", "INFERRED_VERBS"):
        assert needle in sc, f"silk_style_contract.py: {needle} محذوف (LESSONS ٨٧)"
    import silk_style_contract as _S
    assert _S.EPISTEMIC_VERB_RULE in _S.ACADEMIC_WRITER_CONTRACT
    assert _S.EPISTEMIC_VERB_RULE in _S.WRITER_STYLE_CONTRACT
    qg = _read("silk_quality_gate.py")
    for needle in ("def _check_epistemic_verb_discipline",
                   "def failure_record", '"failure_records"'):
        assert needle in qg, f"silk_quality_gate.py: {needle} محذوف (LESSONS ٨٧)"
    import silk_quality_gate as _Q
    assert "epistemic_verb_discipline" not in _Q.FAIL_TRIGGER_CHECKS



def _guard_one_gap_channel_for_every_verdict_surface():
    """LESSONS ٨٨ — سجلّ فجواتٍ واحد، مقامٌ لكل نسبة، وسنةٌ من المصدر."""
    render = _read("silk_render.py")
    assert "def verification_gap_line" in render, (
        "مُجمِّع سطر الفجوات الواحد حُذف — قناتا فجوات تعودان (LESSONS ٨٨)")
    assert "verification_gap_line(_jury, limits)" in render, (
        "سطر الكفاية لم يعد يُعاد بناؤه بعد اكتمال الحدود (LESSONS ٨٨)")
    assert "ليست إجمالي واردات السوق" in render, (
        "سطر المورّد فقد مقامه — قيمة مورّدٍ تُقدَّم إجماليَّ واردات")
    judge = _read("silk_ai_judge.py")
    assert "verification_gap_line" in judge, (
        "الكاتب عاد يقرأ قناة فجوات ثانية (LESSONS ٨٨)")
    # المرساة السابقة كانت `judge.split("_REPORT_SECTIONS")[-1]` — هشّةٌ لأنها
    # تفترض أن آخر ذكرٍ للرمز يسبق البرومبت مباشرةً؛ إضافةُ أي رمزٍ يحمل نفس
    # البادئة (`_REPORT_SECTIONS_EN` في الموجة ٠) تُزحزح نقطةَ القطع فيبتلع
    # الذيلُ تعليقاً يقتبس العبارةَ الممنوعة لتوثيق الحادثة. النيّة نفسها،
    # بمرساةٍ صحيحة: **الممنوع سلسلةٌ حيّة في البرومبت لا اقتباسٌ في تعليق** —
    # فتُجرَّد التعليقات قبل الفحص.
    _judge_code = "\n".join(
        ln for ln in judge.splitlines() if not ln.lstrip().startswith("#"))
    assert "(2023 هي الأحدث)" not in _judge_code, (
        "البرومبت عاد يتطوّع بسنةٍ «أحدث» فوق سنة الـDataPoint")
    store = _read("silk_store.py")
    assert "AND value IS NOT NULL" in store, (
        "get_indicator عاد يقبل صفّاً أحدث فارغ القيمة (LESSONS ٨٨)")
    gate = _read("silk_quality_gate.py")
    for fn in ("_check_sufficiency_contradiction", "_check_metric_value_conflict",
               "_check_lpi_year_mismatch"):
        assert f"def {fn}" in gate, f"حارس {fn} حُذف (LESSONS ٨٨)"


def _guard_classifier_needles_come_from_the_producer():
    """LESSONS ٨٩ — الإبر مستورَدة من المنتِج، والسطح الخام يصل المصنّف."""
    dl = _read("silk_data_layer.py")
    assert "RETRIEVAL_FAILURE_NEEDLES" in dl, (
        "قاموس نصوص الفشل المشترك حُذف — تعود الإبر المنسوخة (LESSONS ٨٩)")
    assert "أعاد خطأ API" in dl
    gr = _read("silk_gap_recovery.py")
    assert "RETRIEVAL_FAILURE_NEEDLES" in gr, (
        "مصنّف سد الفجوات عاد ينسخ إبره يدوياً (LESSONS ٨٩)")
    for needle in ("def _raw_failed_findings", "def _recover_tariff",
                   "_GAP_429_RE as _RATE_RE"):
        assert needle in gr, f"silk_gap_recovery: {needle} حُذف (LESSONS ٨٩)"
    assert '"التعرفة"' in gr, "مسار التعرفة الحتمي حُذف من سجل البدائل"


def _guard_typed_hs_code_answers_the_gate():
    """LESSONS ٩٠ — رمزٌ مكتوبٌ ضمن المرشّحين يمرّ، والمجسّ لا يستبدله."""
    c = _read("silk_hs_confirm.py")
    for needle in ("def _code_in_candidates", "def _norm_hs6",
                   "user_supplied: bool = False",
                   "if user_supplied and _code_in_candidates"):
        assert needle in c, f"silk_hs_confirm: {needle} حُذف (LESSONS ٩٠)"
    assert "if user_supplied and hs_code and _norm_hs6(" in c, (
        "المجسّ عاد يستبدل رمزَ المستخدم صامتاً (LESSONS ٩٠)")
    api = _read("api.py")
    # الدرس ١٢٠ شدّد الصيغة: التصريح صار عبر `_hs_user_supplied` (يميّز رمزَ
    # الكتالوج المُعاد عن اختيار الإنسان الحاضر) — العائلة نفسها، إنفاذٌ أدق.
    # موجةُ خطّ التصنيف (٢١٠) أضافت نقطةَ اختناقٍ تُصرّح بالمصدر نفسه، فصار
    # العددُ الصلب يُحمِّر على **إضافة** حارسٍ لا على غيابه. القفلُ أرضيّة.
    assert api.count("user_supplied=_hs_user_supplied(req)") >= 3, (
        "أحد مسارات الدخول الثلاثة لا يُصرّح بمصدر الرمز (الدرسان ٣٥/٣٧)")
    assert api.count("_classify_product_hs(") >= 3, (
        "مسارُ إنفاقٍ لا يمرّ بخطّ التصنيف الواحد (الدرس ٢١٠)")
    assert "def _hs_user_supplied" in api, (
        "دالة تمييز مصدر الرمز حُذفت (الدرس ١٢٠)")


def _guard_visible_layers_have_kill_switches():
    """LESSONS ٩١ — كل طبقة مرئية لها مفتاح إطفاء، افتراضه ON، موثّق."""
    render = _read("silk_render.py")
    assert "def layer_enabled" in render, "صمّام الطبقات حُذف (LESSONS ٩١)"
    for name in ("ECONOMICS_SECTION", "GAP_REGISTER", "VERDICT_STRUCTURE"):
        assert f'layer_enabled("{name}")' in render, (
            f"طبقة {name} بلا مفتاح إطفاء (LESSONS ٩١)")
    assert "def epistemic_rule" in _read("silk_style_contract.py")
    assert "epistemic_rule()" in _read("silk_ai_judge.py")
    env = _read(".env.example")
    for name in ("ECONOMICS_SECTION", "GAP_REGISTER", "VERDICT_STRUCTURE",
                 "EPISTEMIC_VERBS", "GAP_RECOVERY"):
        assert f"SILK_{name}_ENABLED" in env, (
            f"SILK_{name}_ENABLED غير موثّق — مفتاح مجهول ليس مخرجاً")


def _guard_client_reports_speak_plain_arabic():
    """LESSONS ٩٢ — لغة التاجر على سطح العميل، والمصطلحات لسطح المدقّق."""
    sc = _read("silk_style_contract.py")
    for needle in ("PLAIN_TERMS", "PLAIN_GLOSS", "KEEP_WITH_SHORT_DESC",
                   "PLAIN_LANGUAGE_RULE"):
        assert needle in sc, f"silk_style_contract: {needle} حُذف (LESSONS ٩٢)"
    assert sc.count("PLAIN_LANGUAGE_RULE") >= 3, (
        "قاعدة لغة التاجر لم تعد مُلحقةً بكلا عقدَي الكاتب (LESSONS ٩٢)")
    rep = _read("silk_reports.py")
    for needle in ("def _plain_language", "def _glossary_line",
                   "s = _plain_language(s)"):
        assert needle in rep, f"silk_reports: {needle} حُذف (LESSONS ٩٢)"
    assert "def _check_plain_language" in _read("silk_quality_gate.py")


def _guard_money_path_reads_the_source_it_shows():
    """LESSONS ٩٤ — سعرٌ معروضٌ غير السعر المُسجَّل.

    سلوكيّ لا نصّيّ: يضبط سعر باقةٍ من نقطة الأدمِن، ثم يطلب اشتراكاً، ثم
    يقارن `price_sar` في قيد التدقيق بما يعرضه `GET /platform/pricing`.
    الحارس النصّي وحده لا يكفي هنا — العطل كان **ترتيبَ شيفرة** (حسابُ السعر
    قبل فتح الاتصال) لا اسمَ دالّةٍ مفقوداً.
    """
    import json as _json
    import os
    import tempfile
    d = tempfile.mkdtemp()
    saved = {k: os.environ.get(k) for k in
             ("SILK_PLATFORM_DB", "SILK_PLATFORM_SECRET",
              "SILK_PLATFORM_STORAGE_DIR", "SILK_SEED_ADMIN_PASSWORD")}
    try:
        os.environ["SILK_PLATFORM_DB"] = os.path.join(d, "platform.db")
        os.environ["SILK_PLATFORM_SECRET"] = "registry-guard-secret-not-prod"
        os.environ["SILK_PLATFORM_STORAGE_DIR"] = os.path.join(d, "files")
        os.environ["SILK_SEED_ADMIN_PASSWORD"] = "AdminPass1"
        from fastapi.testclient import TestClient
        from silk_platform import db as pdb, seed as pseed
        from silk_platform.api import create_platform_app
        pdb.init_db(os.environ["SILK_PLATFORM_DB"], force=True)
        conn = pdb.connect()
        try:
            pseed.seed(conn)
        finally:
            conn.close()
        with TestClient(create_platform_app()) as cl:
            tok = cl.post("/platform/auth/login",
                          json={"email": "admin@silk.local",
                                "password": "AdminPass1"}).json()["token"]
            h = {"Authorization": f"Bearer {tok}"}
            assert cl.post("/platform/admin/tiers/silver", headers=h,
                           json={"price": 1234, "price_annual": 12340,
                                 "monthly_studies": 2}).status_code == 200
            shown = [t for t in cl.get("/platform/pricing").json()["tiers"]
                     if t["key"] == "silver"][0]["price"]
            assert shown == 1234, f"العرض لا يعكس التجاوز: {shown}"
            assert cl.post("/platform/billing/checkout",
                           json={"plan": "silver", "billing_cycle": "monthly",
                                 "name": "م", "email": "g@f.local"}
                           ).status_code == 200
            rows = cl.get("/platform/admin/audit", headers=h).json()["audit"]
            ch = [e for e in rows
                  if e.get("action") == "checkout_requested"][0]["changes"]
            if isinstance(ch, str):
                ch = _json.loads(ch)
            assert ch["price_sar"] == shown, (
                f"سُجِّل {ch['price_sar']} والمعروض {shown} (LESSONS ٩٤)")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _guard_factory_language_controls_report():
    """LESSONS ٩٥ — لغةُ المصنع تحكم لغةَ التقرير، والدليلُ على المصنوع النهائي."""
    i18n = _read("silk_i18n.py")
    for needle in ("def normalize", "def foreign_prose_spans", "TERMS",
                   "def entity_allowlist", "def report_language_enabled"):
        assert needle in i18n, f"silk_i18n: {needle} حُذف (LESSONS ٩٥)"
    fs = _read("silk_platform/factory_settings.py")
    assert "def factory_language" in fs and "def study_report_language" in fs, (
        "مُحلّل لغة المصنع/لقطة الدراسة حُذف (LESSONS ٩٥)")
    # مصدرُ الحقيقة: عمودُ الحساب وحده — لا سقوطَ على تفضيل المستخدم.
    assert "FROM accounts WHERE id" in fs, (
        "مُحلّل لغة المصنع لم يعد يقرأ عمود الحساب (LESSONS ٩٥)")
    assert "language_preference FROM users" not in fs, (
        "مُحلّل لغة المصنع عاد يقرأ تفضيل المستخدم (LESSONS ٩٥)")
    api = _read("silk_platform/api.py")
    claim = api.split("UPDATE studies SET state = 'in_progress'")[1][:900]
    assert "report_language = ?" in claim, (
        "لقطةُ اللغة خرجت من جملة المطالبة الذرّية (LESSONS ٩٥)")
    gate = _read("silk_quality_gate.py")
    for fn in ("_check_language_consistency", "_check_language_quality"):
        assert f"def {fn}" in gate, f"حارس {fn} حُذف (LESSONS ٩٥)"
    assert '"language_consistency",' in gate, (
        "اتساقُ اللغة لم يعد حاجزاً — تقريرٌ مختلط يمكن أن يُسلَّم (LESSONS ٩٥)")
    rep = _read("silk_reports.py")
    for needle in ("_CLIENT_FORBIDDEN_PATTERNS_EN", "def _stamp_report_metadata",
                   "def _apply_direction", "def _client_head_label"):
        assert needle in rep, f"silk_reports: {needle} حُذف (LESSONS ٩٥)"
    # التذييلُ يتبع اللغة — الحادثةُ التي التقطها استخراجُ نصّ الـPDF.
    assert "def _add_page_header_footer(doc, title: str, lang" in rep, (
        "تذييلُ الصفحة عاد ثابتَ اللغة — تقريرٌ إنجليزيّ بتذييلٍ عربيّ "
        "على كلّ صفحة (LESSONS ٩٥)")
    # عائلةُ المراجعة الذاتية: مُصيّرٌ عربيٌّ ثابتٌ على مسارٍ إنجليزيّ يحجب
    # التقريرَ كلَّه (البوابة حاجزة) — كلُّ واحدٍ منها صار مشروطاً باللغة.
    for needle in ("def _lang_safe", "def _lang_safe_name",
                   "_CLIENT_SANITIZE_EN", "_CLIENT_REDACT_PLACEHOLDER_EN",
                   "def _sanitize(text: object) -> str:"):
        assert needle in rep, f"silk_reports: {needle} حُذف (LESSONS ٩٥)"
    assert "if silk_i18n.normalize(lang) == \"en\":\n        return" in rep, (
        "المسردُ العربيّ عاد يُحقَن في تقريرٍ إنجليزيّ (LESSONS ٩٥)")
    nar = _read("silk_narrative.py")
    assert "def _humanize_note_en" in nar, (
        "مرآةُ تنظيف الملاحظات الإنجليزية حُذفت — التعريبُ يعود يحقن العربية "
        "في نصٍّ إنجليزيّ (LESSONS ٩٥)")
    assert "_AR_ONLY_CHECKS" in gate, (
        "قائمةُ الفحوص الخامدة على الإنجليزية حُذفت — PASS صامتٌ من بوابةٍ "
        "نصفُها لا يعمل (LESSONS ٩٥)")
    t = _read("tests/test_factory_report_language.py")
    assert "pdftotext" in t, (
        "اختبارُ القبول لم يعد يستخرج نصّ الـPDF — عاد الدليل إلى الكائن "
        "الوسيط (LESSONS ٩٥)")


def _guard_test_seam_matches_the_shape_it_fakes():
    """LESSONS ٩٦ — المقعدُ الاختباريّ يلتزم العقدَ البنيويَّ لِما يستبدله.

    حارسٌ **سلوكيّ**: يُفكِّك نصَّ المقعد فعلاً ويعدُّ الأقسام. مقعدٌ يعود إلى
    عناوين حرّةٍ بلا ترقيم يُفكَّك إلى صفر، فتُصدِّق رُتبتا ٢–٣ تقريراً بلا متن.
    """
    from silk_ai_judge import report_sections
    from silk_platform import engine_bridge
    import silk_reports as _rep
    src = _read("silk_platform/engine_bridge.py")
    assert "from silk_ai_judge import report_sections" in src, (
        "المقعدُ لم يعد يشتقّ عناوينه من المنتِج (LESSONS ٩٦)")
    for lang in ("ar", "en"):
        parsed = _rep._parse_writer_sections_numbered(
            engine_bridge._fake_report_text(lang))
        titles = list(report_sections(lang))
        assert [t for _, t, _ in parsed] == titles, (
            f"مقعدُ «{lang}» لم يعد يُفكَّك إلى الأقسام القانونية "
            f"({len(parsed)} من {len(titles)}) — LESSONS ٩٦")
        assert all(any(str(ln).strip() for ln in b) for _, _, b in parsed), (
            f"قسمٌ بلا متنٍ في مقعد «{lang}» (LESSONS ٩٦)")
    assert (engine_bridge._fake_report_text("ar")
            != engine_bridge._fake_report_text("en")), (
        "المقعدُ لا يتفرّع باللغة — أحدُ الفرعين غيرُ مُختبَرٍ حيّاً (LESSONS ٩٦)")


def _guard_migration_versions_never_collide():
    """LESSONS ٩٧ — رقمُ الترحيل مفتاحٌ أساسيّ؛ تكرارُه يُسقِط ترحيلاً صامتاً."""
    import collections
    import os as _os
    import re as _re
    d = _os.path.join(_ROOT, "migrations", "platform")
    nums = collections.defaultdict(list)
    for name in sorted(_os.listdir(d)):
        m = _re.match(r"(\d+).*\.sql$", name)
        if m:
            nums[m.group(1)].append(name)
    dupes = {k: v for k, v in nums.items() if len(v) > 1}
    assert not dupes, (
        f"أرقامُ ترحيلٍ متصادمة — واحدٌ لن يُطبَّق أبداً: {dupes} (LESSONS ٩٧)")
    src = _read("silk_platform/db.py")
    assert "version TEXT PRIMARY KEY" in src, (
        "جدولُ تتبّع الترحيلات تغيّر — راجِع سببَ الحادثة (LESSONS ٩٧)")


def _guard_declared_thresholds_can_actually_fire():
    """LESSONS ٩٨ — حارسٌ لا يمكن أن يُطلِق ليس حارساً (سلوكيّ).

    يُبنى مدخلٌ **يجب** أن يُرسِب العتبةَ ويُقاس فعلاً؛ ويُتحقَّق أنّ سياسةَ
    التسليم وحدةٌ واحدة يستهلكها سطحا التصدير معاً.
    """
    import silk_source_coverage as C
    from silk_quality_gate import run_quality_gate
    # (أ) اسمُ بعثةٍ ليس سنداً، ومصدرٌ عموميٌّ سندٌ — بلا سلبيّةٍ كاذبة.
    assert C._is_backed("UN Comtrade", "") and C._is_backed("Google Maps", "")
    assert not C._is_backed("الاشتراطات الجمركية", "")
    assert not C._is_backed("x", "", retrieval_method="mission_label_fallback")
    # (ب) العتبةُ تسقط فعلاً على مدخلٍ نصفُه بلا سند.
    cov = C.compute_source_coverage({"missions": {"m": {"findings": [
        {"value": 1, "source": "بعثة", "retrieval_method":
         "mission_label_fallback"},
        {"value": 2, "source": "UN Comtrade"}]}}})
    assert cov["pct"] == 50.0 < C.SOURCE_COVERAGE_MIN_PCT, cov
    # (ج) صفرُ أدلةٍ يُرسِب، لا يُقرَّب إلى مثاليّ.
    out = run_quality_gate({"deep_research": {
        "report": {"text": "## 1. الخلاصة التنفيذية\nنصّ."},
        "analyst": {}, "missions": {}}})
    assert out["verdict"] == "FAIL"
    assert "source_coverage_below_threshold" in {f["check"]
                                                 for f in out["findings"]}
    # (د) دليلٌ بلا قيمةٍ ليس استشهاداً — ويصير فجوةً معلنة لا إسقاطاً صامتاً.
    import json as _json
    import silk_llm_runtime as rt
    from silk_data_layer import DataPoint
    res = rt._parse_output(_json.dumps({"findings": [
        {"claim": "على فجوة", "datapoint_ids": ["g"], "confidence": 0.9}],
        "gaps": [], "summary": ""}, ensure_ascii=False),
        {"g": DataPoint(None, "FAOSTAT", 0.0, "401", "2026")})
    assert res["findings"] == [] and any("على فجوة" in g for g in res["gaps"])
    # (هـ) سياسةُ التسليم وحدةٌ واحدة — لا نسخةَ بوّابةٍ في المنصّة.
    eg = _read("silk_export_gate.py")
    assert "def evaluate(" in eg and "def prepare_fallback_prose(" in eg
    plat = _read("silk_platform/api.py")
    assert "import silk_export_gate" in plat
    assert "run_quality_gate(" not in plat, (
        "منطقُ بوّابةٍ نُسِخ في silk_platform — مسارٌ ثانٍ (LESSONS ٩٨)")
    assert plat.count("_client_view_gated(row,") >= 3


def _guard_coverage_verdict_is_not_a_commercial_label():
    """LESSONS ٩٩ — حكمُ تغطيةٍ لا يُطبَع توصيةً تجارية (سلوكيّ)."""
    import silk_render as R
    from silk_agents import AgentReport, JuryCommittee
    from silk_data_layer import DataPoint
    out = JuryCommittee.evaluate([AgentReport(
        "A", [DataPoint(1.0, "UN Comtrade", 0.9, "n", "2026")], False, "s")])
    assert out.get("basis") == "data_coverage", (
        "الجوريةُ لم تعد تُعلن أساسَ حكمها (LESSONS ٩٩)")
    for tone, want in (("preliminary", "data_complete"),
                       ("inconclusive", "data_partial"),
                       ("nogo", "data_absent")):
        got = R._coverage_basis_tone(tone, {"basis": "data_coverage"})
        assert got == want
        for lang in ("ar", "en"):
            lab = R._verdict_label(got, lang)
            for banned in ("توصية", "بالدخول", "recommendation", "enter"):
                assert banned not in lab, (
                    f"تسميةُ حالةِ أدلةٍ تحمل لغةً تجارية: {lab!r}")
    # والنصفُ المقابل: حكمُ محرّك القرار يحتفظ بتسميته التجارية.
    assert R._coverage_basis_tone("go", {}) == "go"
    assert R._VERDICT_LABELS_AR["go"] == "التوصية بالدخول"


# ── الموجة Z · حُرّاسٌ سلوكية (`docs/WAVE_Z_AUDIT.md`) ────────────────────

def _z_view(jury_state="full", engine="NO-GO", lang="ar"):
    """عرضٌ على شكل المسار العميق بعد الموجة Z — يُعاد استعمالُه في حرّاسها."""
    import copy
    import silk_deep_pillars as DP
    import silk_render as R
    from silk_agents import AgentReport, JuryCommittee
    from silk_data_layer import DataPoint
    from silk_requirements_agent import regulatory_state
    sys.path.insert(0, os.path.join(_ROOT, "tools"))
    from canonical_netherlands import netherlands_research_blob

    def dp(v):
        return DataPoint(v, "UN Comtrade", 0.8, "n")
    ok = AgentReport("a", [dp(1.0)], False, "s")
    other = AgentReport("b", [dp(2.0)], False, "s") if jury_state == "full" \
        else AgentReport("b", [dp(None)], True, "s")
    jury = JuryCommittee.evaluate([ok, other])
    reg = regulatory_state("NLD", "080410")
    r = netherlands_research_blob()
    dr = r["deep_research"]
    # قرارٌ حقيقيّ من `decide` لا قاموسٌ مُعدَّلٌ بعده — وإلّا بقي
    # `counter_case` مبنيّاً على حكمٍ آخر فصار قفلُ «لا كسرَ آليّ خام» عاجزاً
    # عن الفشل (مراجعةٌ ذاتية §٥٨ على هذه الموجة نفسِها).
    if engine == "NO-GO":
        import silk_decision as _D
        pi = DP.build_pillar_inputs(dr, regulatory=reg)
        pi["market_attractiveness"] = {"tam_usd": 2.0e5, "import_cagr_pct": -9.0,
                                       "gdp_per_capita_usd": 800.0,
                                       "saudi_share_pct": 19.0}
        pi["competition_intensity"] = {"hhi": 6000.0,
                                       "top_supplier_share_pct": 80.0,
                                       "named_company_count": 1}
        pi["regulatory_fit"] = {"tariff_applied_pct": 28.0,
                                "entry_requirements_count": 1,
                                "eligibility_gate": False}
        pi["profitability"], pi["risk"] = {}, {}
        dec = _D.decide({"pillar_inputs": pi, "coverage": 1.0})
        assert dec["verdict"] == "NO-GO", dec["verdict"]
    elif engine:
        dec = copy.deepcopy(DP.decide_for_deep(dr, regulatory=reg))
        dec["verdict"] = engine
    else:
        dec = None
    dr["verdict"] = DP.promote_engine_verdict(jury, dec)
    r["markets"] = [{"iso3": "NLD", "name_ar": "هولندا",
                     "name_en": "Netherlands", "rank": 1, "deep": True,
                     "regulatory": reg, "components": DP.build_components(dr),
                     "decision": dec}]
    return R.build_view(r, lang)


def _z_client_lines(view):
    import re as _re
    import tempfile
    import zipfile
    import silk_reports as P
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "c.docx")
        P.render_client_docx(view, path)
        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    txt = _re.sub(r"<[^>]+>", "",
                  xml.replace("</w:p>", "\n").replace("</w:tc>", " | "))
    return [l.strip() for l in txt.split("\n") if l.strip()]


def _guard_the_engine_verdict_reaches_the_artefact():
    """LESSONS ١٠٠ — حكمٌ واحد يصل المصنوع، لا حكمان (سلوكيّ)."""
    import silk_deep_pillars as DP
    v = _z_view()
    assert v["decision"]["verdict"] == "NO-GO"
    lines = _z_client_lines(v)
    assert "عدم الدخول حالياً" in lines[:8], (
        f"غلافُ المُسلَّم لا يحمل حكمَ المحرّك: {lines[:6]}")
    assert not any("توصية أولية بالدخول" in l for l in lines), (
        "عدّادُ تغطيةٍ يُقدَّم توصيةً تجارية في المُسلَّم (LESSONS ١٠٠)")
    # وقراءةُ التغطية لم تُفقَد، والتكافؤُ الرجعيّ محفوظ.
    assert (v["deep_research"]["verdict"] or {}).get("coverage_verdict")
    jury = {"verdict": "PRELIMINARY GO", "basis": "data_coverage"}
    assert DP.promote_engine_verdict(jury, None) == jury


def _guard_one_verdict_field_feeds_every_surface():
    """LESSONS ١٠١ — لا اشتقاقَ ثانٍ يتخطّى التصحيح (سلوكيّ)."""
    import silk_render as R
    import silk_reports as P
    for key in R._VERDICT_LABELS_AR:
        assert R._verdict_tone(key) == key, f"التصنيفُ لا يدور: {key}"
    assert P._resolve_vtxt({"verdict_tone": "data_partial",
                            "verdict": {"verdict": "PRELIMINARY / INCONCLUSIVE"}
                            }) == "data_partial"
    for jury_state, engine in (("full", "NO-GO"), ("partial", None)):
        v = _z_view(jury_state, engine)
        label = v["deep_research"]["verdict_label"]
        assert label in v["brief"][0], f"المختصرُ يخالف التسمية: {v['brief'][0]}"
        assert label in _z_client_lines(v)[:8], "الغلافُ يخالف التسمية"


def _guard_no_verdict_tone_can_break_delivery():
    """LESSONS ١٠٢ — خريطتان لا تتباعدان، وزينةٌ لا تُسقِط تسليماً (سلوكيّ)."""
    import silk_render as R
    import silk_reports as P
    missing = [t for t in R._VERDICT_LABELS_AR
               if t not in P._VERDICT_TEXT_COLORS
               or t not in P._ACADEMIC_MAIN_REC]
    assert not missing, f"تصانيفُ بلا لونٍ/نصّ تُسقِط التصدير: {missing}"
    from docx import Document
    P._add_verdict_badge(Document(), "tone_that_does_not_exist", "ar")
    # والحادثةُ نفسُها: دراسةٌ بفجوةٍ مُعلَنة تُصدَّر بدل KeyError.
    assert len(_z_client_lines(_z_view("partial", None))) > 40


def _guard_a_transformed_metric_is_read_the_same_way_everywhere():
    """LESSONS ١٠٣ — قطبُ عمود المنافسة واحدٌ في الحساب والنصّ (سلوكيّ)."""
    import silk_decision as D

    def bundle(hhi, top, named):
        return {"coverage": 1.0, "pillar_inputs": {
            "market_attractiveness": {"tam_usd": 3e8, "import_cagr_pct": 6.0,
                                      "gdp_per_capita_usd": 45_000,
                                      "saudi_share_pct": 2.0},
            "competition_intensity": {"hhi": hhi,
                                      "top_supplier_share_pct": top,
                                      "named_company_count": named},
            "regulatory_fit": {"tariff_applied_pct": 4.0,
                               "entry_requirements_count": 6,
                               "eligibility_gate": False},
            "profitability": {"border_unit_value_usd_kg": 5.0,
                              "saudi_border_unit_value_usd_kg": 4.2,
                              "margin_at_border_pct": 16.0},
            "risk": {"political_stability_wgi": 0.9, "fx_volatility_pct": 1.2,
                     "supplier_concentration_hhi": 900,
                     "critical_risk": False}}}
    assert D.pillar_strength("competition", 0.19) == 0.81
    assert "شدة المنافسة" not in D.decide(bundle(200.0, 4.0, 9))[
        "counter_case"]["case"], "سوقٌ مُفتَّتة تُقدَّم حجّةً ضدّ الدخول"
    assert "شدة المنافسة" in D.decide(bundle(4800.0, 68.0, 2))[
        "counter_case"]["case"], "سوقٌ مُحتكَرة لم تعد الحجّة"


def _guard_a_barrier_is_not_widened_to_the_wrong_audience():
    """LESSONS ١٠٧ — `report.md` مُخرَجُ مشغّلٍ لا عميل (سلوكيّ + بنيويّ)."""
    import silk_reports as P
    sys.path.insert(0, os.path.join(_ROOT, "tools"))
    from canonical_netherlands import netherlands_research_blob
    import silk_render as R
    md = P.render_markdown(R.build_view(netherlands_research_blob(), "ar"))
    assert "ملحق: أثر المصادر" in md, "قالبُ المشغّل فقد ملحقَه — الفحصُ خاوٍ"
    plat = _read("silk_platform/api.py")
    assert 'report.md"' not in plat and '/brief"' not in plat, (
        "سطحُ المصنع صار يبلغ مُخرَجَ المشغّل — يُعاد تقييمُ G-07")
    src = _read("api.py")
    for path in ("report.docx", "report.pdf"):
        i = src.index(f'@app.get("/analyses/{{analysis_id}}/{path}")')
        j = src.index("@app.get(", i + 10)
        assert "_block_client_export_if_gate_failed" in src[i:j], path



def _guard_committed_samples_are_current():
    """LESSONS ١١٠ — العيّنةُ الملتزَمة == مخرَجُ المُصيِّر اليوم (§10.6)."""
    import importlib
    mod = importlib.import_module("tests.test_committed_samples_current")
    for name, builder in mod._CASES:
        committed = (mod._ROOT / "samples" / name).read_text(encoding="utf-8")
        assert mod._normalise(builder()) == mod._normalise(committed), (
            f"عيّنةُ «{name}» الملتزَمة تخالف مخرَجَ الشيفرة (LESSONS ١١٠) — "
            "أعِد التوليد والتزِم الناتج")


def _guard_gate_probes_are_bilingual():
    """LESSONS ١٠٩ — بوّابةُ الجودة تُمفصِل باللغتين، ولا صمتَ غيرُ معلَن.

    حارسٌ **سلوكيّ** لا وجودُ رمز: نفسُ العيب مكتوباً بالإنجليزية يجب أن
    يشتعل كما يشتعل بالعربية، ونفسُ التقرير الصحيح يجب أن يمرّ في اللغتين."""
    import silk_i18n as _I
    import silk_quality_gate as _Q
    # (أ) الحاجزُ الصامت: متنٌ يذكر درجةً أعلى من الحكم — في اللغتين.
    for lang, body in (
            ("ar", "الحكم دخول مشروط، ومع ذلك التوصية بالدخول قائمة."),
            ("en", "The verdict is conditional entry. "
                   "Recommendation: Enter the market.")):
        out = _Q._check_recommendation_tier_label_consistency(
            {"report": {"text": body},
             "verdict": {"verdict": "CONDITIONAL-GO"}}, lang)
        assert out and out[0]["repairable"] is False, (
            f"حاجزُ تسمية الدرجة صامتٌ على «{lang}» (LESSONS ١٠٩)")
    # (ب) كاذبُ الاشتعال: تقريرٌ **يذكر** المدة الكلية لا يُلام — في اللغتين.
    for lang, body in (
            ("ar", "المدة الكلية من قرار الدخول: 45–60 يوماً."),
            ("en", "Total lead time from the entry decision: 45-60 days.")):
        assert _Q._check_access_timeline_presence(
            {"missions": {"customs_requirements": {"failed": False}},
             "report": {"text": body},
             "regulatory": {"access_timeline":
                            {"total_days": {"min": 45, "max": 60}}}},
            lang) == [], f"لومٌ كاذبٌ على «{lang}» (LESSONS ١٠٩)"
    # (ج) كلُّ مفهومٍ في المعجم يحمل اللغتين — لا مِجَسَّ بلغةٍ واحدة.
    for key, row in _Q._GATE_PROBES.items():
        for lang in _I.LANGS:
            assert row.get(lang), f"مِجَسّ «{key}» ينقصه «{lang}»"


def _guard_one_builder_many_viewers():
    """LESSONS ١٠٥ — ما يعرضه سطحان يُبنى في نموذج العرض (سلوكيّ)."""
    import silk_render as R
    basis = (_z_view().get("decision") or {}).get("basis")
    assert basis and basis.get("pillars"), "الأساسُ لا يصل نموذجَ العرض"
    assert callable(getattr(R, "decision_basis", None))
    body = _read("silk_reports.py")
    body = body[body.index("def _client_decision_basis"):
                body.index("def render_client_docx")]
    for banned in ("pillar_strength", "part_labels", "pillar_label"):
        assert banned not in body, f"العارضُ يبني بدل أن يعرض: {banned}"
    html = _read("web/platform.html")
    assert "v.decision && v.decision.basis" in html
    for banned in ("جاذبية السوق", "شدة المنافسة", "الملاءمة التنظيمية"):
        assert banned not in html, f"تسميةُ عمودٍ منسوخةٌ في JS: {banned}"


def _guard_the_seam_still_matches_the_shape():
    """LESSONS ١٠٦ — المقعدُ يستدعي شيفرةَ الإنتاج لا نسخةً منها (سلوكيّ)."""
    src = _read("silk_platform/engine_bridge.py")
    for needle in ("promote_engine_verdict", "build_components",
                   "decide_for_deep"):
        assert needle in src, f"المقعدُ لا يبني الشكلَ الجديد: {needle}"
    import silk_platform.engine_bridge as EB
    out = EB._fake_result_deep("تمور", "080410", "ar")
    assert out.get("markets"), "المقعدُ ما يزال يُعيد markets فارغة"
    assert (out["markets"][0].get("decision") or {}).get("schema"), out
    assert (out["deep_research"]["verdict"].get("basis")
            == "silk.decision/v1"), out["deep_research"]["verdict"]


def _guard_provenance_reaches_the_artifact():
    """LESSONS ١٠٨ — الإسنادُ يبلغ النصَّ المُصيَّر على **شكل الإنتاج**."""
    import silk_render as R
    import silk_reports as P
    from silk_data_layer import DataPoint
    view = R.build_view({
        "header": {}, "product": "ت", "hs_code": "080410",
        "markets": [{"country": "س", "iso3": "NLD", "total_score": 0.5,
                     "confidence": 0.5, "components": {"market_size": DataPoint(
                         5, "World Bank", 0.77, "n", url="https://x.test/q",
                         evidence_ids=("dp1",))}}]}, "ar")
    md = P.render_markdown(view)
    i = md.find("أثر المصادر")
    assert i >= 0, "ملحقُ الأثر اختفى من المصنوع"
    tail = md[i:i + 400]
    assert "https://x.test/q" in tail, f"الرابطُ المرصود لا يبلغ المصنوع: {tail[:160]}"
    assert "data.worldbank.org" not in tail, "رابطٌ مرصودٌ استُبدِل بصفحةِ السجلّ"
    assert "ثقة المرصود 77%" in tail, tail[:200]
    # و`dpN` **لا يُنطَق**: نطاقُه بعثةٌ واحدة ولا مصنوعَ يحمل جدولَ فكِّه
    # (مراجعةٌ ذاتية §٥٨ على الدرس ١٠٨ نفسِه) — محمولٌ في البند لا معروضاً:
    import re as _re108
    assert _re108.search(r"\bdp\d+\b", tail) is None, tail[:200]
    # وسلسلةُ أسماءٍ مفردةٌ لا تصير أحرفاً مختلَقة:
    from silk_data_layer import atomic_source_ids as _a108
    assert _a108("GCC secretariat", "GAFTA") == ["GAFTA"]
    # وقائمةُ الحقول واحدةٌ للفرعين:
    assert set(R._DP_CARRIED_FIELDS) == {
        "url", "confidence", "evidence_ids", "source_ids",
        "retrieved_at", "data_year"}
    # وشكلُ `sources[]` (§4b) معه — ولا إسنادَ يُنسَب لمصدرٍ شقيق:
    url2 = "https://comtradeplus.un.org/x"
    v2 = R.build_view({
        "header": {}, "markets": [{"country": "س", "components": {}}],
        "deep_research": {"missions": {"m": {"findings": [
            {"metric": "t", "value": 1.0, "note": "n",
             "sources": [{"source": "UN Comtrade", "url": url2},
                         {"source": "مسح ميداني"}]}]}},
            "verdict": {"verdict": "WATCH"},
            "report": {"report": "نصّ"}}}, "ar")
    md2 = P.render_markdown(v2)
    t2 = md2[md2.index("أثر المصادر"):][:400]
    assert url2 in t2, f"الرابطُ لا يبلغ الملحقَ المُصيَّر: {t2[:160]}"
    survey = [l for l in t2.splitlines() if "مسح ميداني" in l]
    assert survey and "http" not in survey[0], (
        f"إسنادٌ مختلَق لمصدرٍ شقيق: {survey}")
    # ولا ذيلَ يُبنى في العارض (الدرس ١٠٥):
    assert "def _provenance_tail" not in _read("silk_reports.py")


def _guard_the_decision_basis_reaches_the_client_artefact():
    """LESSONS ١٠٤ — «يصل العرض» لا يكفي؛ يُعَدّ في المصنوع (سلوكيّ)."""
    import re as _re
    import silk_i18n
    blob = "\n".join(_z_client_lines(_z_view()))
    for needle in ("على أيّ أساس صدر هذا الحكم",
                   "قاعدة الحكم مُعلنة قبل النظر في الأرقام",
                   "جاذبية السوق", "لا نعرفه بعد", "ينقصنا:",
                   "أقوى ما يُقال ضدّ هذا الحكم"):
        assert needle in blob, f"أساسُ الحكم غائبٌ عن المُسلَّم: {needle!r}"
    for banned in ("political_stability", "price_position", "tam_log"):
        assert banned not in blob, f"معرّفٌ داخليّ في مُسلَّم العميل: {banned}"
    assert not _re.search(r"\b0\.\d{2,3}\b", blob), (
        "كسرٌ آليٌّ خام على وجه تقرير العميل (LESSONS ٩٢/١٠٤)")
    for key in ("decision_basis_head", "counter_case_computed"):
        en = silk_i18n.t(key, "en", strong="A", weak="B", strong_pct=1,
                         weak_pct=2)
        assert en and not silk_i18n.foreign_prose_spans(en, "en"), key
def _guard_full_hs_list_migration_no_silent_display_breakage():
    """LESSONS ٤٢ — الترحيل للقائمة الرسمية الكاملة (HS2022، ٥٦١٣ رمزاً)
    غيّر أسماء أعمدة صفوف `load_hs_codes()` (`description_en`/`keywords_ar`
    بدل `name_en`/`name_ar`/`keywords`) — ثلاث دوالّ عرض قرأت الأعمدة
    القديمة مباشرةً (`r.get("name_ar")`) فكانت ستُعيد **فراغاً صامتاً** لكل
    صفٍّ (لا استثناء، `dict.get` لا يفشل على مفتاحٍ غائب) رغم أنّ التصنيف
    نفسه يعمل تماماً: صندوق بحث المنتج (`api._index_search`) كان سيُظهر
    كل نتيجةٍ باسم `None`/فارغ، والمنتقي اليدوي (`_candidate_rows`) وخريطة
    أسماء الاكتشاف العكسي (`silk_discovery._hs_names`) كذلك — عطلُ عرضٍ
    صامتٌ تماماً لا يُسقِط أيّ اختبارٍ ولا يرفع استثناءً، يُكتشَف فقط بفحصٍ
    يدويٍّ فعليّ لمحتوى الاستجابة. الحارس السلوكي: كل دالة عرضٍ تُعيد اسماً
    غير فارغ لصفٍّ حقيقيّ.

    وجدنا أيضاً أثناء التحقّق الحيّ (متصفّحٌ حقيقي، رُتبة ٣): بعد عكس التدفّق،
    منتجاتٌ كانت تُصنَّف تلقائياً («تمور») صارت تعرض صندوق حوارٍ الآن — و`#pDrop`
    (نقر صفّ الفهرس) يستدعي `ensureHs` فوراً عند الاختيار (إصلاحٌ سابق)، ثم
    «بحث عميق» يستدعيها **مجدداً** بلا حارسٍ يتحقّق من تأكيدٍ سابق — فيظهر
    صندوقا حوارٍ متراكبان لنفس المنتج، والثاني يحجب أزرار الأول (فشل e2e حيّ:
    `page.locator('.hsCand').first().click()` يُعلَّق ٣٠ ثانية، «intercepts
    pointer events»). الحارس: `ensureHs` تتجاوز أيّ نداءٍ ثانٍ لمنتجٍ **مؤكَّدٍ
    فعلاً** (`hsConfirmed&&S.hs`) — لا يخالف عقد «تأكيد قبل كل تشغيل» (الدرس
    ٤٠) لأنّ `hsConfirmed` لا يصير true إلا بعد تأكيدٍ فعليّ، ويُصفَّر عند أيّ
    تغييرٍ للمنتج."""
    import api
    import silk_discovery
    from silk_hs_classifier import _candidate_rows

    rows = api._index_search("تمور", limit=3)
    assert rows and all(r.get("name") for r in rows), (
        f"صندوق بحث المنتج يُعيد اسماً فارغاً: {rows}")

    cand = _candidate_rows("تمور", n=3)
    assert cand and all(c.get("label") for c in cand), (
        f"المنتقي اليدوي يُعيد تسميةً فارغة: {cand}")

    names = silk_discovery._hs_names()
    assert names and names.get("080410"), (
        "خريطة أسماء الاكتشاف العكسي فارغة لرمزٍ حقيقيّ (080410/تمور)")
    # وصفّ المخطّط القديم أيضاً (اتحاد الرموز الـ١٣ المعاد ترقيمها): المراجعة
    # الذاتية للدمج المُكيَّف وجدت القارئات تُفرِغها صامتةً — المسبار بالمهاجر
    # وحده لا يلتقط ذلك.
    assert names.get("150910"), "صفّ المخطّط القديم بلا اسم في الاكتشاف العكسي"
    assert any(r["hs"] == "150910" for r in api._index_search("زيت زيتون")), (
        "صندوق البحث لا يجد صفّ المخطّط القديم (150910)")
    from silk_hs_resolver import resolve_all
    dps = resolve_all("زيت زيتون بكر ممتاز", top_n=1)
    assert dps and dps[0].value == "150910" and dps[0].note and         "None" not in dps[0].note, dps and dps[0].note

    html = _read("web/index.html")
    ensure_hs_start = html.index("function ensureHs(")
    ensure_hs_body = html[ensure_hs_start:html.index("function _pct(", ensure_hs_start)]
    assert "S.hsConfirmed&&S.hs" in ensure_hs_body, (
        "ensureHs لم تعد تتجاوز إعادة التصنيف لمنتجٍ مؤكَّدٍ فعلاً — "
        "يعيد صندوقَي حوارٍ متراكبين (فخّ e2e حيّ)")


def _guard_price_derived_test_threshold_is_ledger_calibrated():
    """LESSONS ١١٥ — قفلُ السقف اليوميّ كان يُعوِّل على تكلفةِ نداءٍ بنموذجٍ
    بعينه (Opus ≈1.75$ فوق سقف 1.5$)؛ فحين صار الذكيُّ Sonnet (#223) هبطت
    تكلفةُ النداء نفسِه إلى 1.05$، فلم يعُد المشهدُ يتخطّى السقفَ وبقي الاختبارُ
    أخضرَ أياماً وهو لا يحرس شيئاً — أخضرُ للسبب الخاطئ، وهو أسوأُ من الأحمر.

    الحارس **حسابيّ لا وجوديّ**: يقرأ أرقامَ المعايرة الثلاثة من جسد الاختبار
    (البذر · السقف · الحجز) ويتحقّق أنّ العتبةَ مشتقّةٌ من **حالةِ الدفتر** —
    بذرٌ تحت السقف بهامشٍ ضيّق — فيتخطّاها أيُّ إنفاقٍ فعليٍّ موجب مهما تغيّر
    سعرُ النموذج. تثبيتُ مبلغٍ مطلقٍ من جديد (توسيعُ الهامش) يُحمِّر هنا."""
    rel = "tests/test_wave_p6_pipeline_resilience.py"
    src = _read(rel)
    start = src.index("def test_daily_usd_cap_halts_mid_run")
    body = src[start:src.index(chr(10) + "def ", start)]

    def _one(pattern: str, what: str) -> float:
        found = re.findall(pattern, body)
        assert len(found) == 1, (
            f"{rel}: {what} — المتوقّع مرّةً واحدةً في جسد الاختبار، وُجِد "
            f"{len(found)}: {found}")
        return float(found[0])

    seed = _one(r"record_usd\(([\d.]+)", "بذرُ إنفاقِ اليوم record_usd")
    cap = _one(r'"SILK_PAID_DAILY_USD_CAP":\s*"([\d.]+)"', "السقفُ اليوميّ")
    reserved = _one(r'"SILK_RESEARCH_EXPECTED_USD":\s*"([\d.]+)"', "الحجز")

    assert seed < cap, (
        f"البذرُ ({seed}$) يتخطّى السقفَ ({cap}$) وحدَه — التشغيلةُ تُوقَف قبل "
        "أن تُقاس البوّابةُ على إنفاقٍ فعليّ")
    assert seed + reserved <= cap, (
        f"البذر+الحجز ({seed}+{reserved}$) فوق السقف ({cap}$) — تُوقَف عند "
        "الحجز فلا يُختبَر الإيقافُ وسطَ الطريق")
    margin = cap - seed
    assert 0 < margin <= 0.1 + 1e-9, (
        f"هامشُ العتبة {margin:.4g}$ — يجب أن يتخطّاه أيُّ إنفاقٍ فعليٍّ موجب "
        "مهما رخُص النموذج؛ هامشٌ أوسع يُعيد تثبيتَ العتبة على سعرٍ بعينه")


def _guard_stream_assembler_replayable_thinking():
    """LESSONS ١١٦ — مُجمِّعُ SSE أسقط `thinking_delta`/`signature_delta`
    صامتَين، فخرجت كتلةُ التفكير بنصٍّ فارغ وبلا توقيع ورُفِض الدورُ التالي
    بـ400. الحارس **سلوكيّ**: يُشغّل المُجمِّعَ على بثٍّ حقيقيّ الشكل ويتحقّق
    أنّ الحمولةَ صالحةٌ للإعادة — لا مجرّد وجودِ الحقلين في المصدر."""
    import json as _json
    import silk_llm_provider as _lp

    def _sse(event, data):
        return ["event: " + event, "data: " + _json.dumps(data), ""]

    class _R:
        def __init__(self, lines):
            self._lines = lines
            self.status_code, self.headers, self.text = 200, {}, ""

        def iter_lines(self, decode_unicode=True, **kw):
            yield from self._lines

        def close(self):
            pass

    lines = _sse("message_start", {"type": "message_start", "message": {
        "id": "m", "role": "assistant", "content": [],
        "usage": {"input_tokens": 1, "output_tokens": 1}}})
    lines += _sse("content_block_start", {
        "type": "content_block_start", "index": 0,
        "content_block": {"type": "thinking", "thinking": "", "signature": ""}})
    for part in ("أفكّرُ ", "بصوتٍ مسموع."):
        lines += _sse("content_block_delta", {
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "thinking_delta", "thinking": part}})
    for part in ("SigAAA", "BBB=="):
        lines += _sse("content_block_delta", {
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "signature_delta", "signature": part}})
    lines += _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    lines += _sse("content_block_start", {
        "type": "content_block_start", "index": 1,
        "content_block": {"type": "tool_use", "id": "t1", "name": "x",
                          "input": {}}})
    lines += _sse("content_block_delta", {
        "type": "content_block_delta", "index": 1,
        "delta": {"type": "input_json_delta", "partial_json": "{}"}})
    lines += _sse("content_block_stop", {"type": "content_block_stop", "index": 1})
    lines += _sse("message_delta", {
        "type": "message_delta", "delta": {"stop_reason": "tool_use"},
        "usage": {"output_tokens": 7}})
    lines += _sse("message_stop", {"type": "message_stop"})

    data, abort = _lp.AnthropicProvider._consume_stream(_R(lines), 60.0)
    assert abort is None, f"البثّ أُجهِض في الحارس: {abort}"
    content = data["content"]
    think = [b for b in content if b.get("type") == "thinking"]
    assert len(think) == 1, f"كتلةُ التفكير ضاعت من التجميع: {content}"
    assert think[0].get("thinking") == "أفكّرُ بصوتٍ مسموع.", (
        "نصُّ التفكير لم يُسلسَل حرفياً — الدورُ التالي يُرفَض بـ400 "
        f"«each thinking block must contain thinking»: {think[0]!r}")
    assert think[0].get("signature") == "SigAAABBB==", (
        f"التوقيع لم يُسلسَل حرفياً: {think[0]!r}")
    assert [b.get("type") for b in content] == ["thinking", "tool_use"], (
        f"ترتيبُ الكتل تغيّر: {[b.get('type') for b in content]}")

    # النصفُ الثاني من القفل نفسِه — الاسمُ يَعِد بـ«صالحةٍ للإعادة»، فيجب أن
    # يُقاس ذلك فعلاً لا أن يُستنتَج من وجود الحقول عند التجميع.
    import silk_llm_runtime as _rt
    replayed = _rt._replayable_content(content, "guard", 0)
    assert [b.get("type") for b in replayed] == ["thinking", "tool_use"], (
        "كتلةٌ موقَّعةٌ صالحة أُسقِطت من الدور المُعاد: "
        f"{[b.get('type') for b in replayed]}")

    # شكلُ `display=omitted` (الافتراضيّ على Opus 5/4.8/4.7 · Sonnet 5):
    # موقَّعةٌ بنصٍّ فارغ. قياسُ النصّ بدل التوقيع يُسقِطها وهي مكتملة.
    omitted = [{"type": "thinking", "thinking": "", "signature": "SigZZZ=="},
               {"type": "tool_use", "id": "t2", "name": "x", "input": {}}]
    assert _rt._replayable_content(omitted, "guard", 0) == omitted, (
        "كتلةُ تفكيرٍ موقَّعة بنصٍّ فارغ أُسقِطت — المعيارُ يجب أن يكون "
        "التوقيعَ لا النصّ")

    # والحدُّ المقابل يبقى مقفولاً: بلا توقيعٍ تُسقَط مهما كان نصُّها.
    unsigned = [{"type": "thinking", "thinking": "تحليلٌ بُتِر"}]
    assert _rt._replayable_content(unsigned, "guard", 0) == [], (
        "كتلةُ تفكيرٍ بلا توقيع نجت في الدور المُعاد — نفسُ الـ400")


def _guard_analysis20_no_op_continuation_and_partial_delivery():
    """LESSONS ١١٧ — حارسٌ سلوكيّ (يُشغّل حلقة الإكمال فعلياً): إكمالٌ لا يزيد
    تغطيةَ الأقسام يوقف الحلقة بعد نداءٍ واحد (لا يستنفد SILK_WRITER_
    CONTINUATIONS في عمليةٍ مدفوعةٍ عقيمة، بلاغ تحليل 20)، والمسوّدةُ الناقصة
    **تُسلَّم** موسومةً `incomplete` بدل `None` (تجاوز §5-الإتلاف)."""
    import os as _os
    import unittest.mock as _mock
    import silk_ai_judge as aj
    import silk_llm_provider as lp
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint

    def _trunc():
        secs = aj.report_sections("ar")
        return f"## 1. {secs[0]}\nفقرة أولى تنقطع وسط"

    calls = {"n": 0}

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        calls["n"] += 1
        lp._last_stop_reason.set("max_tokens")
        # مسوّدة مقتطعة، ثم إكمالٌ نصُّه لا يضيف عنوان قسمٍ جديد (عقيم)
        return " ذيلٌ عقيمٌ لا قسمَ فيه" if "مهمة إكمال" in user else _trunc()

    _saved = {k: _os.environ.get(k) for k in
              ("ANTHROPIC_API_KEY", "SILK_WRITER_CONTINUATIONS")}
    _os.environ["ANTHROPIC_API_KEY"] = "k"
    _os.environ["SILK_WRITER_CONTINUATIONS"] = "2"
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)
    try:
        reports = {"trade_flow": AgentReport(
            "LLMAgent:trade_flow",
            [DataPoint("x", "UN Comtrade", 0.9, "n")], False, "ok")}
        with _mock.patch("silk_ai_judge._call", side_effect=fake_call):
            res = aj.write_reviewed_report(
                reports, "محلل", {"verdict": "WATCH"}, "تمور", "هولندا")
    finally:
        for k, v in _saved.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v
        lp._last_error.set(None)
        lp._last_stop_reason.set(None)
    assert calls["n"] == 2, \
        f"العملية العقيمة لم تُوقِف الحلقة مبكّراً (نداءات={calls['n']}، المتوقّع ٢)"
    assert res.get("report") and res.get("incomplete") is True, \
        "المسوّدة الناقصة لم تُسلَّم موسومةً (§5-الإتلاف لم يُتجاوَز)"
    assert res.get("missing_sections"), "الأقسام الغائبة غير معلَنة"


def _guard_analysis20_trailing_fragment_accepted():
    """LESSONS ١١٧ (الخطوة ٢، قرار المالك) — حارسٌ سلوكيّ: تقريرٌ حاضرةٌ فيه
    الأقسام الأحد عشر كلّها لكنه ينتهي بجملةٍ مقطوعةٍ قصيرة يُقبَل **مكتملاً**
    بعد قصّ الشظيّة (لا يُوسَم «غير مكتمل» على نقطةٍ ناقصة)؛ بينما نقصٌ بنيويّ
    (قسمٌ غائب) أو شظيّةٌ متعدّدةُ الأسطر (اقتطاعٌ حقيقيّ) يبقى موسوماً بصدق."""
    import silk_ai_judge as aj
    secs = aj.report_sections("ar")
    dangling = "\n".join(f"## {i}. {s}\nفقرة كاملة." for i, s in
                         enumerate(secs[:-1], 1))
    dangling += f"\n## {len(secs)}. {secs[-1]}\nفقرةٌ كاملة. وجملةٌ تنقطع وسط"
    out = aj._finalize_trailing_fragment(dangling)
    assert aj._writer_incomplete(out) == [], \
        "تقريرٌ ١١/١١ بجملةٍ مقطوعةٍ قصيرة لم يُقبَل مكتملاً (رُفِض على نقطة)"
    assert "وجملةٌ تنقطع وسط" not in out, "الشظيّةُ المعلَّقة لم تُقصّ"
    # نقصٌ بنيويّ لا يُقصّ ولا يُقبَل مكتملاً
    missing = f"## 1. {secs[0]}\nفقرةٌ تنقطع وسط"
    assert aj._finalize_trailing_fragment(missing) == missing
    assert aj._writer_incomplete(missing), "نقصٌ بنيويّ وُسِم مكتملاً خطأً"


def _guard_analysis20_duplicate_section_dedup():
    """LESSONS ١١٧ (التقرير الحيّ الفاشل) — حارسٌ سلوكيّ: عنوانُ قسمٍ مكرَّرٌ
    (البذرة انقطعت وسط القسم فأعاد الإكمالُ كتابتَه) يُدمَج فيبقى مبتورٌ+كامل
    ويُفشِل `section_structure`؛ `_dedupe_duplicate_sections` يُبقي الأخير الكامل
    ويحذف السابق المبتور فتصير البنيةُ سليمة."""
    import silk_ai_judge as aj
    secs = aj.report_sections("ar")
    parts = [f"## {i}. {s}\nفقرة." for i, s in enumerate(secs[:4], 1)]
    parts.append(f"## 5. {secs[4]}\nمبتورٌ أن ق")
    parts.append(f"## 5. {secs[4]}\nالكاملُ المكتمل.")
    parts += [f"## {i}. {s}\nفقرة." for i, s in enumerate(secs[5:], 6)]
    out = aj._dedupe_duplicate_sections("\n".join(parts))
    import re as _re
    assert len(_re.findall(r"^##\s+5\.", out, _re.M)) == 1, "القسمُ المكرَّر لم يُسقَط"
    assert "مبتورٌ أن ق" not in out and "الكاملُ المكتمل." in out
    assert aj._section_order_issues(out) == [], "البنيةُ ما زالت مكسورة بعد الدِّدَب"


def _guard_analysis20_join_overlap_trimmed():
    """LESSONS ١١٧ (التقرير الحيّ) — حارسٌ سلوكيّ: استئنافُ جملةٍ يعيد العبارةَ
    المقطوعة عند اللصق («هذا الانكماش هذا الانكماش»)؛ `_trim_join_overlap` يُسقِط
    التداخلَ الحرفيّ عند حدّ الكلمة فلا تلعثم."""
    import silk_ai_judge as aj
    out = aj._trim_join_overlap("الطلبُ يتقلّص. هذا الانكماش",
                                "هذا الانكماش الحاد يستدعي تحققاً.")
    assert out == "الحاد يستدعي تحققاً.", "التداخلُ لم يُقصّ"
    # لا قصَّ لتطابقٍ عرضيٍّ قصير
    assert aj._trim_join_overlap("السوق في نموّ", "مطّردٌ هذا العام") \
        == "مطّردٌ هذا العام"


def _guard_market_study_charter_shadow_wave():
    """LESSONS ١١٨ — حادثة دراسة #9: دراسة «حليب» عامة حُلِّلت على HS 040110
    (منزوع الدسم ≤١٪ حصراً) صامتاً، وفجوةُ مرآة ٥٫٦× لم تُختبَر كتضييق نطاقٍ
    أولاً، ومسارٌ بحريٌّ افتراضيٌّ رغم حدودٍ برّية. الحارس السلوكي: (١) وكيل
    الميثاق يتوقّف فعلياً على نفس السيناريو؛ (٢) وسيلة النقل تُحسَب من
    الجغرافيا لا افتراضاً بحرياً؛ (٣) فجوة مرآة > ٢× تفرض فرضية عدم تطابق
    HS أولاً؛ (٤) الطرح SHADOW فقط — `run_all_missions` لا يزال يُستدعى
    افتراضياً رغم ميثاقٍ متوقِّف (الصمّام مُطفأ)؛ (٥) **المُطعِّم مربوطٌ فعلياً**
    (لا تأجيل) — يعمل على مدوّنةٍ حقيقية الشكل واحدة على الأقل بمعدّل تحويلٍ
    ١٠٠٪ ويكتشف حادثةَ سوء تصنيفٍ حقيقيةً موثّقة (زبدة الفول السوداني على
    HS 040510 — DZA) بلا اعتماد على سيناريو 040110 الاصطناعي وحده."""
    import silk_charter
    import silk_contradiction
    import silk_fact_records

    halted = silk_charter.build_charter("milk", "040110", market_iso3="NLD")
    assert halted.halted is True and halted.excluded_attributes

    assert silk_charter.determine_transport_mode("JOR")["mode"] == "land"
    assert silk_charter.determine_transport_mode("NLD")["mode"] == "sea"

    gap = silk_contradiction.detect_mirror_gap(100, 560)
    assert gap["hypothesis"] == "hs_scope_mismatch"

    assert silk_charter.charter_enforce_enabled() is False   # افتراضياً مُطفأ

    # (٥) المُطعِّم على مدوّنةٍ حقيقية الشكل حقيقية (DZA — حادثة موثّقة).
    import sys as _sys
    _tools = os.path.join(_ROOT, "tools")
    if _tools not in _sys.path:
        _sys.path.insert(0, _tools)
    import canonical_dza_peanut_butter as _dza
    _blob = _dza.dza_research_blob()
    _charter = silk_charter.build_charter(
        _blob["product"], _blob["hs_code"],
        market_iso3=(_blob.get("market") or {}).get("iso3"))
    assert _charter.halted is True, "حادثة زبدة الفول السوداني (DZA) لم تُكتشَف"
    _fr = silk_fact_records.build_fact_records_from_missions(
        _blob["deep_research"]["missions"], _charter)
    assert _fr["stats"]["parse_rate"] == 1.0, _fr["stats"]["skipped_reasons"]


def _guard_market_study_judge_abstain_shadow_wave():
    """LESSONS ١١٩ — حادثة دراسة #9 (تكملة ١١٨): حكمٌ سُجِّل ١٦٪ رفضاً من
    عمودين غير مقاسين بدل الامتناع. الحارس السلوكي: (١) ميثاقٌ متوقِّف يكفي
    وحده للامتناع بصرف النظر عن الأعمدة؛ (٢) عمودٌ واحدٌ غائبٌ كلياً من
    `by_category` يُعامَل كصفر مؤهَّل لا يُتخطَّى؛ (٣) `charter` كـdict
    (شكل الإنتاج الفعليّ عبر `research_run.get("charter")`) يُنتج نفس
    الإشارة تماماً ككائن `Charter` حيّ؛ (٤) الشرط الثالث (تعارضٌ حرجٌ غير
    محسوم) مُعلَنٌ `False` صراحةً لا مُخمَّناً."""
    import silk_charter
    import silk_judge_abstain

    halted = silk_charter.build_charter("milk", "040110", market_iso3="NLD")
    assert halted.halted is True
    r_scope = silk_judge_abstain.would_abstain(charter=halted, by_category={
        "demand": [{"value": 1, "source": "UN Comtrade", "confidence": 0.9,
                    "note": "x"}],
        "entry_cost": [{"value": 1, "source": "UN Comtrade", "confidence": 0.9,
                        "note": "x"}],
        "price_competitiveness": [{"value": 1, "source": "UN Comtrade",
                                   "confidence": 0.9, "note": "x"}],
        "entry_door": [{"value": 1, "source": "UN Comtrade", "confidence": 0.9,
                        "note": "x"}],
        "swot": [{"value": 1, "source": "UN Comtrade", "confidence": 0.9,
                 "note": "x"}],
    })
    assert r_scope["would_abstain"] is True and r_scope["scope_mismatch"] is True

    not_halted = silk_charter.build_charter("تمور", "080410", market_iso3="NLD")
    assert not_halted.halted is False
    r_gap = silk_judge_abstain.check_pillar_eligibility({}, not_halted)
    assert set(r_gap["zero_eligible_pillars"]) == {
        "demand", "entry_cost", "price_competitiveness", "entry_door", "swot"}

    charter_dict = not_halted.to_dict()
    r_obj = silk_judge_abstain.would_abstain(charter=not_halted, by_category={})
    r_dict = silk_judge_abstain.would_abstain(charter=charter_dict, by_category={})
    assert r_obj["would_abstain"] is True and r_dict["would_abstain"] is True
    assert r_obj["zero_eligible_pillars"] != []
    assert r_obj["unresolved_critical_conflict_checked"] is False


def _guard_forensic_raw_evidence():
    from tests.test_forensic_20260908_runtime import test_numeric_claim_is_checked_against_source_not_its_own_text
    test_numeric_claim_is_checked_against_source_not_its_own_text()


_LESSONS = {
    1: _needles("docs/LIVE_PROOF_RUNBOOK.md", "لا يُشغَّل هيرمتياً"),
    2: _needles("silk_render.py", "_deep_research_view"),
    3: _guard_docx501_row3,          # docx-501 (١)
    4: _needles("api.py", "SILK_REQUIRE_PERSISTENT_DATA_DIR",
                "SILK_DATA_DIR غير مضبوط"),
    5: _needles("silk_storage.py", "def create_research_run",
                "def load_mission_checkpoints"),
    6: _needles("silk_llm_runtime.py", "_JSON_PARSE_FAILURE_GAP"),
    7: _needles("silk_data_layer.py", "_WB_INDICATOR_SOURCE"),
    8: _needles("silk_data_layer.py", "class DataPoint"),
    9: _absent("web/index.html", 'id="snapBtn"'),
    10: _needles("docs/AUDIT_STATUS.md", "قراءة فقط", "غير موجود"),
    11: _guard_docx501_row11,         # docx-501 (٣)
    12: _needles("silk_render.py", "_reconcile_mission_limits", "_first_clause"),
    13: _guard_docx501_row13,         # docx-501 (٢، الفشل الحيّ)
    14: _needles("silk_quality_gate.py", "_check_confidentiality_leaks",
                 "_check_style"),
    15: _needles("tools/live_shape_server.py", "class LiveShapeServer",
                 "def seed_db"),
    16: _needles("silk_ai_judge.py", "_WRITER_MAX_TOKENS", "_MAX_TOKENS_CEILING",
                 "max_tokens=_MAX_TOKENS_CEILING"),
    17: _guard_datapoint_repr_flexible,  # هجوم المشرف — ريبر DataPoint المرن
    18: _guard_vendor_name_leak,         # بلاغ UK — تسريب اسم مزوّد للعميل
    19: _guard_export_format_contract,   # بلاغ المُشرِف — زرّ PDF كان ينزّل docx
    20: _guard_world_tier2_no_fabrication,  # الميزة أ — لا تلفيق فئة-٢/تفجّر ميزانية
    21: _guard_intake_no_silent_guess,      # الميزة ب — لا اختلاق منتج من صورة
    22: _guard_out_of_coverage_thin_study,  # الميزة أ — سوق خارج التغطية لا دراسة هزيلة
    23: _guard_unresolved_hs_silent_spend,  # Wave 1 — الفيتوتشيني: لا إنفاق برمز HS مجهول
    24: _guard_hardcoded_product_rule,      # Wave 1 — الحارسان قاعدتان مبنيّتان على البيانات
    25: _guard_wrong_direction_study,       # Wave 1.5 A — أشقّاء «الدراسة بالاتجاه الخاطئ»
    26: _guard_silent_external_failure,     # Wave 1.5 C — لا فشلٌ صامت لخدمةٍ خارجية
    27: _guard_readiness_before_spend,      # Wave 1.5 D — كلُّ تدهورٍ قبل الحجز
    28: _guard_leads_table_hygiene,         # Wave 2 — نقاء جدول الروابط (جغرافيا/نثر/حشو)
    29: _guard_report_arabic_shape_a4,      # Wave 2 — «سلك» متّصلة + A4
    30: _guard_client_template_no_hardcoded_product,  # Wave 2 — لا منتج مثبَّت في القوالب
    31: _guard_analyze_persist_canonical_db,   # /analyze — التخزين للقاعدة القانونية لا قرصٍ نسبيّ فانٍ
    32: _guard_report_quality_upgrade,         # ترقية جودة التقرير — إصلاحُ المحرّك لا تحرير التقرير
    33: _guard_parse_provenance_not_prose,     # التقادُم من المصدر لا النثر (قرار المالك)
    34: _guard_new_source_contracts,           # دمج مصادر جديدة — نفس العقود (فجوة/ops/مخزَّن/محكوم/نظيف)
    35: _guard_hs_gate_shared_choke_point_fail_safe,  # تقرير الكويت — بوّابة HS فشل-آمن + نقطة اختناق مشتركة
    36: _guard_cross_market_checkpoint_leak,          # تقرير الكويت — تسرّب يمن↔كويت عبر نقاط تفتيش بعثات
    37: _guard_golden_contract_test_exists_and_covers_both_paths,  # الاختبار الذهبي — كل العقود، كلا المسارين
    38: _guard_watchdog_owner_only_no_client_contamination,  # الحارس — مراقبةٌ للمالك حصراً، صفر تلوّث للعميل
    39: _guard_general_hs_classifier_no_lookup_table_ceiling,  # المصنّف العام — جدول البحث تلميحٌ ابتدائي لا حاكمٌ نهائي
    40: _guard_ui_tier_consumption_single_choke_point,  # UI-ONLY FIX — نقطة اختناق tier واحدة، لا مسار ثانٍ يثق بـhs6 خامًا
    41: _guard_active_resolution_beats_rejected_and_short_root_collision,  # ONE FIX — المصادَق يتصدّر على المرفوض، لا تصادف جذرٍ قصير
    42: _guard_dza_quality_gate_six_findings,  # تحليل #1 DZA — ست نتائج فشل بوّابة الجودة معاً على تشغيلة واحدة
    43: _guard_hs_classifier_valve_fail_safe_default,  # المُصنِّف العام — صمّامٌ فشل-آمن مفعَّل افتراضياً لا مُطفأ
    44: _guard_verdict_tone_recognizes_arabic_labels,  # Master Prompt Part 2 §B — _verdict_tone تتعرّف على التسمية العربية أيضاً
    45: _guard_price_fix_scoped_to_table_window,  # دالة إصلاح عملة السعر مقيَّدة بنافذة الجدول لا كامل المستند
    46: _guard_quality_gate_is_client_export_delivery_condition,  # حزمة v2.1 — بوابة الجودة شرط تسليم + عائلة فحوصات كاتب/عرض
    47: _guard_wp1_verdict_determinism,        # WP-1 — حتمية الحكم ومصدره الواحد
    48: _guard_wp2_no_raw_internal_output,     # WP-2 — لا مخرَج داخلي خام للعميل
    49: _guard_wp3_evidence_integrity,         # WP-3 — نزاهة الأدلة والمصالحة
    50: _guard_wp4_gaps_consistency,           # WP-4 — اتساق الفجوات مع الختام
    51: _guard_wp5_rtl_bracket_isolation,      # WP-5 — عزل أقواس RTL + فحص PDF
    52: _guard_wp6_injector_adversarial_locks,  # WP-6 — أقفال الحاقنات العدائية
    53: _guard_wp7_delivery_gate_hardening,    # WP-7 — تصليب بوابة التسليم
    54: _guard_zero_confidence_finding_declared_gap,  # بند بثقة 0.0 => فجوة معلنة لا بند (خرق حارس المراقبة الحي)
    56: _guard_coverage_gate_year_fallback,    # تدقيق v2 الموجة ١ — سُلَّم سنوات بوّابة التغطية
    57: _guard_sanitizer_obfuscation_variants,  # الموجة ١ — ست صيغ تشويش المشرف
    58: _needles("CLAUDE.md", "/code-review",   # المراجعة الذاتية قبل فتح/وسم أي PR جاهزًا (Yemen stale-tag)
                 "self-review catches what hermetic tests structurally cannot"),
    55: _needles("tests/conftest.py", "def _hermetic_env_guard"),  # عزل SILK_HERMETIC لكل اختبار — لا تسرّب لافتة «نموذج توضيحي»
    59: _guard_wave2_med_hardening,   # الموجة ٢ — خمسة إصلاحات MED من تدقيق v2
    60: _guard_composite_source_id_attribution,   # بلاغ قطر HF1 — إسنادٌ ذرّيّ لا مركّب
    61: _guard_renderer_truncation_and_empty_parens,  # بلاغ قطر HF2 — لا بترٌ داخل رقم/قوسٌ فارغ
    62: _guard_cross_source_plausibility,         # بلاغ قطر HF3 — حارسُ معقوليةٍ عبر المصادر
    63: _guard_bloc_list_single_source,           # DEF-2 — عضويةُ الكتلة من مصدرٍ واحد (EU27 كاملة)
    64: _guard_g41_domestic_production,           # DEF-1/G4.1 — مرتكزُ الإنتاج المحليّ (سوقٌ مُنتِجة لا تُوسَم)
    65: _guard_ask_what_the_product_answers,      # بلاغ المُشرِف — قِسِ الرقمَ قبل أن تسأل عنه
    66: _guard_band_boundary_strictness_and_second_axis,  # صرامةُ الحدّ + المحورُ الثاني
    67: _guard_dimension_terms_not_frozen_in_code,        # مصطلحُ بُعدٍ مجمَّد (عودةُ ٣٠)
    68: _guard_multi_axis_heading_confident_wrong_code,    # F2 — محورٌ ثانٍ غيرُ رقميّ
    69: _guard_client_operator_document_divergence,        # F3 — تباعدُ مُسلَّمَي العميل/المشغّل
    70: _guard_attribute_resolver_flag_off_by_default,     # D1 — صمّامٌ مُطفأٌ افتراضياً
    71: _guard_cross_basis_edge_refusal,                   # D2 — أساسُ النسبة قربَ الحافّة
    72: _guard_dialog_band_text_from_the_official_reference_only,  # E2 — نصُّ الحدّ من المرجع حصراً
    73: _guard_dialog_axis_siblings_never_partial,         # E3 — لا مجموعةَ محورٍ جزئية
    74: _guard_dialog_prose_carries_no_product_brand_or_country,  # E4 — لا صدى منتج/علامة/دولة
    75: _guard_gate_passes_synthetic_but_silent_on_real,  # تحليل ٧ — بوّابة مرّت التركيبيّ ثم صمتت على الحقيقيّ (قفلان لكلّ بوّابة)
    76: _guard_paid_limit_lock_is_load_bearing,  # PR-2 — قفل الحدّ المدفوع وحارسه المُميِّز
    77: _guard_readiness_names_the_offending_variable,  # #197 — تشخيصٌ بلا سبب
    78: _guard_platform_studies_run_the_deep_engine,  # 2026-08-18 — «٨ ثوانٍ» ليست دراسة
    79: _guard_refused_launch_hands_back_a_way_out,  # 2026-08-19 — رفضٌ بلا مخرج
    80: _guard_golden_set_is_load_bearing,  # 2026-08-19 — المجموعة الذهبية حاجبة
    81: _guard_gap_recovery_layer_contracts,  # 2026-08-19 — طبقة سد الفجوات
    82: _guard_source_contract_and_vintage_tiers,  # الموجة ١ — عقد المصدر + قِدم 3/7
    83: _guard_canonical_economics_arithmetic,  # الموجة 2أ — HHI الموحّد + المعادلة الواحدة
    84: _guard_economics_engine_contracts,  # الموجة ٣ — المحرك الاقتصادي والتطبيع
    85: _guard_classification_derivation_and_lock,  # الموجة ٤ — اشتقاق التصنيف وقفله
    86: _guard_verdict_structure_and_timeline,  # الموجة ٥ — بنية الحكم + جدول النفاذ
    88: _guard_one_gap_channel_for_every_verdict_surface,  # قناة فجوات واحدة
    89: _guard_classifier_needles_come_from_the_producer,  # إبر من المنتِج
    90: _guard_typed_hs_code_answers_the_gate,             # رمز مكتوب يمرّ
    93: _guard_borrowed_visual_identity,            # هوية مستعارة
    94: _guard_money_path_reads_the_source_it_shows,  # سعرٌ معروضٌ ≠ مُسجَّل
    95: _guard_factory_language_controls_report,    # لغة المصنع تحكم التقرير
    96: _guard_test_seam_matches_the_shape_it_fakes,  # المقعد يطابق الشكل
    97: _guard_migration_versions_never_collide,  # أرقام الترحيلات
    98: _guard_declared_thresholds_can_actually_fire,  # عتبةٌ تُطلِق فعلاً
    99: _guard_coverage_verdict_is_not_a_commercial_label,  # تغطية ≠ توصية
    100: _guard_the_engine_verdict_reaches_the_artefact,   # حكمٌ واحد
    101: _guard_one_verdict_field_feeds_every_surface,     # حقلٌ واحد
    102: _guard_no_verdict_tone_can_break_delivery,        # لا تسليمٌ ينهار
    103: _guard_a_transformed_metric_is_read_the_same_way_everywhere,  # القطب
    104: _guard_the_decision_basis_reaches_the_client_artefact,  # في المصنوع
    105: _guard_one_builder_many_viewers,       # بانٍ واحد، عارضون
    106: _guard_the_seam_still_matches_the_shape,  # المقعد يلاحق الشكل
    107: _guard_a_barrier_is_not_widened_to_the_wrong_audience,  # الجمهور
    108: _guard_provenance_reaches_the_artifact,        # يبلغ المصنوع
    109: _guard_gate_probes_are_bilingual,      # البوّابة باللغتين
    110: _guard_committed_samples_are_current,  # العيّنة تُقاس
    # ١١١ — الموجة p6: لا مرحلة مدفوعة بلا نقطة تفتيش؛ الكاتب لا يُطعَم نصّ
    # الخطأ؛ المقتطع يُكمَل لا يُعاد توليده؛ البثّ؛ مصالحة الدولار مرّة واحدة.
    111: lambda: (
        _needles("silk_storage.py", "def save_stage_checkpoint",
                 "def load_stage_checkpoints", "research_stages")(),
        _needles("api.py", "def _stage_checkpoint", "def _llm_error_retryable",
                 "def _budget_ok", "def _stage_mark", "reconcile_run_usd_final",  # R2b
                 "resume_stages")(),
        _needles("silk_llm_provider.py", "def _consume_stream",
                 "class StreamTotalTimeout", "path=json_fallback")(),
        _needles("silk_ai_judge.py", "def _writer_continuations",
                 "_fresh_provider_state", "_last_partial_draft")(),
        _needles("silk_platform/engine_bridge.py", "def _resume_matches",
                 "analysis_id = COALESCE")(),
        _needles("tests/test_wave_p6_pipeline_resilience.py",
                 "def test_analyst_timeout_does_not_invoke_writer",
                 "def test_usd_reservation_released_exactly_once")(),
        _needles("tests/test_wave_p6_writer_continuation.py",
                 "def test_truncation_with_text_continues_instead_of_regenerating")(),
        _needles("tests/test_wave_p6_streaming_provider.py",
                 "def test_mid_stream_death_never_falls_back_to_json")()),
    # ١١٢ — مؤشّر الاستئناف يُخزَّن فقط إن كان خلفه عملٌ محفوظ يُستأنَف.
    112: lambda: (
        _needles("silk_platform/engine_bridge.py", "_resumable",
                 "analysis_id = COALESCE")(),
        _needles("tests/test_wave_p6_platform_bridge.py",
                 "def test_empty_run_without_saved_work_does_not_store_analysis_id")(),
        _needles("tests/test_platform_engine_honesty.py",
                 "assert row.get(\"analysis_id\") in (None, 0)")()),
    # ١١٣ — عطلان **مفتوحان بقرار مالك** (W-04 بوّابةُ أقواس WP-5 وقفلُها
    # المُخمَد، W-05 الإسنادُ المعكوس في ملحق الأثر): لا حارسَ سلوكيّاً بعد —
    # قفلٌ اليوم إمّا يثبّت السلوكَ الخاطئ أو يُحمِّر الحزمة. المرساةُ وثيقةُ
    # التدقيق نفسُها: حذفُ أيٍّ من القسمين، أو فكُّ مرساة البند من سجلّ
    # الدروس، يُحمِّر هنا — فلا يختفي عطلٌ مفتوحٌ بصمت.
    113: lambda: (
        _needles("docs/ENGINE_AUDIT.md", "#### W-04", "#### W-05",
                 "الوصولُ إنتاجياً اليوم: لا.",
                 "الوصولُ إنتاجياً اليوم: مشروط")(),
        _needles("tests/test_lessons_enforcement.py",
                 '(113, "docs/ENGINE_AUDIT.md"')()),
    92: _guard_client_reports_speak_plain_arabic,   # لغة التاجر
    91: _guard_visible_layers_have_kill_switches,          # مفاتيح الإطفاء
    87: _guard_epistemic_register_and_failure_record,  # الموجة ٦ — الأفعال + سجل الفشل
    114: _guard_full_hs_list_migration_no_silent_display_breakage,  # ترحيل القائمة الكاملة — لا عطل عرضٍ صامت من تغيّر أسماء الأعمدة (كان مرقّماً ١١١ خطأً — تكرارٌ يُخفي حارس درس p6 صامتاً؛ §58 #16)
    # ١١٥ — عتبةٌ مشتقّةٌ من سعرٍ مثبّتةٌ داخل قفل: تخضرّ للسبب الخاطئ حين
    # يتغيّر النموذج. الحارسُ يُعايِر أرقامَ الاختبار بحالة الدفتر، ويُثبِّت
    # فرعَ السقف اليوميّ في بوّابة الإنفاق نفسِها.
    115: lambda: (
        _guard_price_derived_test_threshold_is_ledger_calibrated(),
        _needles("api.py", "def _budget_ok",
                 "silk_usage.usd_spent_on(_reserve_day)",
                 "- _reserved_usd + actual)")(),
        _needles("tests/test_wave_p6_pipeline_resilience.py",
                 "def test_daily_usd_cap_halts_mid_run")()),
    # ١١٦ — مُجمِّعٌ يُسقِط أنواعَ دلتا لا يعرفها: الحمولةُ صالحةُ الشكل
    # ومرفوضةٌ عند المستهلك التالي (الواجهة). الحارسُ سلوكيّ + قفلُ الملفّ.
    116: lambda: (
        _guard_stream_assembler_replayable_thinking(),
        _needles("silk_llm_provider.py", "thinking_delta", "signature_delta")(),
        _needles("tests/test_thinking_block_stream_assembly.py",
                 "def test_streamed_thinking_block_is_byte_valid_for_a_follow_up_request",
                 "def test_redacted_thinking_block_survives_assembly_intact",
                 "def test_truncated_thinking_block_is_never_replayed_without_its_signature")(),
        # النصفُ الثاني من الحادثة نفسِها: البترُ عند max_tokens داخل كتلة
        # تفكير يخرج بنصٍّ بلا توقيع، وإعادتُه ترفع نفسَ الـ400.
        _needles("silk_llm_runtime.py", "def _replayable_content",
                 "_replayable_content(content, mission_key, _round)")()),
    # ١١٧ — بلاغ تحليل 20: نداءُ إكمالٍ مدفوعٌ لا يزيد التغطية = عمليةٌ عقيمة؛
    # و§5-إتلافُ الناقص يحوّل نصّاً مدفوعاً إلى صفر. الحارس سلوكيّ (يُشغّل حلقة
    # الإكمال بمموّهٍ عقيمٍ ويتحقّق من التوقّف + تسليم الجزء) + أقفال الملفّات.
    117: lambda: (
        _guard_analysis20_no_op_continuation_and_partial_delivery(),
        _guard_analysis20_trailing_fragment_accepted(),
        _guard_analysis20_duplicate_section_dedup(),
        _guard_analysis20_join_overlap_trimmed(),
        _needles("silk_ai_judge.py", "writer_continuation",
                 "def _missing_sections", "seed_draft",
                 "def _finalize_trailing_fragment",
                 "def _dedupe_duplicate_sections",
                 "def _trim_join_overlap")(),
        _needles("tests/test_analysis20_duplicate_section_dedup.py",
                 "def test_deep_report_seed_midsection_cut_yields_no_duplicate")(),
        _needles("tests/test_analysis20_join_overlap_trim.py",
                 "def test_continuation_join_has_no_stutter")(),
        _needles("tests/test_analysis20_trailing_fragment.py",
                 "def test_finalize_does_not_swallow_complete_bulleted_last_section",
                 "def test_seed_with_all_sections_dangling_spends_zero_"
                 "continuation_calls")(),
        _needles("tests/test_analysis20_resume_from_partial.py",
                 "def test_seed_skips_fresh_draft_and_completes_missing_"
                 "sections")(),
        _needles("silk_render.py", "def _incomplete_banner")(),
        _needles("silk_reports.py", "def _stamp_degraded_banner")(),
        _needles("tests/test_analysis20_incomplete_delivery.py",
                 "def test_markdown_carries_incomplete_banner",
                 "def test_docx_carries_incomplete_banner")(),
        _needles("tests/test_lessons_enforcement.py", '(117, ')()),
    # ١١٨ — محرك دراسة السوق (قواعد المُشرِف): وكيل الميثاق + سجلّ الحقائق
    # ودرجات المصادر + وكيل التناقض، طَور SHADOW (الموجة ١).
    118: lambda: (
        _guard_market_study_charter_shadow_wave(),
        _needles("silk_charter.py", "def build_charter",
                 "def check_attribute_exclusion", "def determine_transport_mode",
                 "CHARTER_ENFORCE_ENV")(),
        _needles("silk_fact_records.py", "TIER_WEIGHTS", "def classify_tier",
                 "def effective_confidence", "def report_confidence",
                 "class FactRecord", "def build_fact_records_from_missions",
                 "def fact_record_from_finding")(),
        _needles("silk_contradiction.py", "def detect_mirror_gap",
                 "def import_premium_synthesis",
                 "def origin_aware_trend_synthesis",
                 "MAX_CHALLENGE_CYCLES")(),
        _needles("silk_missions.py", "from silk_charter import build_charter",
                 'out["charter"] = charter.to_dict()',
                 "build_fact_records_from_missions(reports, charter)")(),
        _needles("silk_render.py", '"charter": dr.get("charter") or {}',
                 '"fact_records": dr.get("fact_records") or {}')(),
        _needles("tools/wave1_charter_adapter_validation.py", "def run(",
                 "_FIXTURES", "canonical_jordan_milk",
                 "لا تُستخدَم هذه الأرقام لتبرير ترقية الموجة ١ من SHADOW إلى WARN")(),
        _needles("tools/canonical_jordan_milk.py", "def jordan_milk_research_blob",
                 "JORDAN_MILK_HS")(),
        _needles("tests/test_lessons_enforcement.py", '(118, ')()),
    # ١١٩ — محرك دراسة السوق (قواعد المُشرِف): حقّ الحَكَم في الامتناع،
    # طَور SHADOW (الموجة ٣).
    119: lambda: (
        _guard_market_study_judge_abstain_shadow_wave(),
        _needles("silk_judge_abstain.py", "def check_pillar_eligibility",
                 "def would_abstain",
                 "unresolved_critical_conflict_checked")(),
        _needles("silk_fact_records.py", "isinstance(charter, dict)")(),
        _needles("api.py", "judge_abstain_shadow",
                 '"charter": research_run.get("charter") or {}',
                 '"fact_records": research_run.get("fact_records") or {}')(),
        _needles("silk_render.py",
                 '"judge_abstain_shadow": dr.get("judge_abstain_shadow") or {}'
                 )(),
        _needles("tests/test_lessons_enforcement.py", '(119, ')()),
    # ١٢٠ — حادثة الدراسة #10 (حليب/الأردن 2026-08-24، direct reproduction):
    # (أ) رمزُ كتالوجٍ مخزَّن وصل بوّابةَ HS كأنه إدخالُ مستخدمٍ حاضر فمرّ
    # اختصارُ محور preflight_block:692 وبُنيت دراسةٌ كاملة (1.80$) على بندٍ
    # قديمٍ (040110) لا يطابق المنتج؛ (ب) تلعثمُ دمج الإكمال بذيلٍ مبتور
    # («…ضيقة م» + إعادة الجملة) نجا من القصّ الحرفيّ فأفشل بوابةَ الجودة
    # (style_repeated_key_figure) وحُجب التسليم.
    120: lambda: (
        _needles("api.py", "def _hs_user_supplied",
                 'hs_source: str | None = None')(),
        _needles("silk_platform/engine_bridge.py",
                 'kwargs["hs_source"] = "catalog"')(),
        _needles("silk_ai_judge.py", "def _trim_join_stutter",
                 "_MIN_RESTART_OVERLAP", "def _find_join_overlap")(),
        _needles("silk_hs_confirm.py",
                 "وصف الرمز المخزَّن غير متاح في المرجع")(),
        _needles("tests/test_catalog_hs_provenance_gate.py",
                 "def test_catalog_hs_faces_the_axis_gate_before_any_spend",
                 "def test_factory_confirmed_catalog_hs_passes_the_gate")(),
        _needles("tests/test_analysis20_join_overlap_trim.py",
                 "def test_stutter_trim_drops_truncated_tail_token",
                 "def test_stutter_trim_drops_diverging_tail_token")(),
        _needles("tests/test_lessons_enforcement.py", '(120, ')()),
    # ١٢١ — البند 1 من أمر إصلاح المحرّك (تقرير #11): مقياسا المنافسة من
    # الملخّص المُهيكل حصراً؛ لا استخراج نثريّاً يبتلع الحصص كأنها HHI.
    121: lambda: (
        _needles("silk_deep_pillars.py", "def _structured_competition",
                 '"incumbent_is_self"')(),
        _needles("silk_decision.py", '"incumbent_is_self"')(),
        _needles("tests/test_goal1_competition_unit_and_direction.py",
                 "def test_acceptance_hhi_7118_scores_at_most_25pct",
                 "def test_share_in_prose_is_never_read_as_hhi")(),
        _needles("tests/test_lessons_enforcement.py", '(121, ')()),
    # ١٢٢ — البند 2 من أمر إصلاح المحرّك: لا درجةَ ولا حكمَ آلياً بأقل من
    # الحد الأدنى من الأعمدة (درجة 84% بعمود واحد في تقرير #11).
    122: lambda: (
        _needles("silk_decision.py", "def _min_scored_pillars",
                 '"insufficient_pillars": True')(),
        _needles("silk_quality_gate.py",
                 "def _check_min_pillars_scored")(),
        _needles("tests/test_goal2_min_pillars.py",
                 "def test_acceptance_one_pillar_yields_no_score_and_no_verdict",
                 "def test_zero_pillars_no_longer_fabricates_a_nogo",
                 "def test_insufficient_decision_is_never_promoted_to_the_artefact")(),
        _needles("tests/test_lessons_enforcement.py", '(122, ')()),
    # ١٢٣ — البند 3: اللوحة والسرد من مصدرٍ واحد (استقرار العملة/الاشتراطات/
    # الحصة السعودية كانت «غير مرصودة» بينما المتن يسردها رقمياً).
    123: lambda: (
        _needles("silk_missions.py", "def _augment_risk_news_fx",
                 "قاعدة معلنة")(),
        _needles("silk_deep_pillars.py", '"fx_volatility_pct"',
                 "تستحوذ السعودية", "customs_requirements")(),
        _needles("silk_quality_gate.py",
                 "def _check_pillar_narrative_sync")(),
        _needles("tests/test_goal3_pillar_narrative_sync.py",
                 "def test_fx_volatility_augment_computes_from_wb_series_declaredly",
                 "def test_gate_fails_when_panel_denies_what_the_body_narrates")(),
        _needles("tests/test_lessons_enforcement.py", '(123, ')()),
    # ١٢٤ — البند 4: قِيسَت الفئة الصحيحة ووُصي بفئةٍ أخرى (بيانات 0401
    # وتوصية بالمجفف/المكثف 0402) — فحص مطابقة قبل التسليم يوقف التقرير.
    124: lambda: (
        _needles("silk_quality_gate.py", "_HS_ATTR_HEADINGS",
                 "def _check_hs_recommendation_match",
                 '"hs_recommendation_match"')(),
        _needles("tests/test_goal4_hs_recommendation_match.py",
                 "def test_acceptance_data_under_0401_recommendation_names_0402_halts",
                 "def test_mention_outside_recommendation_windows_is_legitimate")(),
        _needles("tests/test_lessons_enforcement.py", '(124, ')()),
    # ١٢٥ — البند 5: لا رقم مشتق من مدخلات غير مرصودة (أقصى سعر مصنع
    # $0.3274/كجم من عبوة مجهولة الحجم بعملة غير محوَّلة).
    125: lambda: (
        _needles("silk_economics.py", "حجم العبوة (لتطبيع السعر",
                 "عملة السعر المرصود", 'reverse["unit"]')(),
        _needles("silk_quality_gate.py",
                 "def _check_derived_number_has_inputs",
                 '"derived_number_has_inputs"')(),
        _needles("silk_ai_judge.py", "لا تحوّل العملة ولا",
                 "لا تطبع أي رقم لأقصى سعر مصنع")(),
        _needles("tests/test_goal5_derived_number_inputs.py",
                 "def test_pack_size_unobserved_suspends_reverse_and_names_the_missing_input",
                 "def test_gate_fails_a_numeric_exw_while_reverse_is_suspended")(),
        _needles("tests/test_lessons_enforcement.py", '(125, ')()),
    # ١٢٦ — البند 6: تناقض تسعيري محسوب لا يمرّ بلا تعليق (EXW أدنى بـ60%
    # من متوسط الاستيراد وقُدِّم أساساً للتفاوض بلا تحذير).
    126: lambda: (
        _needles("silk_economics.py", "pricing_contradiction",
                 "لا يصلح هذا الرقم أساساً للتفاوض")(),
        _needles("silk_missions.py", "سعر الصرف الرسمي")(),
        _needles("silk_quality_gate.py",
                 "def _check_pricing_contradiction_flagged",
                 '"pricing_contradiction_flagged"')(),
        _needles("silk_ai_judge.py", "أساساً للتفاوض")(),
        _needles("tests/test_goal6_pricing_contradiction.py",
                 "def test_acceptance_shortfall_over_20pct_emits_mandatory_warning",
                 "def test_gate_fails_a_negotiating_baseline_suggestion")(),
        _needles("tests/test_lessons_enforcement.py", '(126, ')()),
    # ١٢٧ — البند 7: الحكم يتحرك مع الدليل عبر التشغيلات (ترقية مع تدهور
    # الثقة والمؤشرات والفجوات = توقّف وبلاغ).
    127: lambda: (
        _needles("silk_consistency.py", "def check_against_history",
                 "def direction_check", "def evidence_stats")(),
        _needles("api.py", "check_against_history",
                 '"verdict_consistency"')(),
        _needles("silk_render.py", '"verdict_consistency"')(),
        _needles("silk_quality_gate.py",
                 "def _check_verdict_evidence_direction",
                 '"verdict_evidence_direction"')(),
        _needles("tests/test_goal7_verdict_evidence_direction.py",
                 "def test_acceptance_10_to_11_pattern_is_flagged",
                 "def test_history_lookup_matches_product_market_completed_only")(),
        _needles("tests/test_lessons_enforcement.py", '(127, ')()),
    # ١٢٨ — البند 8: الحجة المضادة تشترط عمودين مختلفين.
    128: lambda: (
        _needles("silk_decision.py", '"single_pillar"')(),
        _needles("tests/test_goal8_counter_case_two_pillars.py",
                 "def test_single_pillar_counter_case_abstains_declaredly",
                 "def test_render_omits_the_section_for_a_skipped_case")(),
        _needles("tests/test_lessons_enforcement.py", '(128, ')()),
    # ١٢٩ — البند 9: مرجع تعريفات HS الداخلي يحسم التعارض.
    129: lambda: (
        _needles("silk_hs_reference.py", "def definition_line",
                 "WCO HS 2022")(),
        _needles("silk_ai_judge.py", "التعريف المرجعي الحاسم للبند")(),
        _needles("tests/test_goal9_10_hs_reference_and_label.py",
                 "def test_reference_settles_the_exact_conflict_of_report_11")(),
        _needles("tests/test_lessons_enforcement.py", '(129, ')()),
    # ١٣٠ — البند 10: تسمية الحكم تطابق محتواه.
    130: lambda: (
        _needles("silk_quality_gate.py",
                 "def _check_verdict_label_matches_content",
                 '"verdict_label_matches_content"')(),
        _needles("tests/test_goal9_10_hs_reference_and_label.py",
                 "def test_nogo_label_over_a_named_entry_route_fails",
                 "def test_hypothetical_flip_condition_is_legitimate")(),
        _needles("tests/test_lessons_enforcement.py", '(130, ')()),
    # ١٣١–١٣٨ — موجة P2 (البنود 11–24) + المُطبِّع الواحد.
    131: lambda: (
        _needles("silk_quality_gate.py", "def _check_repeated_span")(),
        _needles("tests/test_goal_p2_text_checks.py",
                 "def test_repeated_span_catches_the_stutter_family")(),
        _needles("tests/test_lessons_enforcement.py", '(131, ')()),
    132: lambda: (
        _needles("silk_render.py", "_ORPHAN_LEAD_COMMA_RE",
                 "_ORPHAN_TAIL_COMMA_RE")(),
        _needles("silk_quality_gate.py", "def _check_empty_citation")(),
        _needles("tests/test_lessons_enforcement.py", '(132, ')()),
    133: lambda: (
        _needles("silk_render.py", "_STATIC_YEAR_CTX")(),
        _needles("tests/test_goal_p2_text_checks.py",
                 "def test_founding_year_is_never_stamped_stale")(),
        _needles("tests/test_lessons_enforcement.py", '(133, ')()),
    134: lambda: (
        _needles("silk_render.py", "def _collapse_dead_tables")(),
        _needles("silk_quality_gate.py", "def _check_dead_table",
                 "def _table_cell_populated")(),
        _needles("tests/test_lessons_enforcement.py", '(134, ')()),
    135: lambda: (
        _needles("silk_quality_gate.py", "def _check_absence_vocabulary",
                 "def _check_decimal_precision",
                 "def _check_sentence_length")(),
        _needles("docs/LESSONS.md", "ثلاث دراسات حية متتالية بلا أي إصابة")(),
        _needles("tests/test_lessons_enforcement.py", '(135, ')()),
    136: lambda: (
        _needles("silk_render.py", "_SYSTEM_MECHANICS_RE")(),
        _needles("silk_quality_gate.py",
                 "def _check_system_language_leak")(),
        _needles("silk_style_contract.py", "بلا الافتتاحية القالبية")(),
        _needles("tests/test_lessons_enforcement.py", '(136, ')()),
    137: lambda: (
        _needles("silk_plausibility.py", "def _prefer_latest",
                 "def _finding_year", "لسنة المرجع")(),
        _needles("tests/test_goal_p2_text_checks.py",
                 "def test_market_size_anchor_uses_reference_year_not_peak")(),
        _needles("tests/test_lessons_enforcement.py", '(137, ')()),
    138: lambda: (
        _needles("silk_quality_gate.py", "def _norm_ar")(),
        _needles("tests/test_goal_p2_text_checks.py",
                 "def test_normalizer_tanween_needle_matches_plain_text_and_reverse")(),
        _needles("tests/test_lessons_enforcement.py", '(138, ')()),
    139: lambda: (
        _needles("silk_deep_pillars.py",
                 "if hhi is not None and not (100.0 <= hhi <= 10_000.0):")(),
        _needles("silk_research.py", "def _incumbent_is_self")(),
        _needles("silk_quality_gate.py",
                 "def _check_competition_unit_valid")(),
        _needles("tests/test_goal1_competition_unit_and_direction.py",
                 "def test_quality_gate_competition_unit_valid_"
                 "fails_out_of_range_value")(),
        _needles("tests/test_lessons_enforcement.py", '(139, ')()),
    140: lambda: (
        _needles("silk_quality_gate.py",
                 "سطرٌ داخل كتلةٍ ينتهي بنقاط حذف")(),
        _needles("tests/test_goal_p2_text_checks.py",
                 "def test_mid_block_bullet_ellipsis_is_caught_on_md_path")(),
        _needles("tests/test_goal_full_report_zero_hits.py",
                 "def test_full_canonical_report_is_clean_"
                 "on_the_three_fail_checks")(),
        _needles("tests/test_lessons_enforcement.py", '(140, ')()),
    141: lambda: (
        _needles("silk_quality_gate.py", '"غير مرصود", "غير مذكور",')(),
        _needles("silk_ai_judge.py", "«الوزن غير متاح»")(),
        _needles("tests/test_goal_p2_text_checks.py",
                 "def test_writer_prompt_no_longer_mandates_"
                 "a_forbidden_absence_term")(),
        _needles("tests/test_lessons_enforcement.py", '(141, ')()),
    142: lambda: (
        _needles("silk_render.py", '"caveat_box": _caveat_box')(),
        _needles("silk_quality_gate.py",
                 "def _check_caveat_repetition")(),
        _needles("tests/test_goal_p2_text_checks.py",
                 "def test_view_builds_one_deterministic_caveat_box_"
                 "when_hs_flagged")(),
        _needles("tests/test_lessons_enforcement.py", '(142, ')()),
    143: lambda: (
        _needles("silk_ai_judge.py", 'base[-k - 1] in (" ", "\\n")')(),
        _needles("silk_quality_gate.py",
                 "def _check_table_row_stutter")(),
        _needles("tests/test_study12_live_defects.py",
                 "def test_join_stutter_trims_across_table_row_boundary")(),
        _needles("tests/test_lessons_enforcement.py", '(143, ')()),
    144: lambda: (
        # موجة #14 (الدرس 174): حدُّ النطاق صار الفقرة (`\n` حصراً) فحُذف
        # نمطُ الجملة الميّت — عائلة الفاصلة العشرية مستحيلة بنيوياً الآن،
        # والحارس السلوكي للحادثة باقٍ كما هو.
        _needles("silk_render.py", 'lo = s.rfind("\\n", 0, start) + 1')(),
        _needles("silk_render.py", "y2 > _stale_years_threshold()")(),
        _needles("tests/test_study12_live_defects.py",
                 "def test_series_narrative_with_decimal_figures_"
                 "gets_no_stale_stamp")(),
        _needles("tests/test_lessons_enforcement.py", '(144, ')()),
    145: lambda: (
        _needles("silk_llm_runtime.py", "def _gaps_blob")(),
        _needles("silk_render.py",
                 'not g.strip().endswith(("…", "..."))')(),
        _needles("tests/test_study12_live_defects.py",
                 "def test_quality_gate_flags_truncated_limit_line")(),
        _needles("tests/test_lessons_enforcement.py", '(145, ')()),
    146: lambda: (
        _needles("silk_i18n.py", '"ar": "ينقصنا: {parts}')(),
        _needles("silk_quality_gate.py",
                 "على سطح العرض (لوحة/شروط/حدود)")(),
        _needles("tests/test_study12_live_defects.py",
                 "def test_view_surface_producers_use_canonical_"
                 "absence_vocabulary")(),
        _needles("tests/test_lessons_enforcement.py", '(146, ')()),
    147: lambda: (
        _needles("silk_deep_pillars.py", "def _numeric_with_source")(),
        _needles("silk_deep_pillars.py", "def _fact_year")(),
        _needles("tests/test_study12_live_defects.py",
                 "def test_numeric_prefers_latest_fact_year_over_"
                 "first_match")(),
        _needles("tests/test_lessons_enforcement.py", '(147, ')()),
    148: lambda: (
        _needles("silk_style_contract.py", "WRITING_STANDARD_RULE = (")(),
        _needles("silk_quality_gate.py",
                 "def _check_decision_numbers_present")(),
        _needles("tests/test_part_b_writing_standard.py",
                 "def test_standard_is_one_shared_constant_in_both_"
                 "arabic_contracts")(),
        _needles("tests/test_lessons_enforcement.py", '(148, ')()),
    149: lambda: (
        _needles("docs/DEEP_RESEARCH_DECISIONS.md",
                 "السلسلة الكاملة على الشجرة النهائية (شرط الدرس 149)")(),
        _needles("docs/LESSONS.md",
                 "لا رقمَ سلسلةٍ يُكتب في السجل قبل تشغيل")(),
        _needles("tests/test_lessons_enforcement.py", '(149, ')()),
    150: lambda: (
        _needles("tests/test_contract_coherence.py",
                 "def test_no_system_input_phrase_is_mandated_anywhere")(),
        _needles("silk_style_contract.py",
                 "يتقدّم هذا العقد في موضعين")(),
        _needles("tests/test_lessons_enforcement.py", '(150, ')()),
    151: lambda: (
        _needles("silk_quality_gate.py", '"not calculated"')(),
        _needles("tests/test_gate_language_parity.py",
                 "takes_text_param")(),
        _needles("tests/test_contract_coherence.py",
                 "def test_english_silent_checks_now_fire")(),
        _needles("tests/test_lessons_enforcement.py", '(151, ')()),
    152: lambda: (
        _needles("silk_quality_gate.py",
                 "def consecutive_clean_runs")(),
        _needles("tests/test_gap_sweep2.py",
                 "def test_counter_missing_gate_is_unknown_not_clean")(),
        _needles("tests/test_lessons_enforcement.py", '(152, ')()),
    153: lambda: (
        _needles("silk_i18n.py", '"hs_caveat_box"')(),
        _needles("tests/test_gap_sweep2.py",
                 "def test_caveat_box_consumed_on_every_surface")(),
        _needles("tests/test_lessons_enforcement.py", '(153, ')()),
    154: lambda: (
        _needles("silk_export_gate.py", "def _fail_drivers")(),
        _needles("tests/test_download_gate_block.py",
                 "def test_connector_excess_is_the_only_driver_among_"
                 "the_four")(),
        _needles("tests/test_lessons_enforcement.py", '(154, ')()),
    155: lambda: (
        _needles("silk_render.py",
                 "(مختصر — التفصيل في حدود هذا التقرير)")(),
        _needles("tests/test_no_ellipsis_build_rule.py",
                 "def test_no_ellipsis_emitters_in_client_text_modules")(),
        _needles("tests/test_lessons_enforcement.py", '(155, ')()),
    156: lambda: (
        _needles("silk_ai_judge.py", "MANDATED_OUTPUT_LITERALS: tuple = (")(),
        _needles("tests/test_mandated_literals_cross_reference.py",
                 "def test_c_no_registered_literal_hits_any_gate_"
                 "blocklist")(),
        _needles("tests/test_lessons_enforcement.py", '(156, ')()),
    157: lambda: (
        _needles("tests/test_gate_language_parity.py",
                 "def _probe_payload", "def _loop_vars")(),
        _needles("tests/test_lessons_enforcement.py", '(157, ')()),
    158: lambda: (
        _needles("silk_quality_gate.py", "_CONFIDENCE_BAND_EN_RE",
                 "_CURRENCY_COUNTRY_PHRASES_EN")(),
        _needles("tests/test_gap_sweep3_gate.py",
                 "def test_blocking_checks_now_fire_on_english_text")(),
        _needles("tests/test_lessons_enforcement.py", '(158, ')()),
    159: lambda: (
        _needles("silk_store.py", "def staleness_suffix")(),
        _needles("tests/test_gap_sweep3.py",
                 "def test_store_served_market_size_keeps_original_"
                 "provenance")(),
        _needles("tests/test_lessons_enforcement.py", '(159, ')()),
    160: lambda: (
        _needles("silk_collectors.py", "قياس متعذّر، لا إنذار")(),
        _needles("tests/test_gap_sweep3.py",
                 "def test_post_entry_fetch_failure_never_fires_growth_"
                 "alert")(),
        _needles("tests/test_lessons_enforcement.py", '(160, ')()),
    161: lambda: (
        _needles("silk_reports.py", "def _client_price_observations",
                 "def _client_hs_derivation_section")(),
        _needles("web/platform.html", "out.quality")(),
        _needles("tests/test_lessons_enforcement.py", '(161, ')()),
    162: lambda: (
        _needles("tests/test_gap_sweep3_meta.py",
                 "def test_no_tautological_or_true_asserts_in_the_suite")(),
        _needles("tests/test_lessons_enforcement.py", '(162, ')()),
    163: lambda: (
        _needles("tools/gen_client_report_sample.py",
                 "def build_sample_view")(),
        _needles("tests/test_committed_samples_current.py",
                 "def test_committed_client_docx_text_matches_what_the_"
                 "code_emits")(),
        _needles("tests/test_lessons_enforcement.py", '(163, ')()),
    164: lambda: (
        _needles("tests/test_gap_sweep3_meta.py",
                 "def test_every_test_name_cited_in_lessons_exists")(),
        _needles("tests/test_lessons_enforcement.py", '(164, ')()),
    165: lambda: (
        _needles("silk_reports.py", "def _eco_term")(),
        _needles("tests/test_gap_sweep3_surfaces.py",
                 "def test_no_bare_client_sanitize_inside_client_docx_"
                 "renderer")(),
        _needles("tests/test_lessons_enforcement.py", '(165, ')()),
    166: lambda: (
        _needles("silk_platform/api.py", 'named_limits("PWRESET"')(),
        _needles("api.py", "def _operator_artifact_gate_409")(),
        _needles("tests/test_gap_sweep3_surfaces.py",
                 "def test_password_reset_request_is_throttled")(),
        _needles("tests/test_lessons_enforcement.py", '(166, ')()),
    167: lambda: (
        _needles("silk_hs_reference.py", "ATTR_PHRASES = {")(),
        _needles("tests/test_study13_live_defects.py",
                 "def test_infant_formula_recommendation_trips_hs_match",
                 "def test_unclassified_attribute_is_declared_not_silent")(),
        _needles("tests/test_lessons_enforcement.py", '(167, ')()),
    168: lambda: (
        _needles("silk_quality_gate.py",
                 "def _check_adjacent_short_stutter")(),
        _needles("tests/test_study13_live_defects.py",
                 "def test_study13_stutters_trip_the_new_check",
                 "def test_joiner_negative_directions")(),
        _needles("tests/test_lessons_enforcement.py", '(168, ')()),
    169: lambda: (
        _needles("silk_render.py", "def _clean_price_row_note")(),
        _needles("tests/test_study13_live_defects.py",
                 "def test_price_row_note_cleaner_study13_cases")(),
        _needles("tests/test_lessons_enforcement.py", '(169, ')()),
    170: lambda: (
        _needles("silk_reports.py", '("product_card"')(),
        _needles("tests/test_study13_live_defects.py",
                 "def test_render_surfaces_ask_for_the_input_not_the_card")(),
        _needles("tests/test_lessons_enforcement.py", '(170, ')()),
    171: lambda: (
        _needles("silk_i18n.py", '"coverage_named_sources"')(),
        _needles("tests/test_study13_live_defects.py",
                 "def test_named_source_coverage_line_present_in_section")(),
        _needles("tests/test_lessons_enforcement.py", '(171, ')()),
    172: lambda: (
        _needles("silk_quality_gate.py", "منطقة العمى المعلنة")(),
        _needles("docs/LESSONS.md",
                 "كل فحص جديد يصرّح بمنطقة عماه")(),
        _needles("tests/test_lessons_enforcement.py", '(172, ')()),
    # موجة الدراسة الحية #14 — فك الحجب الأخير.
    173: lambda: (
        _needles("silk_i18n.py", "كلمتين صغيرتين")(),
        _needles("tests/test_study14_live_defects.py",
                 "def test_study14_distributor_sentence_is_not_foreign_prose",
                 "def test_capitalized_name_list_without_domain_is_clean")(),
        _needles("tests/test_lessons_enforcement.py", '(173, ')()),
    174: lambda: (
        _needles("silk_render.py", "def _year_in_growth_span")(),
        _needles("tests/test_study14_live_defects.py",
                 "def test_yemen_two_old_facts_still_both_tagged")(),
        _needles("tests/test_lessons_enforcement.py", '(174, ')()),
    175: lambda: (
        _needles("silk_render.py", "def _fix_truncated_prefix_stutter")(),
        _needles("tests/test_study14_live_defects.py",
                 "def test_truncated_prefix_stutter_is_repaired_with_audit_log")(),
        _needles("tests/test_lessons_enforcement.py", '(175, ')()),
    176: lambda: (
        _needles("docs/DEEP_RESEARCH_DECISIONS.md",
                 "ماذا يطلب موجّهُ الكاتب مما قد يُطلق هذا الفحص")(),
        _needles("docs/LESSONS.md", "سؤال التأليف الدائم")(),
        _needles("tests/test_lessons_enforcement.py", '(176, ')()),
    177: lambda: (
        _needles("silk_export_gate.py", 'out["fail_drivers"]')(),
        _needles("web/platform.html", "قائد الحجب")(),
        _needles("tests/test_study14_live_defects.py",
                 "def test_client_quality_summary_carries_names_on_fail")(),
        _needles("tests/test_lessons_enforcement.py", '(177, ')()),
    178: lambda: (
        _needles("silk_quality_gate.py",
                 "def _check_cross_universe_ratio")(),
        _needles("tests/test_study14_live_defects.py",
                 "def test_cross_universe_ratio_fires_on_study14_line")(),
        _needles("tests/test_lessons_enforcement.py", '(178, ')()),
    179: lambda: (
        _needles("silk_deep_pillars.py",
                 "def _saudi_share_from_competitors")(),
        _needles("tests/test_study14_live_defects.py",
                 "def test_saudi_position_falls_back_to_competitors_summary")(),
        _needles("tests/test_lessons_enforcement.py", '(179, ')()),
    180: lambda: (
        _needles("silk_deep_pillars.py",
                 "hhi_nf, hhi_nf_src = _numeric_value_only(findings")(),
        _needles("tests/test_study14_live_defects.py",
                 "def test_direct_numeric_hhi_beats_structured_mirror")(),
        _needles("tests/test_lessons_enforcement.py", '(180, ')()),
    # ١٨١–١٨٥ — هدف الدراسة الاحترافية (البنود ١–٨): القواعد المعمّرة التي
    # أنشأتها الموجات ١–٨ — حارس واحد لكل عائلة، والسلوك تقفله ملفات
    # tests/test_goal_*.py نفسها.
    181: lambda: (
        _needles("silk_economics.py", "MARKET_UNIT_REGISTRY",
                 "def market_unit", "حساب هامش الربح ونقطة التعادل والخسارة المحتملة يحتاج")(),
        _needles("silk_quality_gate.py",
                 "def _check_unit_conversion_refusal",
                 "def _check_uncomputed_repetition")(),
        _needles("tests/test_goal_units_wave1.py",
                 "def test_every_litre_family_has_a_registered_density")(),
        _needles("tests/test_goal_cost_input_wave2.py", "def test_")(),
        _needles("tests/test_lessons_enforcement.py", '(181, ')()),
    182: lambda: (
        _needles("silk_style_contract.py", "CLIENT_TERM_REPLACEMENTS")(),
        _needles("silk_quality_gate.py",
                 "def _check_client_view_vocabulary",
                 "def _check_exec_summary_recommendation_first",
                 "def _check_exec_summary_constraints")(),
        _needles("silk_reports.py", "_CLIENT_SECTION_ORDER")(),
        _needles("tests/test_goal_vocab_wave3.py", "def test_")(),
        _needles("tests/test_goal_summary_wave4.py", "def test_")(),
        _needles("tests/test_lessons_enforcement.py", '(182, ')()),
    183: lambda: (
        _needles("silk_prose_meter.py", "def analyze")(),
        _needles("silk_inference.py", "def derive_hypotheses")(),
        _needles("silk_render.py", "def _hypotheses_safe")(),
        _needles("tests/test_goal_prose_wave5.py", "def test_")(),
        _needles("tests/test_goal_inference_wave6.py",
                 "def test_every_hypothesis_is_a_hypothesis_not_a_finding")(),
        _needles("tests/test_lessons_enforcement.py", '(183, ')()),
    184: lambda: (
        _needles("silk_economics.py", "def _mk_estimate", "TOO_WIDE_PCT",
                 "def build_decision_numbers")(),
        _needles("silk_quality_gate.py",
                 "def _check_estimate_fields_complete")(),
        _needles("tests/test_goal_estimation_wave7.py",
                 "def test_no_estimator_exists_for_binary_contractual_items",
                 "def test_too_wide_range_withholds_the_number")(),
        _needles("tests/test_lessons_enforcement.py", '(184, ')()),
    185: lambda: (
        _needles("api.py", "def _early_halt_enabled")(),
        _needles("silk_ai_judge.py", "_cache_prefix_text")(),
        _needles("tools/prompt_size_report.py", "PILLAR_FEEDING_MISSIONS")(),
        _needles("tests/test_goal_cost_wave8.py",
                 "def test_early_halt_does_not_change_the_engine_decision",
                 "def test_pillar_feeding_missions_map_matches_the_source")(),
        _needles("tests/test_lessons_enforcement.py", '(185, ')()),
    186: lambda: (
        _needles("silk_quality_gate.py",
                 'row.get("entry_decision") or row.get("decision")',
                 "def _competition_unit_finding")(),
        _needles("tests/test_s58_security_fixes.py",
                 "def test_min_pillars_guard_fires_on_the_real_view_key",
                 "def test_pillar_narrative_sync_fires_on_the_real_view_key")(),
        _needles("tests/test_gate_dead_guards_revival.py",
                 "def test_competition_unit_valid_still_covers_the_analyze_pillar_inputs_path")(),
        _needles("tests/test_lessons_enforcement.py", '(186, ')()),
    187: lambda: (
        _needles("silk_platform/throttle.py", "NAMED_WINDOW_DEFAULTS",
                 "def _max_window_s")(),
        _needles("silk_platform/api.py",
                 "throttle.record_failure(conn, ident_ip, limits)")(),
        _needles("tests/test_s58_security_fixes.py",
                 "def test_pwreset_request_cap_holds_for_the_full_declared_hour",
                 "def test_prune_respects_the_longest_named_window")(),
        _needles("tests/test_lessons_enforcement.py", '(187, ')()),
    188: lambda: (
        _needles("silk_usage.py", "def expected_run_usd", "def usd_spent_on")(),
        _needles("api.py", "day=_reserve_day")(),
        _needles("tests/test_money_path_day_bucket.py",
                 "def test_reconcile_applies_delta_to_the_reservation_day_not_today")(),
        _needles("tests/test_lessons_enforcement.py", '(188, ')()),
    189: lambda: (
        _needles("silk_platform/api.py", 'named_limits("VISION"',
                 "daily_paid_cap_exhausted")(),
        _needles("silk_platform/throttle.py", '"VISION"')(),
        _needles("tests/test_platform_paid_cap_coverage.py",
                 "def test_classify_image_is_throttled_per_account",
                 "def test_diagnostics_reserves_from_the_daily_paid_cap")(),
        _needles("tests/test_lessons_enforcement.py", '(189, ')()),
    190: lambda: (
        _needles("silk_platform/throttle.py", "def login_identity",
                 "def login_ip_identity")(),
        _needles("silk_platform/auth.py", "def cleanup_reset_tokens")(),
        _needles("tests/test_throttle_hardening.py",
                 "def test_login_identity_cannot_collide_with_a_named_counter",
                 "def test_login_ip_counter_bounds_password_spraying")(),
        _needles("tests/test_lessons_enforcement.py", '(190, ')()),
    191: lambda: (
        _needles("silk_deep_pillars.py",
                 '"fx_volatility_pct": (0.0, 100_000.0)')(),
        _needles("silk_consistency.py", "current_kind")(),
        _needles("silk_i18n.py", '"hs_caveat_box_nodesc"')(),
        _needles("tests/test_deferred_s58_fixes.py",
                 "def test_collapsed_currency_volatility_reaches_the_pillar_not_dropped",
                 "def test_history_lookup_ignores_a_newer_analyze_row_shadowing_research")(),
        _needles("tests/test_lessons_enforcement.py", '(191, ')()),
    192: lambda: (
        _needles("silk_platform/quota.py", "def reset_account_quota",
                 "quota_reset_at")(),
        _needles("migrations/platform/016_quota_reset_watermark.sql",
                 "quota_reset_at")(),
        _needles("tests/test_quota_reset_watermark.py",
                 "def test_admin_reset_clears_the_derived_per_user_counter")(),
        _needles("tests/test_lessons_enforcement.py", '(192, ')()),
    193: lambda: (
        _needles("silk_platform/quota.py", "launched_at: str | None = None",
                 'str(launched_at) < str(_wm)')(),
        _needles("silk_platform/jobs.py", "storage billing skipped account")(),
        _needles("tests/test_platform_audit_fixes.py",
                 "def test_release_after_reset_does_not_double_refund",
                 "def test_storage_billing_isolates_a_failing_account")(),
        _needles("tests/test_lessons_enforcement.py", '(193, ')()),
    # ── تدقيق شامل 2026-08-27 (AUDIT.md) — حارس لكل بند مُصلَح ──────────────
    194: lambda: (
        _needles("silk_llm_runtime.py", "wall_timeout_s", "wall_deadline",
                 "نافذتها الزمنية")(),
        _needles("silk_missions.py", "_WALL_GRACE_S",
                 '"wall_timeout_s": _MISSION_TIMEOUT_S + _WALL_GRACE_S')(),
        _needles("tests/test_audit_2026_08_27_fixes.py",
                 "def test_item1_wall_timeout_stops_before_the_next_paid_call",
                 "def test_item1_no_wall_timeout_keeps_todays_behaviour")(),
        _needles("tests/test_lessons_enforcement.py", '(194, ')()),
    195: lambda: (
        _needles("silk_sqlite.py", "def connect", "busy_timeout",
                 "LOCK_TIMEOUT_S")(),
        _needles("silk_storage.py", "silk_sqlite.connect")(),
        _needles("silk_store.py", "silk_sqlite.connect")(),
        _needles("silk_usage.py", "silk_sqlite.connect")(),
        _needles("silk_watchdog.py", "silk_sqlite.connect")(),
        _needles("silk_ops_log.py", "silk_sqlite.connect")(),
        _needles("tests/test_audit_2026_08_27_fixes.py",
                 "def test_item2_every_main_path_store_waits_for_the_lock")(),
        _needles("tests/test_lessons_enforcement.py", '(195, ')()),
    196: lambda: (
        _needles("tests/test_rung3_playwright_e2e.py", "def _rung_gate",
                 "pytest.fail")(),
        _needles(".github/workflows/e2e-live-shape.yml",
                 "test_rung2_factory_language_flow.py")(),
        _needles("tests/test_audit_2026_08_27_fixes.py",
                 "def test_item3_every_e2e_marked_rung_file_is_actually_run_by_the_job",
                 "def test_item4_rung3_environment_gaps_fail_loudly_inside_the_job")(),
        _needles("tests/test_lessons_enforcement.py", '(196, ')()),
    197: lambda: (
        _needles(".env.example", "SILK_RESEARCH_MAX_LLM_CALLS",
                 "COMTRADE_DAILY_BUDGET", "── DATABASE_URL")(),
        _needles("tests/test_env_documented.py",
                 "def test_every_env_var_read_by_production_code_is_documented")(),
        _needles("tests/test_lessons_enforcement.py", '(197, ')()),
    198: lambda: (
        _needles("tools/verify_backup.py", "integrity_check", "mode=ro")(),
        _needles("docs/DEPLOY_RAILWAY.md",
                 "نصفُ نسخةٍ احتياطية ليس نسخةً احتياطية",
                 "tools/verify_backup.py")(),
        _needles("tests/test_lessons_enforcement.py", '(198, ')()),
    200: lambda: (
        _needles("tools/gen_analyze_samples.py", "_had_own_request",
                 "del _dl2._session.request")(),
        _needles("tests/test_audit_2026_08_27_fixes.py",
                 "def test_network_block_leaves_no_instance_shadow_on_the_"
                 "shared_session")(),
        _needles("tests/test_lessons_enforcement.py", '(200, ')()),
    199: lambda: (
        _needles("tests/api_source.py", "def api_layer", "API_LAYER_FILES")(),
        _needles("silk_research_pipeline.py", 'logging.getLogger("api")',
                 "def build")(),
        _needles("tests/test_audit_2026_08_27_fixes.py",
                 "def test_item7_pipeline_module_never_imports_api_back",
                 "def test_item7_logger_identity_is_preserved")(),
        _needles("tests/test_lessons_enforcement.py", '(199, ')()),
    201: lambda: (
        _needles("silk_reports.py", "def bracket_orientation_counts",
                 "def classify_bracket_sequence", "def is_arabic_majority")(),
        _needles("requirements.txt", "pymupdf==")(),
        _needles("tools/rtl_calibration.py", "bidi: bool = True",
                 "E(bracket,NO-bidi=INVERTED)")(),
        _needles("tests/test_wp5_rtl_brackets.py",
                 "def test_count_suspicious_brackets_is_not_wired_into_"
                 "the_gate",
                 "def test_classify_ignores_unbalanced_row_no_false_alarm")(),
        _needles("tests/test_lessons_enforcement.py", '(201, ')()),
    202: lambda: (
        _needles("tests/test_wave2_first_pdf_cluster.py",
                 "def test_client_docx_source_keeps_arabic_character_order",
                 "xfail(strict=True")(),
        _needles("tests/test_lessons_enforcement.py", '(202, ')()),
    203: lambda: (
        _needles("tests/e2e/platform_language_flow.cjs",
                 "async function clearToast", "clearToast(page)",
                 "toast_not_cleared")(),
        _needles("tests/e2e/platform_flow.cjs",
                 "async function clearToast", "clearToast(page)",
                 "toast_not_cleared")(),
        _needles("tests/test_lessons_enforcement.py", '(203, ')()),
    204: lambda: (
        _needles("silk_pdf_textlayer.py", "def flip_cmap_bytes",
                 "def normalize_arabic_text_layer", "def cluster_score",
                 "_BFCHAR_BLOCK")(),
        _needles("silk_reports.py", "normalize_arabic_text_layer(")(),
        _needles("tests/test_pdf_textlayer.py",
                 "def test_units_are_reversed_not_hex_digits",
                 "def test_only_bfchar_sections_are_edited_never_bfrange")(),
        _needles("tests/test_lessons_enforcement.py", '(204, ')()),
    # ٢٠٥ — «الطاحونة»: رسالةٌ تُحيل إلى مرشّحين لا وجود لهم، وحارسٌ عربيٌّ
    # غائبٌ ترك «طحين» (دقيق) يشتري ثقة 0.88–0.93 لحلاوةٍ طحينية، ومرشّحو
    # البوّابة كانوا يُبنَون من البذرة المتروكة لا من مرجع الحلّ نفسه.
    205: lambda: (
        _needles("silk_hs_confirm.py",
                 "لا مرشّحين حتميّين لهذا الاسم",
                 'path: str = "data/hscodes_full.csv") -> list[dict]:')(),
        _needles("data/hscodes_full.csv", "حلاوة طحينية", "طحينة;طحينه")(),
        _needles("silk_platform/engine_bridge.py",
                 "def _catalog_candidates")(),
        _needles("tests/test_hs_halva_brandname_gap.py",
                 "def test_halva_resolves_to_sugar_confectionery_never_wheat_flour",
                 "def test_confidence_block_without_candidates_never_promises_a_list")(),
        _needles("tests/test_lessons_enforcement.py", '(205, ')()),
    # ٢٠٦ — التحليل ٢٧: نصُّ حالةٍ ثابتٌ فوق فروعٍ متعدّدة ناقض نفسه («اكتمل
    # التحليل» + «أوقفنا قبل التحليل»)، و«أكمل المصادر الغائبة» بلا اسمِ غائب.
    206: lambda: (
        _needles("silk_platform/engine_bridge.py",
                 'early = rep.get("skip_reason") == "early_halt"',
                 "اكتملت البعثات وحُفظت", "لا لعطلٍ تقني")(),
        _needles("silk_research_pipeline.py",
                 "from silk_decision import _AR as _PILLAR_AR",
                 "الجوانب الغائبة: ")(),
        _needles("tests/test_early_halt_reason_text.py",
                 "def test_early_halt_text_never_claims_the_analyst_ran",
                 "def test_early_halt_is_not_reported_as_a_failed_layer",
                 "def test_early_halt_failure_reason_names_the_missing_pillars")(),
        _needles("tests/test_lessons_enforcement.py", '(206, ')()),
    # ٢٠٧ — الرسالة تسمّي القياس لا العَرَض، والقصُّ يأكل التفصيل لا الذيل.
    207: lambda: (
        _needles("silk_research_pipeline.py",
                 "from silk_decision import _AR as _PILLAR_AR, _parts_ar",
                 "الناقص: ")(),
        _needles("silk_platform/engine_bridge.py",
                 "room = _REASON_MAX - len(head) - len(tail)",
                 "def _close_brackets")(),
        _needles("tests/test_early_halt_reason_text.py",
                 "def test_missing_pillars_name_their_missing_components",
                 "def test_truncation_eats_the_detail_not_the_tail")(),
        _needles("tests/test_lessons_enforcement.py", '(207, ')()),
    # ٢٠٨ — لا معرّفَ كودٍ في نصٍّ يقرؤه مصنع؛ العائلة تُغلَق بقفل تغطية.
    208: lambda: (
        _needles("silk_export_gate.py", "_CLIENT_REASONS",
                 "def client_reason(", "def client_reasons(",
                 '"blocked_reasons"', '"fail_driver_reasons"')(),
        _needles("web/platform.html", "blocked_reasons",
                 "fail_driver_reasons")(),
        _needles("silk_export_gate.py", "_GENERIC_REASON")(),
        _needles("tests/test_gate_client_reasons.py",
                 "def test_no_reachable_check_can_ever_render_as_a_raw_id",
                 "def test_no_visitor_sentence_leaks_a_check_id_or_a_code_token")(),
        _needles("tests/test_lessons_enforcement.py", '(208, ')()),
    # ٢٠٩ — استبدال المصدر لا تغطية عجزه بخيارات؛ `auto` وحدها تُكتَب.
    209: lambda: (
        _needles("silk_hs_from_image.py", "FORBIDDEN_CLIENT_KEYS",
                 "MANUAL_FALLBACK_MSG", 'str(out.get("tier")) != "auto"')(),
        _needles("silk_platform/api.py", "classify-image",
                 "classify_from_image(")(),
        _needles("web/platform.html", "function classifyImageBtn(p)")(),
        _absent("web/platform.html", "function hsPickBtn")(),
        _needles("tests/test_hs_from_image.py",
                 "def test_no_reply_ever_carries_options_or_a_confidence_number",
                 "def test_anything_below_auto_asks_for_the_code_never_guesses")(),
        _needles("tests/test_lessons_enforcement.py", '(209, ')()),
    # ٢١٠ — الثقةُ قياسٌ لا وسمُ مصدر؛ خطُّ تصنيفٍ واحد يستدعيه كلُّ مُنفِق.
    210: lambda: (
        _needles("silk_hs_pipeline.py", "def classify(",
                 "CATALOG_AUTO_APPROVED", "CATALOG_CONFLICT",
                 "REFUSAL_UNRESOLVED", '"refusal_code"')(),
        _needles("api.py", "def _classify_product_hs",
                 "user_supplied=_hs_user_supplied(req)")(),
        _needles("silk_platform/api.py",
                 'else str(body.get("hs_code") or "").strip())',
                 "hs_classification_method = ?")(),
        _absent("api.py",
                "hs_confidence = dp.confidence if dp.value is not None")(),
        _needles("tests/test_hs_catalog_revalidation.py",
                 "def test_catalog_disagrees_with_classifier_is_a_conflict"
                 "_not_a_silent_pick",
                 "def test_confidence_is_never_none_on_any_outcome")(),
        _needles("tests/test_lessons_enforcement.py", '(210, ')()),
    # ٢١١ — الاحتواءُ الحرفيّ ليس دليلاً؛ الوحدةُ الكاملة هي وحدةُ القياس.
    211: lambda: (
        _needles("silk_hs_norm.py", "def normalize(", "def tokens(",
                 "def same_token(")(),
        _needles("silk_hs_resolver.py", "_FUZZY_CAP", "def _score_keys",
                 "def retrieve(")(),
        _absent("silk_hs_resolver.py", "if contained and len(q) >= 3:")(),
        _absent("silk_hs_confirm.py", "if term in c or c in term:")(),
        _needles("tests/test_hs_substring_false_positives.py",
                 "def test_containment_alone_is_never_evidence_anywhere"
                 "_in_the_reference",
                 "def test_paper_products_never_become_watermelons")(),
        _needles("tests/test_lessons_enforcement.py", '(211, ')()),
    # ٢١٢ — مَن يفتح اتصالاً يُغلقه؛ والمؤقّتات تُكنَس عند حدود العملية.
    212: lambda: (
        _needles("silk_storage.py", "def _open(", "conn.close()")(),
        _needles("silk_store.py", "def _open(", "conn.close()")(),
        _needles("silk_usage.py", "def _open(", "conn.close()")(),
        _needles("silk_ops_log.py", "def _open(", "conn.close()")(),
        _needles("tests/conftest.py", "_install_tmpdir_tracking",
                 "def pytest_unconfigure")(),
        _needles("tests/test_sqlite_connection_hygiene.py",
                 "def test_no_storage_module_uses_a_connection_as_a_bare"
                 "_context_manager",
                 "def test_temp_dirs_are_swept_at_session_end")(),
        _needles("tests/test_lessons_enforcement.py", '(212, ')()),
    # ٢١٣ — المخرجُ الثالث: مصنّفٌ مُرسًى على الإخفاق وحده، بدرجة `auto`.
    213: lambda: (
        _needles("silk_hs_pipeline.py", "def _llm_fallback(",
                 "METHOD_LLM_GROUNDED", 'tier != "auto"')(),
        _needles("api.py", "allow_claude=_classify_general_allow_claude()")(),
        _needles("docs/HS_CLASSIFICATION.md", "llm_grounded")(),
        _needles("tests/test_hs_llm_fallback.py",
                 "def test_a_deterministic_hit_never_calls_the_model",
                 "def test_anything_below_auto_asks_and_never_guesses",
                 "def test_a_catalog_conflict_is_not_handed_to_the_model")(),
        _needles("tests/test_lessons_enforcement.py", '(213, ')()),
    # ٢١٤ — مصطلحٌ عامٌّ على بندٍ خاصّ: مقياسٌ مقفولٌ على ألّا ينمو.
    214: lambda: (
        _needles("tests/test_hs_generic_term_granularity.py",
                 "_BASELINE", "def test_the_family_never_grows",
                 "def test_the_worst_cases_stay_visible")(),
        _needles("evals/hs_golden_set.csv", "تمور سكري", "بولي إيثيلين")(),
        _needles("tests/test_lessons_enforcement.py", '(214, ')()),
    # ٢١٥ — R2: سجلّ التشغيلات الدائم — القاعدة تملك دورة التشغيلة، لا الخيط.
    215: lambda: (
        _needles("silk_platform/study_runtime.py", "def dispatch",
                 "BEGIN IMMEDIATE", "def recover", "def shutdown",
                 "def request_cancel", "heartbeat_at")(),
        _needles("migrations/platform/018_study_runs.sql",
                 "ux_study_runs_active", "IF NOT EXISTS")(),
        _needles("silk_platform/engine_bridge.py", "def _close_run_row",
                 "def _finish_if_cancelled")(),
        _needles("silk_platform/api.py", "study_runtime.create_run",
                 'add_event_handler("shutdown", study_runtime.shutdown)')(),
        _needles("tests/test_platform_study_runtime.py",
                 "def test_shutdown_interrupts_active_runs_and_never_completes_them",
                 "def test_the_cap_is_never_exceeded",
                 "def test_a_stale_run_is_interrupted_with_refund_pointer_and_notification")(),
        _needles("tests/test_lessons_enforcement.py", '(215, ')()),
    # ٢١٦ — R0: CI يمارس ما يمارسه النشر — بوّابات قبل الحزمة، صورة تُبنى وتُقلِع،
    # دخانٌ يدخل بوّابة المصانع، وأمرُ تشغيلٍ واحد (CMD الصورة).
    216: lambda: (
        _needles(".github/workflows/ci.yml",
                 "ruff check --select E9,F63,F7,F82", "pip-audit")(),
        _needles(".github/workflows/e2e-live-shape.yml",
                 "docker-health:", "docker build -t silk:ci .")(),
        _needles("tools/post_deploy_smoke.py", "def _check_platform(",
                 "/platform/auth/login", "/platform/me", "/platform/studies")(),
        _needles("railway.json", "--timeout-graceful-shutdown 15",
                 "SILK_FORWARDED_ALLOW_IPS")(),
        _needles("tests/test_audit_2026_09_01_r0.py",
                 "def test_railway_start_command_matches_the_image_cmd_byte_for_byte",
                 "def test_platform_lane_is_read_only_and_skips_loudly_without_credentials")(),
        _needles("tests/test_lessons_enforcement.py", '(216, ')()),
    # ٢١٧ — R1: مقروءٌ ≠ مكتمل؛ الإشعار بعد الالتزام؛ السياق يُنسَخ في الأب؛
    # الخطأ الداخلي بالرمز؛ ETA من المكتمل وحده.
    217: lambda: (
        _needles("silk_platform/engine_bridge.py", "def _orphan_analysis_verdict",
                 "def _notify_after_commit", "class EngineInternalError",
                 "WHERE state = 'completed' AND analysis_id IS NOT NULL")(),
        _needles("silk_context.py", "def map_with_context",
                 "def submit_with_context")(),
        _needles("silk_research.py", "silk_context.submit_with_context")(),
        _needles("tests/test_audit_2026_09_01_p0.py",
                 "def test_sweeper_never_completes_a_study_on_a_non_completed_analysis",
                 "def test_a_notification_failure_never_reverts_a_saved_success")(),
        _needles("tests/test_lessons_enforcement.py", '(217, ')()),
    # ٢١٨ — R3: النهاية تُسمّى (انقطعت/أُلغيت/تعثّرت)، كل انتقالٍ يُشعِر،
    # الحالةُ مشتقٌّ واحد، والاستطلاع يصمت في تبويبٍ مخفيّ.
    218: lambda: (
        _needles("silk_platform/study_runtime.py", "def last_run_view")(),
        _needles("silk_platform/notifications.py", "def notify_study_finish",
                 "def notify_study_finish_safely", "BODY_MAX")(),
        _needles("silk_platform/lifecycle.py", "notify_study_finish_safely")(),
        _needles("api.py", '"report_present"', '"degraded"', '"skip_reason"')(),
        _needles("web/platform.html", "function studyChip(", "RUN_STATE_AR",
                 "document.hidden", "visibilitychange")(),
        _needles("tests/test_audit_2026_09_01_r3.py",
                 "def test_status_reports_report_presence_degradation_and_skip_reason",
                 "def test_page_derives_one_unambiguous_chip_per_study")(),
        _needles("tests/test_lessons_enforcement.py", '(218, ')()),
    # ٢١٩ — R4: كلُّ بابٍ مدفوع تحت عدّاد الحساب، كلُّ مدخلٍ يُرفَض عند بابه،
    # مصدرُ البند يُمرَّر كما سُجِّل، والإقرارُ بالتنبيه فعلُ المصنع.
    219: lambda: (
        _needles("silk_platform/api.py", "def _study_hs_source",
                 "def _pending_advisories", "def _advisory_ack_applicable",
                 "def delete_image", '"error": "prerun_advisory"',
                 '"error": "storage_quota_exceeded"', '"error": "image_in_use"')(),
        _needles("silk_platform/engine_bridge.py", "def _refusal_code",
                 "def _detail_advisories")(),
        _needles("silk_platform/engine_bridge.py", "_SETTLED_HS_SOURCES",
                 "def _classification_method",
                 "COALESCE(?, hs_classification_method)")(),
        _needles("silk_platform/quota.py", "def storage_cap_bytes")(),
        _needles("silk_platform/tier_config.py", "def _monthly_for")(),
        _needles("migrations/platform/019_study_advisories_ack.sql",
                 "ALTER TABLE studies ADD COLUMN advisories_ack_at")(),
        _needles("web/platform.html", "function advisoryDialog(",
                 "أقرّ بالتنبيه وأطلق")(),
        _needles("tests/test_audit_2026_09_01_r4.py",
                 "def test_classify_product_image_is_throttled_per_account",
                 "def test_launch_with_an_advisory_refuses_before_any_claim",
                 "def test_settled_product_provenance_reaches_the_engine",
                 "def test_classify_image_on_a_foreign_product_is_404_and_audited",
                 "def test_concurrent_uploads_cannot_both_pass_the_storage_cap",
                 "def test_engine_side_advisory_refusal_is_actionable_on_the_draft_row")(),
        _needles("tests/test_lessons_enforcement.py", '(219, ')()),
    # ٢٢٠ — R5: ملفٌّ = معاملة، والقاعدةُ WAL، وكلُّ طابعٍ UTC، والنسخةُ تُستَرجَع.
    220: lambda: (
        _needles("silk_sqlite.py", "def iter_statements", "def journal_mode")(),
        _needles("silk_platform/db.py", "BEGIN IMMEDIATE",
                 "def _already_applied_alter")(),
        _needles("silk_storage.py", "def _now_iso", "DELETE FROM market_scores",
                 "idx_market_scores_analysis")(),
        _needles("silk_backup.py", "def restore", "platform_files",
                 "integrity_check")(),
        _needles("silk_collectors.py", "silk_store._open()")(),
        _needles("silk_platform/scheduler.py", "def _scheduler_tick")(),
        _needles("silk_platform/jobs.py", "wallet.apply_entry")(),
        _needles("tests/test_sqlite_connection_hygiene.py", '"silk_collectors.py"')(),
        _needles("tests/test_audit_2026_09_01_r5.py",
                 "def test_platform_migration_file_rolls_back_entirely_and_boot_survives",
                 "def test_every_store_connection_runs_in_wal_with_normal_sync",
                 "def test_backup_includes_uploads_and_restore_round_trips")(),
        _needles("tests/test_lessons_enforcement.py", '(220, ')()),
    # ٢٢١ — R2b: مرآةُ study_runtime للمسار الجذري — نبضة، سقف، إلغاء، ختم إغلاق، حفظٌ داخل try.
    221: lambda: (
        _needles("silk_research_runtime.py", "def register", "def shutdown",
                 "def start_reaper", "BOOT_ID")(),
        _needles("api.py", '"error": "resume_still_running"', '"error": "research_busy"',
                 "/research/{analysis_id}/cancel", "research_run_create_failed")(),
        _needles("silk_storage.py", "usd_reconciled_actual",
                 "def reconcile_run_usd_final", "def orphan_stale_cutoff")(),
        _needles("silk_research_pipeline.py", '"report", dict(report_out)')(),
        _needles("silk_context.py", 'copy.deepcopy(c.get("llm_usage")')(),
        _needles("tests/test_audit_2026_09_01_r2b.py",
                 "def test_mission_checkpoints_and_progress_snapshots_beat_the_reaper_heartbeat",
                 "def test_resume_on_a_running_row_is_409_resume_still_running",
                 "def test_cancel_stops_a_background_run_at_the_next_stage_boundary",
                 "def test_reaper_tick_skips_runs_live_in_this_process",
                 "def test_resume_is_409_while_the_handle_is_live_even_if_the_row_was_reaped",
                 "def test_final_reconcile_writes_the_ledger_once_when_the_flag_write_fails",
                 "def test_thread_start_failure_releases_the_handle_and_marks_the_row_failed",
                 "def test_sync_failure_releases_the_http_slot_exactly_once",
                 "def test_shutdown_sets_the_outer_cancel_event_too",
                 "def test_sync_run_without_persist_gives_its_slot_back",
                 "def test_resumed_run_reconciles_its_fresh_reservation_not_the_previous_attempts",
                 "def test_root_cancel_refuses_platform_owned_runs",
                 "def test_tick_runs_the_janitor_once_per_hour_not_every_reap")(),
        _needles("tests/test_lessons_enforcement.py", '(221, ')()),
    # ── R7 — الأمن (تدقيق 2026-09-01): خنقٌ بهويّةٍ لا يملكها المهاجم، أسرارٌ لا
    # تسافر، حاويةٌ بلا جذر، جلسةٌ بعمرٍ مطلق، صورةٌ بمحتواها، تشخيصٌ للمشغّل.
    222: lambda: (
        _needles("silk_platform/throttle.py", "def login_email_identity")(),
        _needles("silk_platform/api.py", "def _reject_cross_site_cookie_get",
                 '"error": "image_content_mismatch"', "top_hs_chapters",
                 "def _deliver_reset_email_async")(),
        _needles("silk_platform/auth.py", "def session_absolute_hours")(),
        _needles("silk_platform/scheduler.py", "def _cleanup_due")(),
        _needles("api.py", "class _QueryTokenFilter", "Strict-Transport-Security",
                 "def _health_verbose_allowed", "_OWNER_ENV_ONLY")(),
        _needles("silk_data_layer.py", "Ocp-Apim-Subscription-Key", "def _comtrade_key")(),
        _needles("Dockerfile", "sha256sum -c", "useradd")(),
        _needles("docker/entrypoint.sh", "setpriv --reuid=silk")(),
        _needles("tests/test_audit_2026_09_01_r7.py", "def test_login_email_counter_holds_under_ip_rotation", "def test_root_rate_limit_shares_the_host_bucket_for_unvalidated_keys", "def test_comtrade_key_travels_as_a_header_read_per_call", "def test_comtrade_key_in_query_rollback_valve", "def test_fetch_failure_logs_never_carry_the_comtrade_key", "def test_cached_get_failure_log_is_redacted")(),
        _needles("tests/test_lessons_enforcement.py", '(222, ')()),
    # ── R9 — تشغيل Railway (تدقيق 2026-09-01): مسبارُ الحياة لقطةٌ من حلقة الحدث،
    # سقفُ الجسم قبل قراءته، LibreOffice تحت فتحة، استطلاعٌ يستجيب للإغلاق.
    223: lambda: (
        _needles("api.py", "async def health", "def _health_probe", '@app.get("/ready")',
                 "class _BodyLimitMiddleware", "pdf_busy_detail()", "def _kick_health_refresh")(),
        _needles("silk_storage.py", "def persistence_violation")(),
        _needles("silk_reports.py", "class PdfBusy", "def _run_soffice",
                 "start_new_session=True")(),
        _needles("silk_gmaps.py", "def stop_all", "_STOP.wait")(),
        _needles("silk_research_runtime.py", "def add_tick_hook", "silk_gmaps.stop_all()")(),
        _needles("docs/DEPLOY_RAILWAY.md", "/ready", "probe_age_s")(),
        _needles("tests/test_audit_2026_09_01_r9.py",
                 "def test_health_is_async_and_probes_nothing_per_request",
                 "def test_ready_runs_a_fresh_probe_is_rate_limited_and_503s_on_misconfig",
                 "def test_oversized_bodies_are_413_before_any_handler_runs",
                 "def test_pdf_conversion_is_bounded_and_busy_is_a_named_error",
                 "def test_pdf_timeout_kills_the_whole_process_group_and_frees_the_slot",
                 "def test_gmaps_poll_worker_exits_promptly_on_stop_all",
                 "def test_stale_health_snapshot_refreshes_on_read_without_the_reaper",
                 "def test_body_limit_is_outermost_and_rejects_before_auth_touches_the_db")(),
        _needles("tests/test_rung2_real_server.py",
                 "def test_health_answers_within_a_second_while_the_threadpool_is_saturated")(),
        _needles("tests/test_lessons_enforcement.py", '(223, ')()),
    # ── R6 — الواجهة (تدقيق 2026-09-01): رفوضٌ منظَّمة بلغة الزائر، لا كاش لـHTML،
    # استطلاعُ الإشعارات، مصدرُ الرمز، حقولٌ ميتة تُتجاهَل، حدُّ جدول الأدمِن معلَن.
    224: lambda: (
        _needles("silk_platform/api.py", "def _err", '_err(404, "not_found"',
                 '_err(401, "invalid_credentials"', '_err(422, "bad_hs_code"')(),
        _needles("api.py", '"Cache-Control"')(),
        _needles("web/platform.html", "_notifPoll", ".msg.warn{", "HS_SOURCE_AR",
                 "adminStudiesNote", "_loadAllOnce", 'name="pship"')(),
        _needles("tests/test_audit_2026_09_01_r6.py",
                 "def test_platform_api_raises_no_plain_string_details_outside_the_field_validators",
                 "def test_html_pages_carry_cache_control_no_cache_and_health_does_not",
                 "def test_notifications_poll_every_minute_and_refresh_on_tab_return",
                 "def test_dead_study_fields_are_ignored_on_create_and_patch",
                 "def test_admin_studies_page_is_100_by_default_500_at_most_and_the_page_says_so",
                 "def test_notif_menu_marks_read_only_after_the_server_confirms")(),
        _needles("tests/test_lessons_enforcement.py", '(224, ')()),
    # ── EXT — الخدمات الخارجية (تدقيق 2026-09-01): قاطعٌ يرفض بلا نداء، فشلٌ معلَن لا
    # يُنفَق مرّتين، مجمّعاتٌ تُغلَق عند جدارها، جدارٌ كلّي، نداءُ كلود مقيسٌ ومعدود.
    225: lambda: (
        _needles("silk_circuit.py", "class CircuitOpen")(),
        _needles("silk_data_layer.py", "class ThrottleBacklog", "def _timeout_pair_for",
                 "def _is_fetch_failed")(),
        _needles("silk_cache.py", "_FETCH_FAILED", "os.replace(")(),
        _needles("silk_missions.py", "shutdown(wait=False, cancel_futures=True)",
                 "def _bounded_augment")(),
        _needles("silk_context.py", "def deadline_context")(),
        _needles("silk_engine.py", "SILK_ANALYZE_DEADLINE_S", "skipped_layers")(),
        _needles("silk_llm_provider.py", "def _is_connect_phase")(),
        _needles("silk_ai_judge.py", "def _call_vision", "llm_calls_failed")(),
        _needles("silk_usage.py", "def release_paid_calls", "def vision_allowed")(),
        _needles("tests/test_audit_2026_09_01_ext.py",
                 "def test_open_breaker_raises_circuit_open_with_zero_network_calls",
                 "def test_a_failed_fetch_is_not_retried_live_by_the_caller",
                 "def test_mission_pool_shuts_down_without_waiting_and_cancels_pending",
                 "def test_analyze_respects_a_deadline_and_declares_the_layers_it_skipped",
                 "def test_non_connect_connection_errors_are_retried_at_most_once",
                 "def test_agents_fetch_through_the_hardened_path")(),
        _needles("tests/test_lessons_enforcement.py", '(225, ')()),
    # ── R8 — الاختبار (تدقيق 2026-09-01): رُتبةٌ رابعة على الخطّ الحقيقي، بيئةُ رُتبٍ
    # إنتاجية، بوّابةُ PDF واحدة، ترتيبٌ عشوائيّ ليليّ، فحصُ عبورٍ مُوَلَّد، حرّاسٌ سلوكيّون.
    226: lambda: (
        _needles("silk_llm_provider.py", "class FakeProvider", "def _production_signal")(),
        _needles("tools/live_shape_server.py", "_SESSION_SWITCHES")(),
        _needles("tests/pdf_gate.py", "def pdf_gate")(),
        _needles(".github/workflows/ci.yml", "test-production-switches", "gitleaks")(),
        _needles(".github/workflows/nightly-shuffle.yml", "randomly")(),
        _needles("tests/test_rung4_platform_real_bridge.py", "SILK_LLM_PROVIDER")(),
        _needles("tests/test_audit_2026_09_01_r8.py",
                 "def test_a_fake_llm_provider_is_registered_and_refused_under_a_production_signal",
                 "def test_the_rung_server_keeps_production_switches_unless_told_otherwise",
                 "def test_the_pdf_gate_is_shared_and_no_unconditional_soffice_skip_remains",
                 "def test_no_id_route_leaks_across_tenants",
                 "def test_the_four_named_registry_guards_are_behavioural")(),
        _needles("tests/test_lessons_enforcement.py", '(226, ')()),
    # ── P3 — التنظيف (تدقيق 2026-09-01): صمّامٌ لكلّ أثر، إعلانٌ حيث تنظر العين،
    # فشلٌ مغلقٌ للمرجع الغائب، حذفُ الميت، وحارسُ توثيقٍ عكسيّ يعرف طرقَ القراءة.
    227: lambda: (
        _needles("silk_platform/scheduler.py", "SILK_PLATFORM_STORAGE_BILLING")(),
        _needles("silk_platform/api.py", "def _duplicate_checkout",
                 "def _mark_changed_product_codes", "account_renamed")(),
        _needles("silk_platform/notifications.py", "up_to_id")(),
        _needles("silk_platform/seed.py", "demo_factories")(),
        _needles("web/platform.html", "product_code_changed")(),
        _needles("requirements.txt", "pydantic==")(),
        _needles("tests/test_env_documented.py",
                 "def test_every_documented_env_var_is_read_or_exempt")(),
        _needles("tests/e2e/platform_flow.cjs", 'ok("admin_rename_account")')(),
        _needles("tests/test_audit_2026_09_01_p3.py",
                 "def test_storage_billing_is_not_scheduled_unless_opted_in",
                 "def test_a_duplicate_checkout_is_recorded_once",
                 "def test_a_changed_product_code_is_declared_on_the_study_row",
                 "def test_mark_all_read_uses_a_watermark_not_a_blanket",
                 "def test_seeding_under_a_production_signal_creates_no_demo_data",
                 "def test_market_known_fails_closed_when_the_reference_is_unavailable")(),
        _needles("tests/test_lessons_enforcement.py", '(227, ')()),
    228: lambda: (
        _needles("tests/test_repo_repair_2026_09_06.py",
                 "def test_old_toast_timer_cannot_hide_a_new_message",
                 "def test_refused_resume_does_not_mark_the_saved_attempt_running",
                 "def test_resume_claim_has_one_winner_and_rejects_old_generations",
                 "def test_failed_resume_claim_returns_its_reservation_and_slot",
                 "def test_two_http_resumes_execute_one_pipeline_and_leave_no_double_reservation",
                 "def test_browser_ci_uses_production_font_pin_and_checksums",
                 "def test_supervisor_stop_interrupts_a_long_heartbeat_wait")(),
        _needles("tests/e2e/platform_flow.cjs", "factory_product_single_refresh")(),
        _needles("tests/test_platform_deep_real_path.py",
                 "def test_empty_evidence_halts_with_production_guard_and_refunds_quota")(),
        _needles("tests/test_lessons_enforcement.py", '(228, ')()),
    229: lambda: (
        _needles("tests/test_owner_followup_2026_09_07.py",
                 "def test_study_image_flow_never_exposes_candidate_lists_or_confidence",
                 "def test_plain_language_simplifies_cited_arabic_without_changing_url",
                 "def test_photo_classification_preserves_a_product_name_edited_in_flight",
                 "def test_replacing_a_photo_ignores_the_older_upload_response")(),
        _needles("tests/e2e/platform_flow.cjs", "study_photo_automatic_and_manual_paths")(),
        _needles("tests/test_lessons_enforcement.py", '(229, ')()),
    230: lambda: (
        _needles("tests/test_owner_hs_provenance.py",
                 "def test_direct_factory_source_reaches_deep_gateway",
                 "def test_resaving_legacy_code_does_not_invent_factory_confirmation",
                 "def test_client_cannot_claim_image_proof_or_confirm_an_unspecified_code",
                 "def test_manual_form_source_and_old_classify_button_completion_are_fenced")(),
        _needles("tests/e2e/platform_flow.cjs", "factory_manual_hs_persisted")(),
        _needles("tests/test_lessons_enforcement.py", '(230, ')()),
    234: lambda: (
        _needles("silk_style_contract.py", "FORBIDDEN_READER_PHRASES",
                 "CONTEXTUAL_READER_TOKENS", "SYSTEM_SENSE_CUES",
                 "READER_LANGUAGE_RULE")(),
        _needles("silk_quality_gate.py",
                 "def _check_reader_language_leak")(),
        _absent("silk_decision.py", "العمود الأقوى", "العمود الأضعف")(),
        _absent("silk_reports.py", "هامشك عند المضاهاة")(),
        _absent("silk_render.py", "هامشك عند المضاهاة")(),
        _needles("tests/test_lessons_enforcement.py", '(234, ')()),
    233: lambda: (
        _needles("tests/test_platform_report_recovery.py",
                 "test_writer_receives_the_same_missing_components_as_the_decision_panel",
                 "test_real_numeric_resolver_is_used_for_ambiguous_image")(),
        _needles("tests/e2e/platform_dialog_recovery.cjs", "scrollable", "agent_failed")(),
        _needles("tests/test_lessons_enforcement.py", '(233, ')()),
    232: _guard_forensic_raw_evidence,
    231: lambda: (
        _needles("tests/test_platform_study_runtime.py",
                 "def test_a_stray_active_run_row_is_superseded_on_relaunch",
                 "_blocking_engine(monkeypatch, 778)")(),
        _needles("tests/test_lessons_enforcement.py", '(231, ')()),
}

_TRAPS = [
    ("mock_passes_real_fails", "Mock-passes / real-fails",
     _needles("silk_render.py", "_deep_research_view")),
    ("markets_empty_misroute", "misroutes exporters",
     _guard_trap_markets_empty),
    ("two_sanitizers", "Two different sanitizers",
     _guard_trap_two_sanitizers),
    ("redaction_mangling", "Redaction mangling",
     _guard_trap_redaction_mangling),
    ("parallel_cache_window", "Parallel missions and the cache window",
     _guard_trap_parallel_cache_window),
    ("cap_counts_not_dollars", "Cap counted operations, not dollars",
     _needles("silk_usage.py", "def try_reserve_usd")),
    ("styled_not_wired", "Styled-but-never-wired UI affordance",
     _needles("web/index.html", 'data-id="',
              '$("#histList").addEventListener("click"')),
    ("silent_noop_family", "silent no-op has three forms",
     _needles("web/index.html", "function openStoredAnalysis",
              # حزمة الإغلاق، البند ٤: سلسلة /markets في بناء نيّة الدردشة
              # اكتسبت .catch عربياً (كانت ترفض صامتةً فتُعلّق مؤشّر الانتظار).
              "تعذّر تحميل قائمة الأسواق")),
    ("view_after_persist", "view attached AFTER persist",
     _guard_trap_view_after_persist),
    ("strip_plumbing_three_leaks", "leaked three raw forms",
     _guard_trap_strip_plumbing_three_leaks),
    ("orphan_reservation_leak", "Orphaned runs leak their USD reservation",
     lambda: (
         _needles("silk_storage.py", "def reap_orphan_research_runs",
                  "reconcile_usd", "SILK_ORPHAN_STALE_MINUTES")(),
         _needles("api.py", "reap_orphan_research_runs")(),
         _needles("silk_collectors.py", "reap_orphan_research_runs")())),
]


# ── حارس واحد لكل حادثة (تُوسَّع برمجياً لتقارير pytest واضحة) ────────────────

@pytest.mark.parametrize("row", sorted(_LESSONS), ids=[f"lessons-{n}" for n in sorted(_LESSONS)])
def test_lessons_incident_guard_holds(row):
    """كل صفّ في docs/LESSONS.md له حارس حيّ يُفشِل على عودة عائلته."""
    _LESSONS[row]()


@pytest.mark.parametrize("slug,match,check", _TRAPS,
                         ids=[t[0] for t in _TRAPS])
def test_operations_trap_guard_holds(slug, match, check):
    """كل فخّ في silk-operations §2 (THE TRAPS) له حارس حيّ."""
    check()


# ── الاختبار الشامل: التغطية كاملة ضدّ كلا السِّجلّين ─────────────────────────

def _lessons_row_numbers() -> list[int]:
    """أرقام صفوف السجلّ **بتكرارها** — قائمةٌ لا مجموعة (مراجعة §58، الثغرة
    #16): درسان مختلفان تحت رقمٍ واحد كانا يتساويان في المجموعة فيبقى القفلُ
    أخضر — وقد وقع فعلاً (صفّان برقم ١١٢ في يومٍ واحد). العدُّ يكشفه."""
    ledger = _read("docs/LESSONS.md")
    return [int(m.group(1))
            for m in re.finditer(r"^\|\s*(\d+)\s*\|", ledger, re.M)]


def _lessons_rows_in_ledger() -> set[int]:
    return set(_lessons_row_numbers())


def test_no_lesson_number_is_used_twice():
    """رقمُ الدرس معرّفٌ فريد: تكرارُه يعني درسين تحت مرساةٍ واحدة — أحدهما
    بلا حارسٍ فعليّ بينما يبدو الجميعُ مغطّى."""
    nums = _lessons_row_numbers()
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    assert not dupes, (
        f"أرقام دروس مكرّرة في docs/LESSONS.md: {dupes} — "
        "كل درسٍ رقمٌ فريد، وإلا غطّى حارسُ أحدِهما الآخرَ صامتاً")


def _trap_rows_in_skill() -> list[str]:
    """صفوف بيانات جدول §2 (THE TRAPS) — الخلية الأولى (اسم الفخّ العريض)."""
    skill = _read(".claude/skills/silk-operations/SKILL.md")
    m = re.search(r"## 2\. THE TRAPS(.*?)\n## 3\.", skill, re.S)
    assert m, "قسم §2 THE TRAPS غير موجود في مهارة silk-operations"
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("| **"):        # صفوف البيانات فقط
            continue
        first_cell = line.split("|")[1].strip()
        rows.append(first_cell)
    return rows


def test_meta_registry_covers_every_known_incident():
    """التغطية الشاملة: كل صفّ LESSONS وكل فخّ §2 مُسجَّل هنا بحارس، ولا مدخلة
    يتيمة بلا صفّ مقابل. حادثة جديدة تسقط في أي سِجلّ بلا حارس تُحمِّر هنا."""
    # (أ) LESSONS: مفاتيح السجلّ = أرقام الصفوف بالضبط، متتابعة ١..N.
    ledger_rows = _lessons_rows_in_ledger()
    assert ledger_rows == set(range(1, max(ledger_rows) + 1)), (
        f"أرقام صفوف LESSONS غير متتابعة: {sorted(ledger_rows)}")
    registry_rows = set(_LESSONS)
    assert registry_rows == ledger_rows, (
        f"صفوف LESSONS بلا حارس في السجلّ: {sorted(ledger_rows - registry_rows)}؛ "
        f"حُرّاس بلا صفّ: {sorted(registry_rows - ledger_rows)}")

    # (ب) TRAPS: كل صفّ فخّ في §2 يطابقه حارس واحد بالضبط عبر إبرة `match`،
    # وكل حارس فخّ يطابق صفّاً واحداً على الأقل (لا يتيم).
    trap_rows = _trap_rows_in_skill()
    assert trap_rows, "لم تُقرَأ صفوف فخاخ من المهارة"
    for row in trap_rows:
        matched = [slug for slug, match, _ in _TRAPS if match in row]
        assert len(matched) == 1, (
            f"صفّ الفخّ «{row[:60]}…» يطابقه {len(matched)} حُرّاس (المتوقّع ١): "
            f"{matched}")
    for slug, match, _ in _TRAPS:
        assert any(match in row for row in trap_rows), (
            f"حارس الفخّ «{slug}» (match={match!r}) لا يطابق أيّ صفّ في §2 — "
            "يتيم؛ حدِّث السجلّ أو المهارة")


def test_meta_docx501_trio_all_have_behavioral_guards():
    """الحوادث الثلاث لعطل docx-501 (LESSONS ٣/١١/١٣) لها حُرّاس **سلوكية**
    (تبني/تنقّي فعلياً)، لا مجرّد وجود رمز — أمر المُشرِف الصريح."""
    behavioral = {3: _guard_docx501_row3, 11: _guard_docx501_row11,
                  13: _guard_docx501_row13}
    for row, guard in behavioral.items():
        assert _LESSONS[row] is guard, (
            f"صفّ docx-501 رقم {row} ليس مربوطاً بحارسه السلوكي")
        guard()  # يجب أن يمرّ فعلياً الآن
