#!/usr/bin/env python3
"""استرداد تقريرٍ من جزءٍ محفوظ + تحقّق التصدير — على نشرٍ حيّ بمفتاحٍ حقيقيّ.

بلاغ تحليل 20: التشغيلة دفعت البعثات + المحلل + مسوّدةَ كاتبٍ ٨/١١ قسماً
(`writer_partial`) ثم فشلت. المسارُ الرخيص لاستردادها هو نقطةُ إعادة التوليد:
`POST /analyses/{id}/report` يكتشف غيابَ تقريرٍ كامل + وجودَ `writer_partial`
(status=partial) فيبذر منه ويُكمِل الأقسامَ الباقية بنداءِ إكمالٍ واحد — قروشٌ لا
دولارات (المنطقُ مقفولٌ في `tests/test_analysis20_resume_from_partial.py`).

هذه الأداةُ تُشغَّل على النشر الحيّ (ليست هرمتية): تُنفّذ الاسترداد ثم تسحب
التصديرات الثلاثة وتتحقّق أنها تُنتِج مخرَجاً — تقريرُ رُتبةٍ حيّةٍ صادق، لا
ادعاء. لا مفاتيح في الشيفرة: تُقرأ من البيئة (المفاتيح تبقى في بيئة النشر —
عقد `CLAUDE.md`)، فتبقى نقرةُ المالك أمراً واحداً زُهيدَ التكلفة.

الاستعمال (على جهازٍ يصل الخادمَ الحيّ):
    SILK_BASE_URL=https://<الخادم> SILK_API_KEY=<المفتاح> \
        python3 tools/recover_and_verify.py [--id 20] [--style academic]

المخرَج: حالةُ الاسترداد (مكتمل/عدد الأقسام/الغائب)، وبايتاتُ كلّ تصدير، ورمزُ
حالته (٢٠٠/٥٠٣...). التكلفة الفعلية تُقرأ من `data_economics` في الاستجابة إن
حملتها الاستجابة، وإلا من `GET /health`/سجلّ المشغّل على الخادم.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

_SECTION_RE = re.compile(r"^##\s+\d+\.", re.M)


def _req(method: str, url: str, key: str, timeout: float = 900.0,
         owner_key: str | None = None):
    """نداءُ HTTP واحد — يعيد (رمز الحالة, البايتات, رأس المحتوى)."""
    req = urllib.request.Request(url, method=method)
    if key:
        req.add_header("X-API-Key", key)
    if owner_key:
        req.add_header("X-Owner-Key", owner_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:  # ٤٠١/٤٠٤/٥٠٣... جسمٌ صالحٌ للقراءة
        return e.code, e.read(), e.headers.get("Content-Type", "")


def _blocked_checks(body: bytes) -> list[str]:
    """أسماءُ فحوص بوابة الجودة الحاجبة من جسم 409 (quality_gate_fail)، إن وُجدت."""
    try:
        d = json.loads(body).get("detail") or {}
        if d.get("error") == "quality_gate_fail":
            return list(d.get("blocked_checks") or [])
    except Exception:  # noqa: BLE001 — جسمٌ غيرُ متوقَّع = لا فحوص معروفة
        pass
    return []


def _cost_line(analysis: dict) -> str:
    econ = (analysis or {}).get("data_economics") or {}
    cost = econ.get("cost_usd")
    if cost is None:
        cost = econ.get("estimated_cost_usd")
    if cost is None:
        return ("التكلفة: غير مذكورة في الاستجابة — اقرأها من GET /health أو "
                "سجلّ المشغّل على الخادم (stage_transition).")
    unpriced = econ.get("cost_unpriced_models") or []
    tail = f" (نماذج بلا سعر: {'، '.join(unpriced)})" if unpriced else ""
    return f"التكلفة (من data_economics): ${cost}{tail}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, default=20, help="رقم التحليل (افتراضي 20)")
    ap.add_argument("--style", default=None, help="أسلوب اختياري (مثل academic)")
    ap.add_argument("--fresh", action="store_true",
                    help="تجاوُز البذرة (?seed=0): مسوّدةٌ كاملةٌ من الصفر بدل "
                         "الإكمال من الجزء — أوثقُ متى تعثّر مسارُ البذرة، وأغلى قليلاً")
    ap.add_argument("--override", action="store_true",
                    help="عند حجب بوابة الجودة (409): أعِد التصدير بتجاوز المالك "
                         "(?override=1 + X-Owner-Key من SILK_OWNER_KEY) فتُسلَّم "
                         "النسخة موسومةً بملاحظات البوابة بدل حجبها (LESSONS 46/53).")
    ap.add_argument("--base", default=os.environ.get("SILK_BASE_URL"))
    ap.add_argument("--key", default=os.environ.get("SILK_API_KEY"))
    ap.add_argument("--owner-key", default=os.environ.get("SILK_OWNER_KEY"),
                    help="مفتاح المالك المنفصل لتجاوز البوابة (افتراضي من البيئة)")
    args = ap.parse_args()

    if not args.base:
        print("خطأ: SILK_BASE_URL غير مضبوط (عنوان الخادم الحيّ).", file=sys.stderr)
        return 2
    base = args.base.rstrip("/")
    aid = args.id
    _params = ([f"style={args.style}"] if args.style else []) \
        + (["seed=0"] if args.fresh else [])
    qs = ("?" + "&".join(_params)) if _params else ""

    print(f"→ استرداد تحليل {aid}: POST {base}/analyses/{aid}/report{qs}")
    status, body, _ = _req("POST", f"{base}/analyses/{aid}/report{qs}", args.key)
    if status != 200:
        print(f"✗ الاسترداد فشل: HTTP {status}\n{body[:800].decode(errors='replace')}")
        return 1
    try:
        analysis = json.loads(body)
    except Exception as e:  # noqa: BLE001
        print(f"✗ استجابةٌ ليست JSON: {e}\n{body[:400].decode(errors='replace')}")
        return 1

    if analysis.get("regenerated") is False:
        print(f"⚠ لم يُعَد التوليد: {analysis.get('note') or ''} "
              f"{analysis.get('failure_reason') or ''}")
        return 1

    rep = ((analysis.get("deep_research") or {}).get("report") or {})
    text = rep.get("report") or ""
    n_sections = len(_SECTION_RE.findall(text))
    incomplete = bool(rep.get("incomplete"))
    missing = rep.get("missing_sections") or []
    print(f"  تقرير: {len(text)} حرفاً · {n_sections}/11 قسماً · "
          f"{'ناقص' if incomplete else 'مكتمل'}"
          + (f" · غائب: {'، '.join(missing)}" if missing else ""))
    print("  " + _cost_line(analysis))

    print("→ تحقّق التصدير:")
    exports = ("report.md", "report.docx", "report.pdf")
    ok_any = False
    gate_blocked: list[str] = []
    for name in exports:
        st, data, ctype = _req("GET", f"{base}/analyses/{aid}/{name}", args.key)
        # بوابةُ الجودة تحجب (409): إن أُذِن التجاوز ووُجد مفتاحُ المالك، أعِد
        # التصدير موسوماً بدل حجبه — تقريرٌ مدفوعٌ يُسلَّم بملاحظاته أصدقُ من صفر
        # (LESSONS 46/53؛ نفسُ فلسفة #230 على طبقة التصدير).
        if st == 409:
            checks = _blocked_checks(data)
            if checks and not gate_blocked:
                gate_blocked = checks
            if args.override and args.owner_key:
                sep = "&" if "?" in name else "?"
                st, data, ctype = _req(
                    "GET", f"{base}/analyses/{aid}/{name}{sep}override=1",
                    args.key, owner_key=args.owner_key)
                if st == 200 and data:
                    ok_any = True
                    print(f"  ✓ {name}: {len(data)} بايت ({ctype}) "
                          f"[تجاوزُ مالكٍ — ملاحظات البوابة مرفقة]")
                    continue
        if st == 200 and data:
            ok_any = True
            print(f"  ✓ {name}: {len(data)} بايت ({ctype})")
        else:
            snippet = data[:200].decode(errors="replace") if data else ""
            print(f"  ✗ {name}: HTTP {st} {snippet}")

    if gate_blocked:
        print("\n⚠ بوابةُ الجودة حجبت تصديرَ العميل — الفحوصُ الحاجبة: "
              + "، ".join(dict.fromkeys(gate_blocked)))
        print("  • `trends_hollow_completion` مصدرُه ملخّصُ بعثة الطلب "
              "المخزَّنة (بيانات الدراسة الأصلية) — لا يُصلحه إعادةُ التوليد؛ "
              "يحتاج إعادةَ تشغيل تلك البعثة (تكلفة) أو تسليماً موسوماً.")
        print("  • فحوصُ نصّ التقرير (البنية/تكرار رقم/تعارض حكم) قد يُصلحها "
              "توليدٌ نظيفٌ من الصفر: أعِد التشغيل بـ--fresh (?seed=0، 24k).")
        if not args.override:
            print("  • لتسليم النسخة الآن موسومةً بالملاحظات: --override "
                  "مع SILK_OWNER_KEY في البيئة (سلطةُ المالك المنفصلة).")

    complete = (n_sections >= 11 and not incomplete)
    print("\nالخلاصة: "
          + ("تقريرٌ مكتملٌ مسترَدٌّ وقابلٌ للتصدير."
             if complete and ok_any and not gate_blocked else
             "تقريرٌ مسترَدٌّ مع تحفّظات — راجع الأعلى (لا ادعاءَ اكتمال)."
             if ok_any else
             "استردادٌ جزئيٌّ/محجوبٌ — راجع الأعلى (لا ادعاءَ اكتمال)."))
    return 0 if (complete and ok_any and not gate_blocked) else 1


if __name__ == "__main__":
    raise SystemExit(main())
