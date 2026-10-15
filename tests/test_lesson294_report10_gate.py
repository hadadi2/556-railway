"""الدرس ٢٩٤ — حجبُ الدراسة ١٠ (قهوة محمّصة → البحرين، سجلّ Railway 2026-10-14).

القائدان: `adjacent_short_stutter` على «نقطة التعادل التشغيلي: نقطة التعادل
التشغيلي = …» (الصيغة التي يمليها موجّه الكاتب نفسه بعد عنوانٍ عريض)، و
`ledger_token_unbound` لرمزٍ كُتب بصيغةٍ لا يطابقها `TOKEN_RE` (مسافة/حرف كبير/
شرطة/عنصرٌ نائب عربي) فلم يُملأ ولم يُعَد للتنقيح.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import silk_fact_ledger as L                                  # noqa: E402
import silk_quality_gate as Q                                 # noqa: E402


def _ledger_with(key, value, **kw):
    kw.setdefault("source", "UN Comtrade")
    kw.setdefault("confidence", 0.9)
    return {"entries": {key: L._entry(key, value, **kw)},
            "order": [key], "gaps": []}


# ── ١) التسمية ثم معادلتُها ليست تلعثماً ───────────────────────────────────

def test_label_then_its_formula_is_not_a_stutter():
    line = ("- **نقطة التعادل التشغيلي:** نقطة التعادل التشغيلي = التكاليف "
            "الثابتة ÷ هامش المساهمة. المتاح: الهامش. الناقص: التكاليف الثابتة.")
    assert not Q._check_adjacent_short_stutter(line)
    assert not Q._check_adjacent_short_stutter(
        "**نقطة التعادل التشغيلي**: نقطة التعادل التشغيلي غير محسوبة.")


def test_real_adjacent_stutter_still_fires():
    for line in ("هذه الأرقام تحتاج تحققا تحتاج تحققا إضافيا قبل القرار.",
                 "لا يتوفر س لا يتوفر سعر تجزئة مرصود في السوق.",
                 "الخلاصة: لا يتوفر س لا يتوفر سعر تجزئة مرصود."):
        assert Q._check_adjacent_short_stutter(line), line


# ── ٢) الرمز المشوَّه يُملأ أو يُعلَن غيابُه — لا يصل `{{` عميلاً ─────────────

def test_loosely_written_tokens_bind():
    led = _ledger_with("hhi", 3800.0)
    for tok in ("{{ status: hhi }}", "{{Status:HHI}}", "{{status:hhi }}"):
        out, info = L.bind(f"حالة التركّز: {tok}.", led)
        assert out == "حالة التركّز: متاح من مصدر موثّق.", (tok, out)
        assert info["used"] == ["hhi"]


def test_unparseable_token_never_reaches_the_text():
    led = _ledger_with("hhi", 3800.0)
    for tok in ("{{status:المفتاح}}", "{{hhi:value}}", "{{imports_2024}}"):
        out, info = L.bind(f"حالة التركّز {tok} هنا.", led)
        assert "{{" not in out and "}}" not in out, (tok, out)
        assert info["unknown"], tok
    assert not L.check({"ledger": led}, L.bind("قيمة {{status:المفتاح}}.",
                                                led)[0])


def test_malformed_token_is_sent_back_to_the_writer():
    led = _ledger_with("hhi", 3800.0)
    issues = L.draft_issues("حالة التركّز {{status:المفتاح}} هنا.", led)
    assert any("{{status:المفتاح}}" in i for i in issues), issues
    assert not L.draft_issues("حالة التركّز {{ Status: HHI }} هنا.", led)
