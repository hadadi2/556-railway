"""المجموعة الذهبية — golden set (المرحلة 0.5 من توجيه المنصّة 2026-08-19).

> **الغرض.** خمسة تقارير مرجعية بمدخلاتها ومخرجاتها، تُعاد توليدها هرمتياً
> (من المدوّنات القانونية المجمَّدة — صفر شبكة، صفر كلفة) بعد كل مرحلة/موجة،
> وتُقارَن آلياً على خمسة مؤشرات:
>   1. الحكم النهائي (verdict)
>   2. نسبة الثقة (confidence)
>   3. الأرقام المفتاحية (key figures)
>   4. عدد الأقسام (section count)
>   5. أرقام في التقرير غير موجودة في المصادر (fabrication bell —
>      جرس إنذار برومبت الكاتب)
> أي تغيّر في الحكم يوقف المرحلة حتى يُفسَّر (قرار مالك، تعديل ١).
>
> **Purpose.** Five reference reports regenerated hermetically from the frozen
> canonical blobs and compared on five indicators after every phase/wave. Any
> verdict change blocks the phase until explained (owner amendment #1).

**فجوة معلنة:** تقرير الحليب–الأردن الحيّ غير مؤرشف داخل الريبو (مدخلاته في
قاعدة الإنتاج فقط)، فيقوم مقامه هنا أقرب مرجع ألبان مجمَّد
(`canonical_nadec_yemen_dairy`). اختبار القبول الحيّ للحليب–الأردن يبقى بنداً
مستقلاً في المرحلة 0 بموافقة المالك على توقيته.

الاستعمال · usage:
    python3 tools/golden_set.py archive    # يكتب/يحدّث خط الأساس evals/golden_set/
    python3 tools/golden_set.py compare    # يقارن التوليد الحالي بخط الأساس (exit 1 عند تغيّر حكم)

المكتبات: stdlib + وحدات الريبو فقط — هرمتي بالكامل، لا شبكة.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASELINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "evals", "golden_set")

# الحالات الخمس — متنوّعة المنتج/السوق/شكل الحادثة (كلها مدوّنات قانونية مجمَّدة).
GOLDEN_CASES = {
    "netherlands_dates": ("tools.canonical_netherlands", "netherlands_research_blob"),
    "kuwait_peanut_butter": ("tools.canonical_kuwait_peanut_butter", "kuwait_research_blob"),
    "nadec_yemen_dairy": ("tools.canonical_nadec_yemen_dairy", "nadec_yemen_research_blob"),
    "germany_dates": ("tools.canonical_germany_dates", "germany_dates_research_blob"),
    "japan_honey": ("tools.canonical_japan_honey", "japan_honey_research_blob"),
}

# أرقام أصغر من هذا تُهمَل في مؤشر ٥ (أرقام أقسام/ترقيم/نسب صغيرة شائعة).
_MIN_FABRICATION_MAGNITUDE = 100.0
# سنوات قريبة تُهمَل أيضاً (ترقيم زمني لا ادّعاء كمّي).
_YEAR_RANGE = (1990, 2040)

_NUM_RE = re.compile(r"\d[\d,\.]*")


def _blob(key: str) -> dict:
    mod_name, fn_name = GOLDEN_CASES[key]
    mod = __import__(mod_name, fromlist=[fn_name])
    return getattr(mod, fn_name)()


def _numbers_in(text: str) -> set:
    """كل الأرقام في نصّ، مطبَّعة (نزع الفواصل، float مقرَّب لخانة واحدة)."""
    out = set()
    for tok in _NUM_RE.findall(text or ""):
        tok = tok.strip(".,").replace(",", "")
        if not tok:
            continue
        try:
            out.add(round(float(tok), 1))
        except ValueError:
            continue
    return out


def _walk_numbers(obj, acc: set):
    """كل قيمة رقمية (أو رقم داخل نص) في بنية متداخلة."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        acc.add(round(float(obj), 1))
    elif isinstance(obj, str):
        acc.update(_numbers_in(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_numbers(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_numbers(v, acc)


def _report_text(blob: dict, view: dict) -> str:
    dr = view.get("deep_research") or {}
    rep = dr.get("report")
    if isinstance(rep, dict):
        rep = rep.get("text")
    if not rep:
        rep = (blob.get("deep_research") or {}).get("report") or ""
    return rep if isinstance(rep, str) else ""


def _key_figures(view: dict) -> dict:
    """الأرقام المفتاحية الحتمية: حكم/ثقة/نقاط الأسواق/مكوّنات القرار."""
    figs = {}
    dec = view.get("decision") or {}
    if isinstance(dec, dict):
        for k in ("score", "verdict", "confidence"):
            if k in dec:
                figs[f"decision.{k}"] = dec.get(k)
    for i, m in enumerate((view.get("markets") or [])[:3]):
        if isinstance(m, dict) and m.get("total_score") is not None:
            figs[f"market{i}.total_score"] = m.get("total_score")
    dr = view.get("deep_research") or {}
    v = dr.get("verdict") or {}
    if isinstance(v, dict):
        figs["dr.verdict"] = v.get("verdict")
        figs["dr.confidence"] = v.get("confidence")
    return figs


def snapshot(key: str) -> dict:
    """بصمة الحالة على المؤشرات الخمسة — حتمية بالكامل."""
    import silk_render as R
    blob = _blob(key)
    view = R.build_view(blob)
    dr = view.get("deep_research") or {}
    verdict = (dr.get("verdict") or {}).get("verdict")
    confidence = (dr.get("verdict") or {}).get("confidence")
    report = _report_text(blob, view)
    sections = len(re.findall(r"^## ", report, flags=re.M))

    # مؤشر ٥: أرقام التقرير غير المسنودة — المصادر = كل رقم في المدوّنة عدا نص التقرير.
    src_blob = dict(blob)
    src_dr = dict(src_blob.get("deep_research") or {})
    src_dr.pop("report", None)
    src_blob["deep_research"] = src_dr
    source_nums: set = set()
    _walk_numbers(src_blob, source_nums)
    unsupported = sorted(
        n for n in _numbers_in(report)
        if n not in source_nums
        and abs(n) >= _MIN_FABRICATION_MAGNITUDE
        and not (_YEAR_RANGE[0] <= n <= _YEAR_RANGE[1] and float(n).is_integer())
    )

    return {
        "case": key,
        "verdict": verdict,
        "confidence": confidence,
        "key_figures": _key_figures(view),
        "section_count": sections,
        "unsupported_report_numbers": unsupported,
        # المؤشر السادس (بلاغ المالك 2026-08-19): حقل «بنود تحتاج تحققاً»
        # انقلب إلى «لا شيء» والمجموعة الذهبية خضراء — لأن الحقل كان خارج
        # المؤشرات الخمسة كلياً. صار مؤشراً أولَ درجة، وتناقضُه حاجب.
        "verification_items": _verification_items(view),
    }


def _verification_items(view: dict) -> dict:
    """عدد البنود التي تحتاج تحققاً + سطر الكفاية المعروض — المؤشر الذي
    كان أعمى: انقلابُ العدد من N إلى صفر، أو ادّعاءُ «لا شيء» مع وجود
    بنود، كلاهما يُلتقَط الآن."""
    dr = view.get("deep_research") or {}
    n = len(dr.get("gap_register") or dr.get("limits")
            or view.get("limits") or [])
    dec = view.get("decision") or {}
    # مسار الجورية الاحتياطي لا يحمل `sufficiency` بل يضع السطر في `why` —
    # قراءتهما معاً تجعل نصف المؤشر قابلاً للإطلاق على توليدٍ حقيقي لا على
    # عبثٍ يدويّ وحده (مراجعة ذاتية §58).
    suff = str(dec.get("sufficiency") or "")
    line = suff or str(dec.get("why") or "")
    return {"count": n, "claims_none": bool(line) and "لا شيء" in line,
            "sufficiency_present": bool(suff)}


def compare_case(key: str, baseline: dict, current: dict) -> list:
    """يعيد قائمة فروقات؛ فرق الحكم يوسَم BLOCKING."""
    diffs = []
    if baseline.get("verdict") != current.get("verdict"):
        diffs.append(f"BLOCKING: verdict changed {baseline.get('verdict')!r} -> {current.get('verdict')!r}")
    if baseline.get("confidence") != current.get("confidence"):
        diffs.append(f"confidence changed {baseline.get('confidence')} -> {current.get('confidence')}")
    if baseline.get("section_count") != current.get("section_count"):
        diffs.append(f"section_count changed {baseline.get('section_count')} -> {current.get('section_count')}")
    b_f, c_f = baseline.get("key_figures") or {}, current.get("key_figures") or {}
    for k in sorted(set(b_f) | set(c_f)):
        if b_f.get(k) != c_f.get(k):
            diffs.append(f"key_figure {k}: {b_f.get(k)} -> {c_f.get(k)}")
    # المؤشر السادس: التناقض نفسه حاجب (ادّعاء «لا شيء» مع وجود بنود)،
    # وكذلك اختفاءُ بنودٍ كانت موجودة (انحدارُ قناة الفجوات).
    b_v = baseline.get("verification_items") or {}
    c_v = current.get("verification_items") or {}
    if c_v.get("claims_none") and (c_v.get("count") or 0) > 0:
        diffs.append(
            f"BLOCKING: sufficiency claims «لا شيء» while {c_v['count']} "
            "verification items exist")
    if (b_v.get("count") or 0) > 0 and (c_v.get("count") or 0) == 0:
        diffs.append(
            f"BLOCKING: verification items dropped {b_v.get('count')} -> 0")
    elif b_v.get("count") != c_v.get("count"):
        diffs.append(
            f"verification item count {b_v.get('count')} -> {c_v.get('count')}")
    b_u = baseline.get("unsupported_report_numbers") or []
    c_u = current.get("unsupported_report_numbers") or []
    new_unsupported = [n for n in c_u if n not in b_u]
    if new_unsupported:
        diffs.append(f"BLOCKING: new unsupported numbers in report: {new_unsupported}")
    return diffs


def archive() -> None:
    os.makedirs(BASELINE_DIR, exist_ok=True)
    for key in GOLDEN_CASES:
        snap = snapshot(key)
        path = os.path.join(BASELINE_DIR, f"{key}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2, sort_keys=True)
        print(f"archived {key} -> {path}")


def compare() -> int:
    """0 = مطابق أو فروق غير حاجبة؛ 1 = فرق حاجب (حكم/أرقام غير مسنودة جديدة)."""
    blocking = False
    for key in GOLDEN_CASES:
        path = os.path.join(BASELINE_DIR, f"{key}.json")
        if not os.path.exists(path):
            print(f"{key}: NO BASELINE — run `python3 tools/golden_set.py archive` first")
            blocking = True
            continue
        with open(path, encoding="utf-8") as f:
            baseline = json.load(f)
        diffs = compare_case(key, baseline, snapshot(key))
        if not diffs:
            print(f"{key}: OK")
        else:
            for d in diffs:
                print(f"{key}: {d}")
                if d.startswith("BLOCKING"):
                    blocking = True
    return 1 if blocking else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if cmd == "archive":
        archive()
    elif cmd == "compare":
        sys.exit(compare())
    else:
        print(__doc__)
        sys.exit(2)
