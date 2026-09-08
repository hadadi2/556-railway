"""البند 4 من أمر إصلاح المحرّك — التوصية تطابق بندَ بيانات التجارة.

الدليل (direct reproduction — تقرير #11): كل البيانات تحت HS 0401 (حليب غير
مركّز) بينما التوصية تستهدف المجفف/المكثف = بند 0402 مختلف كلياً — فالحجم
6.95M والحصة 84.05% وHHI 7118 والسعر $0.81 لا تنطبق على المنتج الموصى به.
المطلوب حرفياً: فحص مطابقة قبل التسليم يوقف التقرير برسالة صريحة. هرمتي. Run:
  python3 -m pytest tests/test_goal4_hs_recommendation_match.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_quality_gate as QG                           # noqa: E402


def _view(hs, text):
    return {"hs_code": hs,
            "deep_research": {"missions": {}, "report": {"text": text}},
            "markets": []}


_AR_BODY = (
    "## 1. الخلاصة التنفيذية\n"
    "توصي الدراسة باستهداف الحليب المجفّف في السوق الأردني.\n"
    "## 10. التوصيات الاستراتيجية\n"
    "يوصى بالتركيز على حليب البودرة عبر موزّع محلي.\n")


def test_acceptance_data_under_0401_recommendation_names_0402_halts():
    """قبول الأمر حرفياً: لا توصية بالمجفف/المكثف وبيانات تحت 0401."""
    out = QG.run_quality_gate(_view("040120", _AR_BODY))
    hits = [f for f in out["findings"]
            if f["check"] == "hs_recommendation_match"]
    assert hits and out["verdict"] == QG.FAIL
    # الرسالة صريحة: تسمّي السمة والبندين معاً
    assert "0402" in hits[0]["note"] and "0401" in hits[0]["note"]


def test_same_recommendation_under_0402_data_is_a_match_not_a_halt():
    out = QG.run_quality_gate(_view("040210", _AR_BODY))
    assert not [f for f in out["findings"]
                if f["check"] == "hs_recommendation_match"]


def test_mention_outside_recommendation_windows_is_legitimate():
    """ذكر 0402 في شرح تعريف البند أو جدول أسعار التجزئة مشروع — الفحص
    نافذيّ (الدرس ٤٢)، لا مسح لكامل المستند."""
    body = ("## 1. الخلاصة التنفيذية\n"
            "توصي الدراسة بدخول مشروط بالحليب السائل.\n"
            "## 6. المشهد التنافسي\n"
            "رُصد حليب نيدو المجفف في التجزئة عند 9.00 دينار (سياق تسعير).\n"
            "## 10. التوصيات الاستراتيجية\n"
            "يوصى بموزّع مدرج في القائمة الذهبية.\n")
    out = QG.run_quality_gate(_view("040120", body))
    assert not [f for f in out["findings"]
                if f["check"] == "hs_recommendation_match"]


def test_diacritics_do_not_evade_the_needle():
    body = ("## 10. التوصيات الاستراتيجية\n"
            "الأجدى استهداف الحليب المكثّف والمجفّف.\n")
    out = QG.run_quality_gate(_view("040120", body))
    assert [f for f in out["findings"]
            if f["check"] == "hs_recommendation_match"]


def test_english_window_and_needle():
    body = ("## 10. Strategic Recommendations\n"
            "Target powdered milk through a listed distributor.\n")
    out = QG.run_quality_gate(_view("040120", body))
    assert [f for f in out["findings"]
            if f["check"] == "hs_recommendation_match"]


def test_no_hs_code_or_no_text_is_silent():
    assert QG._check_hs_recommendation_match(_view("", _AR_BODY)) == []
    assert QG._check_hs_recommendation_match(_view("040120", "")) == []
    # رمز غير رقمي (عطب إدخال) لا يفجّر الفحص
    assert QG._check_hs_recommendation_match(_view("ABCD12", _AR_BODY)) == []


def test_one_finding_per_attribute_not_per_needle():
    """«الحليب المجفف» بإبرتين (معرّفة/نكرة) = ملاحظة واحدة لا اثنتان."""
    body = ("## 10. التوصيات الاستراتيجية\n"
            "يوصى بالحليب المجفف، وتحديداً أي حليب مجفف كامل الدسم.\n")
    hits = QG._check_hs_recommendation_match(_view("040120", body))
    assert len(hits) == 1


def test_check_is_a_fail_trigger():
    assert "hs_recommendation_match" in QG._REGRESSION_GUARD_FIRED
