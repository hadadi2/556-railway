"""خطُّ أساس جودة التقرير — مولّدٌ ومقارِنٌ هرمتيّ (موجة عيوب التقرير العشرة).

الغرض: إثباتُ «الأرقام مقدّسة» **بسكربت لا بالعين**. الطبقةُ اللغوية (الأصناف
١–٥) لا يجوز أن تُغيّر أيّ قيمةٍ مخزّنة ولا درجةً ولا حكماً ولا ثقة؛ فتُلتقَط
لقطةٌ قبل العمل وتُقارَن بعد كلّ كوميت. والطبقةُ المنطقية (٦–١٠) خلف رايات،
فيُقارَن الفرقُ راية-مفعّلةً ضدّ مطفأة ويُشرَح كلُّ اختلاف.

المصدر: المدوّناتُ القانونية العشر المجمّدة (`tools/canonical_*.py`) عبر سجلّها
الواحد `tools.gen_verdict_baseline.CANONICAL_BLOBS` — لا قائمةَ ثانية تتباعد.

صفرُ شبكة، صفرُ مفتاح، صفرُ كلفة: `build_view` ثم `render_markdown` ثم
`run_quality_gate`، كلُّها منطقُ عرضٍ وقراءةٍ محض.

الاستعمال:

    python3 tools/report_quality_baseline.py archive   # يكتب tests/baseline/
    python3 tools/report_quality_baseline.py compare   # خرجٌ 1 عند أيّ انحراف

تاريخُ التشغيل (`view["date"]`) يُطبَّع إلى `<RUN_DATE>` قبل الكتابة والمقارنة —
هو ساعةُ خطِّ التجميع لا معطىً، وتركُه يجعل كلَّ لقطةٍ مختلفةً كلَّ يوم (نفس
علاج `tests/test_committed_samples_current.py._normalise`).
"""
from __future__ import annotations

import datetime
import difflib
import importlib
import json
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
for _p in (_REPO_ROOT, _TOOLS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

BASELINE_DIR = os.path.join(_REPO_ROOT, "tests", "baseline")
GATE_INDEX = "gate_index.json"
RUN_DATE_TOKEN = "<RUN_DATE>"


def case_keys() -> list:
    """مفاتيحُ المدوّنات — من سجلّها الواحد لا من قائمةٍ منسوخة."""
    from tools import gen_verdict_baseline as B
    return sorted(B.CANONICAL_BLOBS)


def _blob(key: str) -> dict:
    from tools import gen_verdict_baseline as B
    mod, fn = B.CANONICAL_BLOBS[key]
    return getattr(importlib.import_module(mod), fn)()


def _normalise(text: str) -> str:
    """تاريخُ التشغيل → رمزٌ ثابت. لا يمسّ أيّ تاريخِ رصدٍ أو سنةِ مصدر."""
    return text.replace(datetime.date.today().isoformat(), RUN_DATE_TOKEN)


def _sections_recognized(view: dict) -> str:
    """«N/11» — الأقسامُ القانونيةُ التي يقرؤها المحدِّدُ في نصّ التقرير."""
    import re
    import silk_ai_judge as J
    text = (((view.get("deep_research") or {}).get("report") or {})
            .get("text") or "")
    seen = set(t for _n, t in
               re.findall(r"^##\s+(\d+)\.\s*(.+?)\s*$", text, re.M))
    canon = J.report_sections()
    return f"{len([s for s in canon if s in seen])}/{len(canon)}"


def snapshot(key: str) -> dict:
    """لقطةُ حالةٍ واحدة: عرضٌ مهيكل + نصٌّ مُصدَّر + بصمةُ البوابة."""
    import silk_quality_gate as G
    import silk_render
    import silk_reports

    view = silk_render.build_view(_blob(key))
    gate = G.run_quality_gate(view)
    try:
        md = silk_reports.render_markdown(view)
    except Exception as exc:                      # noqa: BLE001
        md = f"<<RENDER_FAILED {type(exc).__name__}: {exc}>>"
    return {
        "view_json": _normalise(json.dumps(
            view, ensure_ascii=False, indent=1, sort_keys=True, default=str)),
        "report_md": _normalise(md),
        # الدرس ٢٦١: عددُ الأقسام **المتعرَّف عليها فعلاً** في نصّ العرض —
        # مقياسٌ صريحٌ على كلّ مدوّنة، فانحدارُ محدِّدِ العنوان (الذي حجب
        # تقريراً حيّاً كاملاً) يُلتقَط هنا قبل الدمج لا على شاشةِ مصنع.
        "gate": {
            # الدرس ٢٦١: عددُ الأقسام **المتعرَّف عليها فعلاً** — داخل بصمةِ
            # البوابة كي **يُقارَن** (مراجعة §58 #4: كان يُحسَب ولا يُقارَن،
            # فمقياسٌ لا يُقارَن حارسٌ لا يُطلِق — الدرس ٩٨).
            "sections_recognized": _sections_recognized(view),
            "verdict": gate["verdict"],
            # مُرتَّبةٌ لأن ترتيبَ الاستدعاء داخل البوابة ليس عقداً
            "findings": sorted(f["check"] for f in gate["findings"]),
            "language_quality": sorted(
                f["check"] for f in gate.get("language_quality") or []),
            "skipped_checks": sorted(
                f["check"] for f in gate.get("skipped_checks") or []),
        },
    }


def archive() -> None:
    os.makedirs(BASELINE_DIR, exist_ok=True)
    index = {}
    for key in case_keys():
        snap = snapshot(key)
        _write(f"{key}.view.json", snap["view_json"])
        _write(f"{key}.report.md", snap["report_md"])
        index[key] = snap["gate"]
        print(f"{key:26s} {snap['gate']['verdict']:20s} "
              f"n={len(snap['gate']['findings']):2d} "
              f"md={len(snap['report_md'])}")
    _write(GATE_INDEX,
           json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True))
    print(f"\n{len(index)} حالة → {BASELINE_DIR}")


def _write(name: str, body: str) -> None:
    with open(os.path.join(BASELINE_DIR, name), "w", encoding="utf-8") as fh:
        fh.write(body if body.endswith("\n") else body + "\n")


def _read(name: str) -> "str | None":
    path = os.path.join(BASELINE_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _diff(name: str, committed: str, fresh: str, limit: int = 12) -> list:
    lines = list(difflib.unified_diff(
        committed.splitlines(), fresh.splitlines(),
        fromfile=f"{name} (المُلتزَم)", tofile=f"{name} (الحالي)", lineterm="",
        n=1))
    return lines[:limit + 3]


def compare_case(key: str) -> list:
    """فروقُ حالةٍ واحدة — قائمةٌ فارغة = مطابقةٌ حرفية."""
    snap = snapshot(key)
    out: list = []
    for name, fresh in ((f"{key}.view.json", snap["view_json"]),
                        (f"{key}.report.md", snap["report_md"])):
        committed = _read(name)
        if committed is None:
            out.append(f"{name}: لا لقطةَ مُلتزَمة — شغّل archive أولاً")
            continue
        if committed.rstrip("\n") != fresh.rstrip("\n"):
            out.append(f"{name}: انحراف")
            out += _diff(name, committed.rstrip("\n"), fresh.rstrip("\n"))
    index = json.loads(_read(GATE_INDEX) or "{}")
    if index.get(key) != snap["gate"]:
        out.append(f"{key}: بصمةُ البوابة تغيّرت — "
                   f"المُلتزَم {index.get(key)} / الحالي {snap['gate']}")
    return out


def compare() -> int:
    bad = 0
    for key in case_keys():
        diffs = compare_case(key)
        if diffs:
            bad += 1
            print(f"✗ {key}")
            for line in diffs:
                print("   " + line)
        else:
            print(f"✓ {key}")
    if bad:
        print(f"\n{bad} حالة انحرفت — انحدارٌ معلَن يوقف العمل. لا يُجدَّد خطُّ "
              "الأساس لتمرير موجة؛ يُشرَح كلُّ فرقٍ في "
              "docs/report-quality/CHANGELOG.md أوّلاً.")
        return 1
    print(f"\n{len(case_keys())} حالة مطابقة حرفياً — القيم لم تتغيّر.")
    return 0


def main(argv: list) -> int:
    cmd = (argv[1] if len(argv) > 1 else "compare").strip().lower()
    if cmd == "archive":
        archive()
        return 0
    if cmd == "compare":
        return compare()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
