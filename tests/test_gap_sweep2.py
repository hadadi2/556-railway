"""موجة سدّ الفجوات الثانية — أقفال (عدّاد التصعيد، أسطح صندوق التحذير،
مرجع HS الموسّع، سطح فحص الاتساق).

المصدر: تدقيق «find all gaps» الثاني (وكيل قراءة، file:line): معيار
التصعيد كان وعداً بلا آلية قياس؛ الصندوق غائب عن docx العميل ولوحة
المصنع ومكرر يدوياً في الأكاديمي؛ فحص الاتساق بلا سطح بشري؛ المرجع
ألبان فقط. هرمتي. Run: python3 -m pytest tests/test_gap_sweep2.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name: str) -> str:
    with open(os.path.join(_ROOT, name), encoding="utf-8") as fh:
        return fh.read()


# ── عدّاد معيار التصعيد (الدرس 135 صار قابلاً للقياس) ────────────────


def _row(i, status="completed"):
    return {"id": i, "status": status}


def _blob(findings=None, *, gate=True, test_run=False):
    dr = {}
    if gate:
        dr["quality_gate"] = {"verdict": "PASS",
                              "findings": list(findings or [])}
    return {"view": {"test_run": test_run, "deep_research": dr}}


def test_counter_three_clean_live_runs_ready():
    import silk_quality_gate as QG
    blobs = {1: _blob(), 2: _blob(), 3: _blob()}
    out = QG.consecutive_clean_runs(
        "absence_vocabulary", 3,
        _list=lambda: [_row(1), _row(2), _row(3)],
        _get=lambda i: blobs[i])
    assert out == {"check": "absence_vocabulary", "target": 3,
                   "streak": 3, "ready": True}


def test_counter_hit_breaks_the_streak():
    import silk_quality_gate as QG
    blobs = {1: _blob(), 2: _blob([{"check": "absence_vocabulary"}]),
             3: _blob()}
    out = QG.consecutive_clean_runs(
        "absence_vocabulary", 3,
        _list=lambda: [_row(1), _row(2), _row(3)],
        _get=lambda i: blobs[i])
    assert out["streak"] == 1 and out["ready"] is False


def test_counter_missing_gate_is_unknown_not_clean():
    """G9: بوابة تخطاها استثناء (لا مفتاح quality_gate) مجهولة لا نظيفة —
    تقطع العدّ ولا تصنع تصعيداً كاذباً."""
    import silk_quality_gate as QG
    blobs = {1: _blob(), 2: _blob(gate=False), 3: _blob()}
    out = QG.consecutive_clean_runs(
        "sentence_length", 3,
        _list=lambda: [_row(1), _row(2), _row(3)],
        _get=lambda i: blobs[i])
    assert out["streak"] == 1 and out["ready"] is False


def test_counter_skips_hermetic_runs_and_incomplete_rows():
    import silk_quality_gate as QG
    blobs = {1: _blob(test_run=True), 2: _blob(), 3: _blob(), 4: _blob()}
    out = QG.consecutive_clean_runs(
        "decimal_precision", 3,
        _list=lambda: [_row(1), _row(5, status="failed"),
                       _row(2), _row(3), _row(4)],
        _get=lambda i: blobs[i])
    assert out["streak"] == 3 and out["ready"] is True


# ── صندوق التحذير الواحد على كل الأسطح (تكملة البند 18) ──────────────


def test_caveat_box_consumed_on_every_surface():
    """G2/G4/G6: كل مُصدِّر يستهلك dr.caveat_box — لا باني بلا مستهلك."""
    reports = _src("silk_reports.py")
    assert reports.count("caveat_box") >= 3   # md + docx المشغل + docx العميل
    assert "caveat_box" in _src("web/index.html")
    assert "caveat_box" in _src("web/platform.html")


def test_academic_docx_has_single_caveat_not_two():
    """G3: القالب الأكاديمي كان يعيد صياغة التحذير مرتين يدوياً — بقي
    نصه الكامل في §٢ وحدها وفي الخلاصة إحالةٌ لا تكرار."""
    reports = _src("silk_reports.py")
    assert "القيد المنهجي الحاكم: رمز التصنيف الجمركي" not in reports
    assert "مفصَّل في قسم «المنهجية ومصادر البيانات»" in reports
    assert "قيد منهجي جوهري" in reports


def test_caveat_box_is_bilingual_via_i18n():
    """صندوق بلغة التقرير — نص عربي في docx إنجليزي خرقٌ لجدار اللغة."""
    import silk_i18n
    ar = silk_i18n.t("hs_caveat_box", "ar", tag="ت", hs="040110", desc="و")
    en = silk_i18n.t("hs_caveat_box", "en", tag="Contextual indicator",
                     hs="040110", desc="milk")
    assert "040110" in ar and "040110" in en
    assert not any("؀" <= ch <= "ۿ" for ch in en)


# ── مرجع HS خارج الألبان (تكملة البند 9) ─────────────────────────────


def test_hs_reference_covers_all_canonical_product_families():
    import silk_hs_reference as HR
    assert HR.definition("040900")            # عسل
    assert HR.definition("080410")            # تمور
    assert HR.definition("200811")            # زبدة فول سوداني
    assert HR.definition("850760")            # بطاريات — بند رباعي
    assert HR.definition("190219")            # عجائن — بند رباعي
    assert HR.definition("999999") is None    # خارج المرجع = غياب معلن


# ── سطح فحص اتساق التشغيلات (تكملة البند 7) ──────────────────────────


def test_verdict_consistency_reaches_operator_markdown():
    """G7: النتيجة والغياب كلاهما يُعلَن على سطح بشري لا للبوابة وحدها."""
    reports = _src("silk_reports.py")
    assert "فحص اتساق التشغيلات" in reports
    assert "لا تشغيلة سابقة مكتملة لنفس" in reports
    assert "previous_analysis_id" in reports
