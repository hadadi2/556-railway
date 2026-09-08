"""عدّاد النثر العربي — قياس حتمي لقواعد النثر الثماني (هدف الدراسة، البند ٥).

> **الغرض.** «المعايرة هي التسليم لا الحقن»: عقد الكتابة يصل الموجّه منذ
> Part B، وهذا العدّاد يقيس هل يُطاع فعلاً — على أي نص تقرير، بلا نموذج،
> بلا شبكة، وبنتيجة قابلة للمقارنة قبل/بعد. **قياسٌ لا حكم**: مخرجاته
> تدخل قناة `language_quality` التحذيرية (الدرس 135) وتقرير أداة
> `tools/prose_report.py` — لا حجب.
>
> **المناطق العمياء المعلنة (الدرس 172):** كشف الافتتاح الاسمي يعتمد
> «ال» التعريف وقائمة أفعال الحشو — الاسم النكرة في أول الجملة لا يُرى؛
> كشف المجهول يعتمد بناء «يتم/تتم + مصدر» والصيغ المشكولة وقائمة صيغ
> معروفة — مجهولٌ غير مشكول خارج القائمة لا يُرى؛ سلاسل الإضافة تُقرَّب
> بتتابع ≥3 كلمات معرَّفة بـ«ال»؛ وقاعدة «المعلومة الجديدة آخر الجملة»
> غير قابلة للقياس الحتمي أصلاً — تبقى على عاتق الموجّه وقراءة المالك.
>
> Deterministic Arabic prose meter for the eight rules — measurement, not
> judgment; stdlib only, zero network.
"""
from __future__ import annotations

import re

# روابط ثقيلة (القاعدة ٥) — نفس قائمة الحظر في Part B وموجّه الكاتب
# (وُحِّدت في نفس الموجة — الدرس 156: لا يعدّ العدّادُ ما يوصي به الموجّه).
HEAVY_CONNECTORS = ("بوصفه", "بوصفها", "من حيث", "في ضوء", "وعليه",
                    "علاوة على", "فضلاً عن")
# «إذ» وحدها قصيرة — تُلتقط ككلمة مستقلة لا كجزء من كلمة (إذا/إذن).
_ITH_RE = re.compile(r"(?<![\w؀-ۿ])إذ(?![\w؀-ۿ])")

# مصطلحات مترجمة حرفياً (القاعدة ٤) — قائمة الهدف؛ تُوسَّع بسؤال الدرس 176.
LITERAL_TERMS = ("نافذة فرصة", "نافذة الفرصة", "من الصفر", "بطاقة تكلفة",
                 "رتبة حجم")

# أفعال الحشو الافتتاحية (القاعدة ١) — فعلٌ شكلاً، اسميةٌ أثراً.
_FILLER_OPENERS = ("يمثل", "يمثّل", "تمثل", "تمثّل", "يشكل", "يشكّل",
                   "تشكل", "تشكّل", "يعتبر", "تعتبر", "يعد", "يُعد",
                   "تعد", "تُعد")

# صيغ مجهول معروفة في تقارير هذا النظام (القاعدة ٣) — مشكولة وغير مشكولة
# حيث لا لبس. «يُوصى» مستثناة: صوت التقرير المعتمد في السجل المهني.
_PASSIVE_FORMS = ("يُرصَد", "يُرصد", "تُرصَد", "تُرصد", "لم يُرصد",
                  "لم يرصد", "يُلاحَظ", "تُلاحَظ", "يُقدَّر", "تُقدَّر",
                  "يُتوقَّع", "تُتوقَّع", "لوحِظ", "رُصِد")
_YUTIM_RE = re.compile(r"\b(?:يتم|تتم|يتمّ|تتمّ)\s+\S+")

# حدود الجملة العربية.
_SENT_SPLIT_RE = re.compile(r"[.!؟?؛;\n]+")
_AR_WORD_RE = re.compile(r"[؀-ۿ]{2,}")

TARGET_MIN, TARGET_MAX = 12, 25


def _sentences(text: str) -> list[str]:
    out = []
    for raw in _SENT_SPLIT_RE.split(text or ""):
        s = raw.strip().strip("#*•-—:").strip()
        # سطر جدول/عنوان/رقم عارٍ ليس جملة نثر.
        if s and len(_AR_WORD_RE.findall(s)) >= 3 and "|" not in s:
            out.append(s)
    return out


def _words(sentence: str) -> list[str]:
    return [w for w in re.split(r"\s+", sentence) if w.strip()]


def analyze(text: str) -> dict:
    """قِس النص وأعد المقاييس مع الشواهد — حتمي، نفس النص نفس النتيجة."""
    sents = _sentences(text)
    n = len(sents)
    lengths = [len(_words(s)) for s in sents]
    in_target = sum(1 for L in lengths if TARGET_MIN <= L <= TARGET_MAX)

    nominal: list[str] = []
    for s in sents:
        first = _words(s)[0]
        bare = first.lstrip("وفب")          # حرف عطف/جر ملتصق
        if bare.startswith("ال") or first in _FILLER_OPENERS \
                or bare in _FILLER_OPENERS:
            nominal.append(s[:80])

    passives: list[str] = []
    for s in sents:
        if any(p in s for p in _PASSIVE_FORMS) or _YUTIM_RE.search(s):
            passives.append(s[:80])

    heavy: dict[str, int] = {}
    for c in HEAVY_CONNECTORS:
        k = text.count(c)
        if k:
            heavy[c] = k
    k = len(_ITH_RE.findall(text or ""))
    if k:
        heavy["إذ"] = k

    literals = {t: text.count(t) for t in LITERAL_TERMS if t in (text or "")}

    idafa: list[str] = []
    for s in sents:
        run = 0
        for w in _words(s):
            if w.startswith("ال") and len(w) > 3:
                run += 1
                if run >= 4:
                    idafa.append(s[:80])
                    break
            else:
                run = 0

    return {
        "sentences": n,
        "avg_words": round(sum(lengths) / n, 1) if n else None,
        "max_words": max(lengths) if lengths else None,
        "pct_in_target": round(in_target / n * 100) if n else None,
        "nominal_openers": nominal,
        "nominal_ratio": round(len(nominal) / n, 2) if n else None,
        "passives": passives,
        "heavy_connectors": heavy,
        "literal_terms": literals,
        "definite_chains": idafa,
    }


def report_lines(m: dict) -> list[str]:
    """أسطر تقرير مقروءة من المقاييس — لأداة المعايرة وسجل CI."""
    out = [f"جُمل النثر: {m['sentences']} · متوسط الطول: {m['avg_words']}"
           f" · الأطول: {m['max_words']}"
           f" · داخل الهدف 12–25: {m['pct_in_target']}%"]
    out.append(f"افتتاح اسمي/حشو: {len(m['nominal_openers'])}"
               f" ({m['nominal_ratio']})")
    for s in m["nominal_openers"][:3]:
        out.append(f"   ← {s}")
    out.append(f"صيغ مجهول/«يتم»: {len(m['passives'])}")
    for s in m["passives"][:3]:
        out.append(f"   ← {s}")
    if m["heavy_connectors"]:
        out.append("روابط ثقيلة: " + "، ".join(
            f"{c}×{k}" for c, k in m["heavy_connectors"].items()))
    if m["literal_terms"]:
        out.append("مصطلحات مترجمة حرفياً: " + "، ".join(m["literal_terms"]))
    if m["definite_chains"]:
        out.append(f"سلاسل تعريف ≥4: {len(m['definite_chains'])}")
    return out
