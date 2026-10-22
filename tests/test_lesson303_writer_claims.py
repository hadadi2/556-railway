"""الدرس ٣٠٣ (PR-B البند د، قرار المالك): الكاتب يُخرج ادعاءاته الرقمية **منظّمة** — القيمة والوحدة
والسنة والمؤشر والأساس (مباشر/مرآة) والمصدر — فتُفحص البياناتُ حتمياً بدل تحليل النثر العربي.

* سياجٌ أخير ```claims {"claims": [...]}``` في مخرَج الكاتب يُنزَع فورَ وصوله (لا يصل العميلَ ولا
  منطقَ الاكتمال والإكمال) ويُحفظ مع عقدة التقرير.
* الفحص C1 يقارن كلَّ ادعاءٍ بالسلسلة والسجلّ: رقمُ مرآةٍ مُعلَنٌ مباشراً، قيمةٌ تخالف سنتَها، نموٌّ أو
  مركّبٌ غير المحسوب من السنوات المصرّحة (213%/20.9% في الدراسة ١) — في وضع الظلّ (البند ب).

Lesson 303 locks: structured numeric claims from the writer. Written test-first.
"""
import json
import os
import sys
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools"), os.path.join(_ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from test_lesson300_series_head import _bahrain_blob    # noqa: E402

_BODY = ("## 1. الخلاصة التنفيذية\n\nبلغت واردات البحرين من القهوة المحمّصة 9.17 مليون دولار في 2024، "
         "ونمت 89.9% منذ 2019.\n")


def _fence(claims) -> str:
    return "\n\n```claims\n" + json.dumps({"claims": claims}, ensure_ascii=False) + "\n```\n"


GOOD = [{"v": 9.17, "unit": "مليون دولار", "year": 2024, "indicator": "imports",
         "basis": "direct", "source": "UN Comtrade"},
        {"v": 89.9, "unit": "%", "year": 2024, "indicator": "imports_growth",
         "basis": "direct", "source": "UN Comtrade"}]


def test_strip_removes_the_block_and_parses_claims():
    import silk_writer_claims as W
    text, claims, status = W.strip(_BODY + _fence(GOOD))
    assert text.strip() == _BODY.strip() and "```" not in text
    assert status == "ok" and claims[0]["v"] == 9.17 and claims[1]["indicator"] == "imports_growth"


def test_strip_declares_missing_invalid_and_truncated_blocks():
    import silk_writer_claims as W
    assert W.strip(_BODY)[2] == "missing" and W.strip(_BODY)[0] == _BODY
    t, c, s = W.strip(_BODY + "\n```claims\n{not json}\n```\n")
    assert s == "invalid" and c is None and "```" not in t
    t, c, s = W.strip(_BODY + "\n```claims\n{\"claims\": [{\"v\": 9.1")     # بُتر عند سقف الرموز
    assert s == "truncated" and "```" not in t and t.strip() == _BODY.strip()


def _found(claims, text=_BODY, status="ok"):
    b = _bahrain_blob()
    b["deep_research"]["report"] = {"report": text, "review_cycles": 1, "unresolved_notes": [],
                                    "claims": claims, "claims_status": status}
    return b


def test_c1_passes_correct_direct_claims():
    import silk_writer_claims as W
    f = W.check(_found(GOOD))
    assert f.check == "C1" and f.status == "PASS", f.items


def test_c1_fails_mirror_presented_as_direct_and_mirror_growth():
    import silk_writer_claims as W
    bad = [{"v": 15.12, "unit": "مليون دولار", "year": 2025, "indicator": "imports",
            "basis": "direct", "source": "UN Comtrade"},
           {"v": 213, "unit": "%", "year": 2025, "from_year": 2019, "indicator": "imports_growth",
            "basis": "direct", "source": "UN Comtrade"},
           {"v": 20.9, "unit": "%", "year": 2024, "from_year": 2019, "indicator": "imports_cagr",
            "basis": "direct", "source": "UN Comtrade"}]
    f = W.check(_found(bad))
    assert f.status == "FAIL"
    whys = " ".join(i["why"] for i in f.items if i["status"] == "FAIL")
    assert "أُعلِن تصريحاً مباشراً" in whys          # 15.12 مليون 2025 مرآة
    assert "2019–2025 محسوبٌ على سنة مرآة" in whys    # 213% على طرف مرآة
    assert "13.7" in whys                             # 20.9% مقابل المحسوب


def test_c1_accepts_a_labelled_mirror_claim_and_flags_a_wrong_value():
    import silk_writer_claims as W
    ok = GOOD + [{"v": 15.12, "unit": "مليون دولار", "year": 2025, "indicator": "imports",
                  "basis": "mirror", "source": "UN Comtrade (مرآة)"}]
    assert W.check(_found(ok)).status == "PASS"
    wrong = [{"v": 12.0, "unit": "مليون دولار", "year": 2024, "indicator": "imports",
              "basis": "direct", "source": "UN Comtrade"}]
    assert W.check(_found(wrong)).status == "FAIL"


def test_c1_warns_on_missing_block_and_on_prose_numbers_not_claimed():
    import silk_writer_claims as W
    assert W.check(_found(None, status="missing")).status == "WARN"
    partial = W.check(_found(GOOD[:1]))                     # 89.9% في النصّ بلا ادعاء
    assert partial.status == "WARN" and "89.9" in json.dumps(partial.items, ensure_ascii=False)


def test_c1_skips_a_refined_report_and_a_report_without_claims_support():
    import silk_writer_claims as W
    b = _found(GOOD)
    b["deep_research"]["report"]["refined_at"] = "2026-10-22T00:00:00Z"
    assert W.check(b).status == "SKIP"
    assert W.check({"deep_research": {}}).status == "SKIP"


def test_writer_output_is_stripped_before_any_completeness_logic_and_kept_on_the_node():
    import silk_ai_judge as J
    full = "\n\n".join(f"## {i}. {t}\n\nنص القسم {i} مكتمل." for i, t in enumerate(
        J._REPORT_SECTIONS, 1)) + _fence(GOOD)
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), \
         mock.patch.object(J, "_call", return_value=full), \
         mock.patch.object(J, "review_report", return_value={"approved": True, "issues": [],
                                                              "blocking": [],
                                                              "review_status": "approved"}):
        node = J.write_reviewed_report({}, "تحليل", {"verdict": "WATCH"}, "قهوة", "البحرين",
                                       max_cycles=1)
    assert node["report"] and "```claims" not in node["report"] and "\"claims\"" not in node["report"]
    assert node["claims_status"] == "ok" and node["claims"][0]["v"] == 9.17


def test_writer_is_told_to_emit_the_claims_block():
    src = open(os.path.join(_ROOT, "silk_ai_judge.py"), encoding="utf-8").read()
    assert "```claims" in src and '\\"basis\\": direct' in src


def test_shadow_records_c1(tmp_path):
    import silk_study_checks_shadow as S
    with mock.patch.dict(os.environ, {"SILK_OPS_LOG_DB": str(tmp_path / "ops.db"),
                                      "SILK_STUDY_CHECKS": "shadow"}):
        out = S.run_and_record(_found(GOOD), analysis_id=1)
    assert out["statuses"]["C1"] == "PASS"


# ── المراجعة الذاتية (§58) — أقفالٌ كُتبت بعد الإصلاح ─────────────────────────────

def test_review_claims_follow_the_delivered_text_not_the_last_call():
    import silk_writer_claims as W
    W.reset()
    W.take(_BODY + _fence(GOOD))
    W.take("نص مراجعةٍ رُفضت.\n" + _fence([{"v": 1, "unit": "%", "indicator": "imports_growth"}]))
    got = W.for_text(_BODY)
    assert got["claims"][0]["v"] == 9.17


def test_review_fence_variants_are_stripped_and_values_normalised():
    import silk_writer_claims as W
    t, c, s = W.strip(_BODY + '\n```Claims {"claims": [{"v": "٩٫١٧", "unit": "ملايين دولار", '
                      '"year": 2024, "indicator": "imports", "basis": "direct"}]}\n```\n')
    assert "```" not in t and s == "ok" and c[0]["v"] == 9.17 and W.scaled(c[0]) == 9.17e6
    _t, c2, s2 = W.strip(_BODY + _fence([{"v": "x"}, GOOD[0]]))
    assert s2 == "ok_dropped:1" and len(c2) == 1


def test_review_pre_303_study_is_skipped_and_unverifiable_claims_warn():
    import silk_writer_claims as W
    b = _found(GOOD)
    del b["deep_research"]["report"]["claims_status"]
    assert W.check(b).status == "SKIP"
    odd = [{"v": 5, "unit": "مليون دولار", "year": 2017, "indicator": "imports", "basis": "direct"}]
    assert W.check(_found(odd, text="## 1. الخلاصة\n\nنص.\n")).status == "WARN"
    yoy = [{"v": 4.6, "unit": "%", "year": 2024, "from_year": 2023, "indicator": "imports_growth",
            "basis": "direct"}]
    assert W.check(_found(yoy, text="## 1. الخلاصة\n\nنص.\n")).status == "PASS"   # 8.77→9.17


def test_review_write_reviewed_report_keeps_its_signature_and_source():
    import inspect
    import silk_ai_judge as J
    assert "product_card" in inspect.signature(J.write_reviewed_report).parameters
    assert "for cycles in range(" in inspect.getsource(J.write_reviewed_report)
