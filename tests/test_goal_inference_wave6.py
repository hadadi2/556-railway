"""هدف الدراسة الاحترافية — الموجة ٦: الاستدلال العابر للمهمات (البند ٦).

المقفول: ستة أنماط عامة (لا قواعد حليب) تُخرج **فرضيات لا نتائج** — كل
إطلاق يحمل الوقائع + تفسيرين مرشحين + الأرجح ولماذا + الفحص الحاسم؛
حتمي stdlib بلا شبكة (AST)؛ لا مساس بالحكم (عرض إضافي، وقفل خط الأساس
في السويت)؛ السلاسل السنوية أحادية المقياس (درس 178) ومُسنوّاة الفجوات؛
والوقائع الخمس لدراسة #14 (كما في أمر الهدف) تُطلق أنماطها فعلاً.
"""
import ast
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import block_network


def _f(value, note, source="مصدر عمومي"):
    return {"value": value, "note": note, "source": source,
            "confidence": 0.8}


# دراسة بشكل وقائع #14 (من نص أمر الهدف — لا بيانات إنتاجية):
# استحواذ المراعي على أكبر موزّع + قفزة 2023→2024 + حصة 84% + بحث بروتين
# +200% غائب من الموردين + رمضان 1.9 مقابل عام 83.
_S14 = {"product": "حليب", "missions": {
    "trade_flow": {"findings": [
        _f(6_950_000, "واردات الأردن 2023 تحت الرمز 040120، USD"),
        _f(18_640_000, "واردات الأردن 2024 تحت الرمز 040120، USD"),
        _f(84.0, "حصة السعودية من واردات البند 84%")]},
    "competitors": {"findings": [
        _f("خبر", "استحوذت المراعي على شركة حمودة أكبر موزّع محلي في 2024"),
        _f(9040, "HHI محسوب من حصص الرمز")]},
    "channels_importers": {"findings": [
        _f("قائمة", "الموردون المرصودون: المراعي، نادك، حليبنا")]},
    "demand_trends": {"findings": [
        _f("صاعد", "نمو 200% في بحث حليب بروتين خلال سنتين"),
        _f(1.9, "مؤشر بحث رمضان حليب — الموسم"),
        _f(83.0, "مؤشر البحث العام عن حليب")]},
    "risk_news": {"findings": [
        _f(0.709, "سعر الصرف الرسمي مستقر — الدينار مربوط بالدولار")]},
}}


def test_study14_shaped_facts_fire_their_patterns():
    from silk_inference import derive_hypotheses
    with block_network():
        hyps = {h["pattern"]: h for h in derive_hypotheses(_S14)}
    assert "channel_redirection" in hyps          # استحواذ + قفزة 168%
    assert "unserved_niche" in hyps               # بروتين +200% وغائب
    assert "no_seasonal_stockpiling" in hyps      # 1.9 مقابل 83
    assert "currency_stable" in hyps              # ربط معلن


def test_every_hypothesis_is_a_hypothesis_not_a_finding():
    """حاكمية البند ٦: تفسيران على الأقل + الأرجح ولماذا + فحص حاسم +
    وسم «فرضية للتحقق» — بنيوياً على كل إطلاق."""
    from silk_inference import derive_hypotheses
    for h in derive_hypotheses(_S14):
        assert len(h["explanations"]) >= 2, h["pattern"]
        assert h["likelier"] and h["why"], h["pattern"]
        assert h["settling_check"], h["pattern"]
        assert "فرضية" in h["status"]
        assert h["facts"], h["pattern"]


def test_neutral_study_fires_nothing():
    """النمط الذي يطلق على كل شيء عديم القيمة — دراسة هادئة: صفر إطلاق."""
    from silk_inference import derive_hypotheses
    neutral = {"product": "تمور", "missions": {
        "trade_flow": {"findings": [
            _f(30_000_000, "واردات 2022 تحت الرمز 080410، USD"),
            _f(33_000_000, "واردات 2023 تحت الرمز 080410، USD")]},
        "competitors": {"findings": [_f(1200, "HHI محسوب من الحصص")]},
    }}
    assert derive_hypotheses(neutral) == []


def test_series_are_single_metric_and_annualized():
    """درس 178: لا خلط أسس في سلسلة واحدة؛ وفجوة سنوات تُسنوَّى فلا يُقرأ
    «-63% عبر أربع سنوات» تقلباً سنوياً فوق 40%."""
    from silk_inference import _yearly_series, _yoy_moves
    dr = {"missions": {"trade_flow": {"findings": [
        _f(880_000, "إجمالي استيراد 2018، USD"),
        _f(5_590_000, "إجمالي استيراد 2019، USD"),
        _f(2_090_000, "إجمالي استيراد 2023، USD"),
        _f(22_140_000, "مرآة صادرات السعودية 2023، USD")]}}}
    series = _yearly_series(dr, "trade_flow")
    # المرآة نقطة واحدة فلا تكوّن سلسلة — والأهم: لم تُخلَط بسلسلة
    # الاستيراد المباشر (لا 22.14M في أي حركة).
    assert len(series) == 1
    assert all("مرآة" not in k for k in series)
    moves = dict((round(p), d) for p, d, _ in _yoy_moves(dr, "trade_flow"))
    assert 535 in moves                          # 2018→2019 سنوية فعلاً
    assert -22 in moves and "مركّباً" in moves[-22]   # 2019→2023 مُسنوّاة


def test_wrong_heading_names_the_bigger_category():
    from silk_inference import derive_hypotheses
    dr = {"product": "حليب", "missions": {"consumer_culture": {"findings": [
        _f("توزيع", "الزبادي 52% من استهلاك الألبان بينما حليب سائل 16%")]}}}
    hyps = [h for h in derive_hypotheses(dr)
            if h["pattern"] == "wrong_heading"]
    assert hyps and "الزبادي" in hyps[0]["title"]


def test_inference_is_stdlib_only_and_never_touches_the_verdict():
    import silk_inference
    tree = ast.parse(inspect.getsource(silk_inference))
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree)
                if isinstance(n, ast.Import)}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom)}
    assert imported <= {"re", "__future__"}, imported
    # الحكم لا يُمسّ بنيوياً: لا استيراد لوحدتي الحكم إطلاقاً (AST أعلاه
    # يضمن stdlib فقط، وهذه الإبر تلتقط حتى الاستيراد الكسول النصي).
    src = inspect.getsource(silk_inference)
    for banned in ("import silk_synthesis", "import silk_decision",
                   "from silk_synthesis", "from silk_decision"):
        assert banned not in src, banned


def test_view_carries_hypotheses_and_render_shows_them(tmp_path):
    import pytest
    pytest.importorskip("docx")
    from silk_render import build_view
    from silk_reports import render_client_docx, render_markdown
    from conftest import docx_all_text
    result = {"product": "حليب", "hs_code": "040120", "year": 2024,
              "report_language": "ar", "markets": [], "test_run": True,
              "deep_research": {
                  **_S14,
                  "market": {"iso3": "JOR", "name_ar": "الأردن",
                             "name_en": "Jordan"},
                  "verdict": {"verdict": "WATCH", "confidence": 0.6},
                  "verdict_label": "مراقبة السوق",
                  "report": {"text": "## 1. الخلاصة التنفيذية\n"
                                     "التوصية: تأجيل.\n"},
                  "limits": [], "gap_register": [],
                  "economics": {"gaps": []}}}
    with block_network():
        view = build_view(result)
    hyps = view["deep_research"]["hypotheses"]
    assert {h["pattern"] for h in hyps} >= {"channel_redirection",
                                            "unserved_niche"}
    md = render_markdown(view)
    assert "قراءات تلتقي عندها الأدلة" in md
    assert "ما يحسم:" in md
    path = os.path.join(tmp_path, "c.docx")
    with block_network():
        render_client_docx(view, path)
    text = docx_all_text(path)
    assert "قراءات تلتقي عندها الأدلة" in text
    assert "تفسيران مرشحان" in text