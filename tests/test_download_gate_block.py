"""إعادة إنتاج حجب تنزيل تقرير الدراسة #12 (بلاغ المالك 2026-08-25).

الحادثة: تنزيل docx/pdf للدراسة #12 رُدّ بـ409 `quality_gate_fail` بحمولة
`blocked_checks: [style_connector_excess, style_repeated_key_figure ×2,
trends_hollow_completion]`. تشخيص القراءة (silk_quality_gate.run_quality_gate
+ silk_export_gate.evaluate): القائمة تسرد **كل** الملاحظات غير القابلة
للإصلاح، بينما حكم FAIL يقوده فقط `_REGRESSION_GUARD_FIRED` ∪
(غير قابل للإصلاح ∩ `FAIL_TRIGGER_CHECKS`) — فمن الأسماء الأربعة واحدٌ
فقط هو المُفشِل (`style_connector_excess`: أداة ربط ≥5 مرات)، والباقي
ملاحظات حاجبة غير قائدة. هذا الملف يعيد إنتاج الشكل كاملاً هرمتياً ويقفل
حقل `fail_drivers` الإضافي الذي يمنع قراءة القائمة كأسباب مجدداً.
هرمتي. Run: python3 -m pytest tests/test_download_gate_block.py -q
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

import silk_export_gate as EG                            # noqa: E402
import silk_render as R                                  # noqa: E402
from canonical_netherlands import netherlands_research_blob  # noqa: E402

# نثرٌ بشكل عيوب #12 حرفياً: «من ناحية» خمس مرات (سقف Part B مرتان)،
# ورقمان مفتاحيان مكرّران ثلاثاً (حصة 95.04% كحصة الدراسة #12 الحقيقية).
_STUDY12_STYLE_PARA = (
    "\n\nمن ناحية حجم السوق، بلغت حصة المورد الأكبر 95.04% في 2024. "
    "من ناحية التسعير، تبقى الفجوة السعرية ضيقة أمام الداخل الجديد. "
    "من ناحية اللوجستيات، يمر معظم التدفق عبر ميناء واحد. "
    "من ناحية التنظيم، تشترط الجهة المستوردة شهادة حلال مصدقة. "
    "من ناحية الطلب، تتركز حصة 95.04% لدى قنوات التجزئة الكبرى، "
    "بينما نما الطلب المبرد بنسبة 41.7% خلال ثلاث سنوات. "
    "وتؤكد المقابلات أن حصة 95.04% تحد من هامش المناورة، "
    "وأن نمو 41.7% مرشح للاستمرار، إذ تدعم سلاسل التبريد نموا بواقع 41.7% "
    "في القنوات الحديثة.")

# ملخّص بعثة اتجاهات «غير فاشلة» يعلن فجوة الموسمية بنفسه — مُطلِق
# trends_hollow_completion (PR B §B5) كما في demand_trends بالدراسة #12.
_HOLLOW_TRENDS_MISSION = {
    "summary": "فجوة بيانات الاتجاهات الموسمية: ذروة رمضان مجهولة لدى البعثة",
    "failed": False,
    "findings": [{"note": "أثر تتبع الموسمية بلا بيانات صالحة"}],
}


def _study12_shaped_view():
    view = R.build_view(netherlands_research_blob(), "ar")
    rep = view["deep_research"]["report"]
    rep["text"] = rep["text"] + _STUDY12_STYLE_PARA
    view["deep_research"].setdefault("missions", {})["demand_trends"] = \
        dict(_HOLLOW_TRENDS_MISSION)
    return view


_OWNER_PAYLOAD_CHECKS = ("style_connector_excess", "style_repeated_key_figure",
                         "style_repeated_key_figure", "trends_hollow_completion")


def test_study12_shaped_defects_block_the_client_export():
    """direct reproduction: نفس شكل حمولة 409 التي تسلّمها المالك —
    FAIL، وblocked_checks تضم الأسماء الأربعة (الرقم المفتاحي مرتين)."""
    dec = EG.evaluate(_study12_shaped_view())
    assert dec["verdict"] == "FAIL"
    assert EG.is_blocked(dec)
    got = EG.factory_detail(dec["digest"], "ar")["blocked_checks"]
    for name in set(_OWNER_PAYLOAD_CHECKS):
        assert got.count(name) >= _OWNER_PAYLOAD_CHECKS.count(name), (name, got)


def test_connector_excess_is_the_only_driver_among_the_four():
    """من الأسماء الأربعة، `style_connector_excess` وحده يقود FAIL —
    الرقم المفتاحي المكرّر (3–4) وبعثة الاتجاهات الجوفاء ملاحظتان حاجبتان
    غير قائدتين (خارج `_REGRESSION_GUARD_FIRED` و`FAIL_TRIGGER_CHECKS`)."""
    dec = EG.evaluate(_study12_shaped_view())
    drivers = dec["fail_drivers"]
    assert "style_connector_excess" in drivers
    assert "style_repeated_key_figure" not in drivers
    assert "trends_hollow_completion" not in drivers


def test_part_b_compliant_text_passes_the_export_gate():
    """الاتجاه المعاكس: النص القانوني الملتزم بسقفَي Part B (روابط ≤2،
    رقم مفتاحي ≤2) وبلا بعثة اتجاهات جوفاء لا يُحجَب — أي أن إعادة توليد
    #12 بموجّه Part B تفتح التنزيل."""
    dec = EG.evaluate(R.build_view(netherlands_research_blob(), "ar"))
    assert dec["verdict"] != "FAIL"
    assert not EG.is_blocked(dec)
    assert dec["fail_drivers"] == []


def test_trends_hollow_completion_blocks_nothing_alone():
    """البعثة الجوفاء وحدها (بلا عيوب أسلوبية) ملاحظة منهجية حاجبة في
    القائمة لكنها لا تقلب الحكم FAIL — التنزيل لا يُحجَب بسببها."""
    view = R.build_view(netherlands_research_blob(), "ar")
    view["deep_research"].setdefault("missions", {})["demand_trends"] = \
        dict(_HOLLOW_TRENDS_MISSION)
    dec = EG.evaluate(view)
    assert dec["verdict"] != "FAIL"
    assert "trends_hollow_completion" in [
        f["check"] for f in dec["blocking"]]
    assert "trends_hollow_completion" not in dec["fail_drivers"]


def test_fail_drivers_field_is_additive_only():
    """الحقل إضافي: الشكل القائم للحمولتين لا يتغيّر بلا تمريره، ويظهر
    مقصوصاً كسلاسل عند تمريره — على السطحين (مشغّل/مصنع)."""
    digest = [{"check": "style_connector_excess", "note": "n"},
              {"check": "trends_hollow_completion", "note": "n"}]
    plain_op = EG.operator_detail(digest)
    plain_fc = EG.factory_detail(digest, "ar")
    assert "fail_drivers" not in plain_op and "fail_drivers" not in plain_fc
    op = EG.operator_detail(digest, fail_drivers=["style_connector_excess"])
    fc = EG.factory_detail(digest, "ar",
                           fail_drivers=["style_connector_excess"])
    assert op["fail_drivers"] == ["style_connector_excess"]
    assert fc["fail_drivers"] == ["style_connector_excess"]
    assert fc["blocked_checks"] == ["style_connector_excess",
                                    "trends_hollow_completion"]


def test_gate_crash_fail_still_names_a_driver():
    """احتياط evaluate: حكم FAIL بلا قائد محسوب (عطل بوابة) يعبّئ
    fail_drivers بأسماء الملاحظات الحاجبة — لا حمولة FAIL بلا سبب معلن."""
    import unittest.mock as mock
    with mock.patch("silk_quality_gate.run_quality_gate",
                    side_effect=RuntimeError("boom")):
        dec = EG.evaluate({"deep_research": {"report": {"text": "نص"}}})
    assert dec["verdict"] == "FAIL"
    assert dec["fail_drivers"] == ["gate_crash"]


def test_platform_409_payload_carries_fail_drivers():
    """سطح المصنع يمرّر القائد فعلاً: مصدر silk_platform/api.py يستدعي
    factory_detail بحقل fail_drivers من القرار (لا استنتاجاً)."""
    with open(os.path.join(_ROOT, "silk_platform", "api.py"),
              encoding="utf-8") as fh:
        src = fh.read()
    assert 'fail_drivers=decision.get("fail_drivers")' in src
    with open(os.path.join(_ROOT, "api.py"), encoding="utf-8") as fh:
        root_src = fh.read()
    assert 'fail_drivers=decision.get("fail_drivers")' in root_src
