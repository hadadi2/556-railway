"""قواعد العربية لمحرك قوالب الدراسة — Arabic rules for the study template engine.

> P0-T §ج (`docs/plans/STUDY_MODE_FIX_PLAN.md`): حروف الجر مع «ال»، مولّد العدد
> والمعدود، مواصفات التنسيق (أرقام لاتينية، فاصلة آلاف، النسبة ملتصقة، «مليون
> دولار» بعد الرقم بعشرية واحدة، أسماء الأشهر)، والكسور اللفظية. stdlib فقط،
> حتمي بالكامل — لا نموذج لغوي يلمس رقماً.
"""
from __future__ import annotations

import math
import re

MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
             "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

# ── حروف الجر ─────────────────────────────────────────────────────────────
_FOREIGN = re.compile(r"^[A-Za-z0-9]")


def prep(letter: str, word: str) -> str:
    """ادمج حرف الجر (ل/ب/ك) بالكلمة: ل+ال = لل، ب/ك+ال ملتصقة، اسم أجنبي بشرطة وصل."""
    word = (word or "").strip()
    if not word:
        return ""
    if _FOREIGN.match(word):
        return f"{letter}ـ{word}"
    if word.startswith("ال"):
        if letter == "ل":
            return "لل" + word[2:]
        return letter + word
    return letter + word


# ── العدد والمعدود ──────────────────────────────────────────────────────────
# جدول المعدودات: مفرد، مثنى (رفع، جر/نصب)، جمع، جنس المفرد.
NOUNS: dict[str, dict] = {
    "دولة": {"sg": "دولة", "du_nom": "دولتان", "du_obl": "دولتين", "pl": "دول", "g": "f"},
    "سنة": {"sg": "سنة", "du_nom": "سنتان", "du_obl": "سنتين", "pl": "سنوات", "g": "f"},
    "مورّد": {"sg": "مورّد", "du_nom": "مورّدان", "du_obl": "مورّدين", "pl": "موردين", "g": "m"},
    "شهر": {"sg": "شهر", "du_nom": "شهران", "du_obl": "شهرين", "pl": "أشهر", "g": "m"},
    "جهة": {"sg": "جهة", "du_nom": "جهتان", "du_obl": "جهتين", "pl": "جهات", "g": "f"},
    "متطلب": {"sg": "متطلب", "du_nom": "متطلبان", "du_obl": "متطلبين", "pl": "متطلبات", "g": "m"},
}
# الصفات: (مذكر مفرد، مؤنث مفرد، مثنى مذكر رفع، مثنى مؤنث رفع، مثنى مذكر جر، مثنى مؤنث جر، جمع مذكر، جمع مؤنث)
ADJS: dict[str, dict] = {
    "مورّدة": {"m": "مورّد", "f": "مورّدة", "du_nom_m": "مورّدان", "du_nom_f": "مورّدتان",
               "du_obl_m": "مورّدين", "du_obl_f": "مورّدتين", "pl_m": "موردين", "pl_f": "مورّدة"},
    "مؤكدة": {"m": "مؤكد", "f": "مؤكدة", "du_nom_m": "مؤكدان", "du_nom_f": "مؤكدتان",
              "du_obl_m": "مؤكدين", "du_obl_f": "مؤكدتين", "pl_m": "مؤكدين", "pl_f": "مؤكدة"},
}
_UNITS_M = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة", "عشرة"]
_UNITS_F = ["", "واحدة", "اثنتان", "ثلاث", "أربع", "خمس", "ست", "سبع", "ثمان", "تسع", "عشر"]


def count(n: int, noun_spec: str, case: str = "nom") -> str:
    """العدد والمعدود: 1 مفرد + صفة «واحد/ة»، 2 مثنى، 3–10 عدد بعكس الجنس + جمع،
    11–99 رقم + مفرد منصوب، ≥100 رقم + مفرد مجرور. `noun_spec` = «دولة» أو «دولة مورّدة»."""
    parts = noun_spec.split()
    noun, adj = parts[0], (parts[1] if len(parts) > 1 else None)
    N = NOUNS[noun]
    g = N["g"]
    A = ADJS.get(adj) if adj else None
    obl = case in ("gen", "acc")
    if n == 1:
        one = "واحدة" if g == "f" else "واحد"
        a = (A[g] + " ") if A else ""
        return f"{N['sg']} {a}{one}"
    if n == 2:
        form = N["du_obl"] if obl else N["du_nom"]
        if A:
            form += " " + A[("du_obl_" if obl else "du_nom_") + g]
        return form
    if 3 <= n <= 10:
        num = (_UNITS_F if g == "f" else _UNITS_M)[n]   # عكس الجنس: مؤنث ← بلا تاء
        a = (" " + A["pl_" + g]) if A else ""
        return f"{num} {N['pl']}{a}"
    if 11 <= n <= 99:
        sg = N["sg"]
        if g == "m" and not sg.endswith("ة"):
            sg = sg + "اً"     # منصوب: «مورّداً»
        a = (" " + (A["f"] if g == "f" else A["m"] + "اً")) if A else ""
        return f"{n} {sg}{a}"
    a = (" " + A[g]) if A else ""
    return f"{fmt_int(n)} {N['sg']}{a}"


# ── التنسيق ─────────────────────────────────────────────────────────────────
def fmt_int(n) -> str:
    return f"{int(round(n)):,}"


def fmt(value, spec: str) -> str:
    """صيغ العرض: m1 «89.4 مليون دولار»، pct0 «19%»، pct1 «0.0%»، usd1 «6.2»، int «1,500»، year، month."""
    if value is None:
        raise ValueError("fmt(None): رقم غائب يُعلَن فجوةً لا يُعرَض")
    if spec == "m1":
        return f"{value:.1f} مليون دولار"
    if spec == "pct0":
        return f"{int(round(value))}%"
    if spec == "pct1":
        return f"{value:.1f}%"
    if spec == "usd1":
        return f"{value:.1f}"
    if spec == "int":
        return fmt_int(value)
    if spec == "year":
        return str(int(value))
    if spec == "month":
        return MONTHS_AR[int(value) - 1]
    if spec == "raw":
        return str(value)
    raise ValueError(f"صيغة غير معروفة: {spec}")


# ── الكسور اللفظية ──────────────────────────────────────────────────────────
_FRACTIONS = [
    (1 / 6, "سدس"), (1 / 5, "خمس"), (1 / 4, "ربع"), (1 / 3, "ثلث"), (2 / 5, "خمسي"),
    (1 / 2, "نصف"), (3 / 5, "ثلاثة أخماس"), (2 / 3, "ثلثي"), (3 / 4, "ثلاثة أرباع"),
]


def fraction_word(ratio: float, definite: bool = False) -> str:
    """أقرب كسر عربي لنسبة (0–1): 0.56 → «ثلاثة أخماس»، 0.49 → «نصف»؛ definite → «الربع»."""
    best = min(_FRACTIONS, key=lambda f: abs(f[0] - ratio))
    if abs(best[0] - ratio) > 0.06:
        return fmt(ratio * 100, "pct0")
    w = best[1]
    if definite:
        return {"ثلاثة أخماس": "ثلاثة الأخماس", "ثلاثة أرباع": "ثلاثة الأرباع"}.get(w, "ال" + w)
    return w


def years_word(n: int) -> str:
    """«أربع سنوات»، «سنتين»، «سنة واحدة» — للمدد (جر)."""
    return count(n, "سنة", "gen")


# ── الاتجاه ─────────────────────────────────────────────────────────────────
def direction(sign_value: float, up: str, down: str, flat: str | None = None) -> str:
    if flat is not None and abs(sign_value) < 1e-9:
        return flat
    return up if sign_value >= 0 else down


def ratio_change_pct(a: float, b: float) -> float:
    """نسبة التغير من a إلى b بالمئة (موقّعة)."""
    return (b / a - 1.0) * 100.0


_FRACTION_WORDS = {
    "سدس": 1 / 6, "خمس": 1 / 5, "ربع": 1 / 4, "ثلث": 1 / 3, "خمسي": 2 / 5, "خمسين": 2 / 5,
    "نصف": 1 / 2, "ثلاثة أخماس": 3 / 5, "ثلاثة الأخماس": 3 / 5, "ثلثي": 2 / 3, "ثلثين": 2 / 3,
    "ثلاثة أرباع": 3 / 4, "ثلاثة الأرباع": 3 / 4,
}
_FRACTION_RE = re.compile(r"(?<![\w\u0600-\u06FF])(?:[وفبلك])?(?:ال)?(ثلاثة (?:ال)?أخماس|ثلاثة (?:ال)?أرباع|خمسي|خمسين|ثلثي|ثلثين|سدس|خمس|ربع|ثلث|نصف)(?![\w\u0600-\u06FF])")


def verbal_fractions(text: str) -> list[tuple[str, float]]:
    """الكسور اللفظية في نص عربي → [(الكلمة، القيمة)] — لفحص الإسناد (P1-6)."""
    out = []
    for m in _FRACTION_RE.finditer(text or ""):
        w = m.group(1)
        out.append((w, _FRACTION_WORDS[w]))
    return out


def fraction_grounded(value: float, known: set, tol: float = 0.06) -> bool:
    """كسرٌ لفظي مسند إذا طابق نسبة رقمين معلومين (أو رقماً معلوماً بالمئة)."""
    ks = [float(k) for k in known if isinstance(k, (int, float))]
    if any(abs(k / 100.0 - value) <= tol for k in ks if 0 < k <= 100):
        return True
    for a in ks:
        for b in ks:
            if b and 0 < a / b <= 1 and abs(a / b - value) <= tol:
                return True
    return False

