"""بنيةُ السوق تهيئةً — market structure as data (الصنف ١٠ من موجة عيوب التقرير).

> **العيوبُ المرصودة** في تقريرٍ حيٍّ واحد: سعرُ صرفٍ واحد و«تقلّب 0.00%» لدولةٍ
> بسعرين متباعدين، وقيودٌ من سلطةٍ ومرفأٌ تحت أخرى بلا إقليمِ هدفٍ مذكور؛ وبندٌ
> جمركيٌّ يغطّي فئةً كاملةً مقروءاً سوقَ منتجٍ واحد؛ وقائمةُ روابطَ فيها نشاطٌ لا
> صلةَ له بالمنتج بينما يغيب عنها الموزّعون الذين يوصي بهم التقرير؛ وحدودٌ
> تستشهد بنظامِ مطابقةٍ يخصّ دولةً أخرى.
>
> **الجذر:** هذه كلُّها **وقائعُ بنيةِ سوقٍ** لا قواعدَ منطق، ومع ذلك لا موطنَ
> مُدقَّقاً لها: مفاتيحُ التهيئة القائمة أربعةُ أسواقٍ من ٣٨ وأغلبُها بلا قارئ،
> واسمُ نظامِ المطابقة محقونٌ في **موجّه بعثةٍ** لكلّ سوق.
>
> **الحلّ:** هذه الوحدةُ قارئةٌ واحدة لكلّ واقعةِ بنية: تقرأ سجلَّي الملامح
> (`data/market_profiles.json` / `data/product_profiles.json`) وجداولَ المراجع
> القائمة (`market_locale.csv` للعملة، `ports_l1.csv` للمرفأ) وسجلَّ أنظمة
> المطابقة الجديد (`regulatory_schemes_l1.csv`). **صفرُ اسمِ دولةٍ أو رمزِ HS في
> الشيفرة** — يحرسه لِنتُ مصدرٍ في الاختبار.

**خلف رايةٍ مطفأةٍ افتراضياً** (`SILK_MARKET_STRUCTURE_CONFIG=1`): بلا الراية لا
يتغيّر موجّهٌ ولا سطحُ عرضٍ ولا شدّةُ فحص — السلوكُ السابق هو نفسُه حرفياً
(قرار المالك: لا حجب جديداً، والتغييرُ خلف رايته).

منطقُ قراءةٍ صرف: صفرُ شبكة، صفرُ تعديلٍ على أيّ قيمة. وكلُّ غيابٍ يُعاد **فراغاً
معلَناً** لا قيمةً مخمَّنة (عقدُ عدم الاختلاق).
"""
from __future__ import annotations

import csv
import functools
import os

FLAG = "SILK_MARKET_STRUCTURE_CONFIG"
_HERE = os.path.dirname(os.path.abspath(__file__))

# أسماءُ الكتل التي تعني «لا مالكَ قُطريّ» في سجلّ الأنظمة — نظامٌ بهذا الوسم لا
# يُحتسَب مخالفةً لأيّ سوق (معيارٌ دوليّ أو اسمٌ تتقاسمه برامجُ عدّة دول).
NO_COUNTRY_OWNER = ("INTL", "MULTI")


def enabled() -> bool:
    """هل رايةُ الصنف ١٠ مفعّلة؟ — نمطُ `silk_figure_store.enabled` القائم."""
    return os.environ.get(FLAG, "").strip().lower() in ("1", "true", "yes")


# ── قراءةُ الجداول المرجعية · L1 reference tables ────────────────────────────
@functools.lru_cache(maxsize=8)
def _rows(name: str) -> tuple:
    """صفوفُ جدولٍ مرجعيٍّ في `data/` — يتجاهل أسطرَ التعليق التوثيقية.

    نفسُ سلوك `silk_llm_runtime._load_csv` (بلاغُ الموجة ٨: `DictReader` بلا
    تصفيةٍ كان يعامل سطرَ `#` رأساً للجدول)، مكتوبٌ هنا بلا استيراد الوحدةِ
    الثقيلة كي تبقى هذه الوحدةُ قابلةً للاستيراد بلا مفتاحٍ ولا شبكة.
    """
    path = os.path.join(_HERE, "data", name)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    except OSError:
        return ()
    try:
        return tuple(dict(r) for r in csv.DictReader(lines))
    except csv.Error:
        return ()


def _iso(v: object) -> str:
    return str(v or "").strip().upper()


def _profile(iso3: object) -> dict:
    """ملامحُ السوق من السجلّ — قاموسٌ فارغٌ عند أيّ تعذّر (فشلٌ آمنٌ مفتوح)."""
    try:
        import silk_profiles
        return silk_profiles.market_profile(_iso(iso3)) or {}
    except Exception:  # noqa: BLE001 — تهيئةٌ غائبةٌ ليست خطأَ تشغيل
        return {}


def _product(hs_code: object) -> dict:
    try:
        import silk_profiles
        return silk_profiles.product_profile(hs_code) or {}
    except Exception:  # noqa: BLE001
        return {}


def _cited(node: object, default: object = None) -> object:
    try:
        import silk_profiles
        return silk_profiles.cited_value(node, default)
    except Exception:  # noqa: BLE001
        return default


# ── عملةُ السوق · market currency ────────────────────────────────────────────
def market_currency(iso3: object) -> str:
    """رمزُ عملةِ السوق (ISO 4217) — من الجدول المرجعيّ أوّلاً ثمّ من الملامح.

    الصنفُ ١٢ ترك خطراً معلَناً: «ريال» اسمٌ يسعُ عدّةَ دول، فيُوسَم برمزِ
    الأشهرِ منها. موطنُ حلِّه هذه الدالّة — عملةُ السوق **مُهيَّأةٌ أصلاً**
    لثمانيةٍ وثلاثين سوقاً في `market_locale.csv`، وما كان ناقصاً وصلُها.
    غيابُ الصفّ يُعاد فراغاً: لا تخمينَ رمزٍ من اسمٍ مشترك.
    """
    code = _iso(iso3)
    if not code:
        return ""
    for r in _rows("market_locale.csv"):
        if _iso(r.get("iso3")) == code:
            cur = str(r.get("currency") or "").strip().upper()
            if cur:
                return cur
            break
    return _iso(_cited((_profile(code).get("identity") or {}).get("currency"),
                       ""))


# ── مرفأُ الوجهة · destination gateway ───────────────────────────────────────
def main_port(iso3: object) -> str:
    """مرفأُ الوجهة الرئيس — من `ports_l1.csv` ثمّ من ممرّات الملامح."""
    code = _iso(iso3)
    if not code:
        return ""
    for r in _rows("ports_l1.csv"):
        if _iso(r.get("iso3")) == code:
            port = str(r.get("main_port") or "").strip()
            if port:
                return port
            break
    for c in ((_profile(code).get("logistics") or {}).get("corridors") or []):
        if isinstance(c, dict) and str(c.get("main_port") or "").strip():
            return str(c["main_port"]).strip()
    return ""


# ── جهاتُ التقييس · standards bodies ─────────────────────────────────────────
def standards_bodies(iso3: object) -> tuple:
    """جهةُ التقييس المُهيَّأة للسوق، مع كتلتِه التجارية إن كانت مُهيَّأة.

    تُستعمَل **لإثراء البلاغ** لا شرطاً للفحص: أربعةُ أسواقٍ من ٣٨ مُهيَّأة،
    وفحصٌ يشترط التهيئة ينام في الباقي (الدرس ٩٨).
    """
    prof = _profile(iso3)
    out = []
    body = _cited((prof.get("regulatory_regime") or {}).get("standards_body"),
                  "")
    if str(body or "").strip():
        out.append(str(body).strip())
    for b in ((prof.get("trade_regime") or {}).get("blocs") or []):
        name = str(_cited(b, "") or "").strip()
        if name and name not in out:
            out.append(name)
    return tuple(out)


# ── الإقليمُ المستهدَف وتعدّدُ السلطات · target region · multi-authority ─────
def multi_authority(iso3: object) -> bool:
    """هل السوقُ مُهيَّأٌ بأكثر من سلطةٍ بحكم الواقع؟ (المفتاحُ اختياريّ)."""
    return bool(_cited(_profile(iso3).get("multi_authority"), False))


def target_region(iso3: object) -> str:
    """الإقليمُ المستهدَف داخل السوق — فراغٌ حين لا يُهيَّأ."""
    return str(_cited(_profile(iso3).get("target_region"), "") or "").strip()


def regions(iso3: object) -> tuple:
    """أقاليمُ السوق المُهيَّأة — كلُّ إقليمٍ قاموسٌ باسمه وما هُيِّئ له.

    **البياناتُ غيرُ مُدخَلةٍ لأيّ سوقٍ بعد** (قرارُ مالكٍ مسجَّل: المخطَّطُ
    والمُدقِّقُ والحارسُ تُشحَن، والصفوفُ إدخالٌ لاحق). فتُعاد `()` اليوم —
    غيابٌ معلَنٌ لا صمت.
    """
    out = []
    for row in (_profile(iso3).get("regions") or []):
        if not isinstance(row, dict):
            continue
        name = str(_cited(row.get("name"), "") or "").strip()
        if not name:
            continue
        item = {"name": name}
        for key in ("fx", "customs", "port", "collection", "distributors",
                    "prices"):
            val = _cited(row.get(key), None)
            if val is not None:
                item[key] = val
        out.append(item)
    return tuple(out)


# ── اتّساعُ البند ومدى سعر الحدود · HS scope · price range ───────────────────
def hs_scope(hs_code: object) -> str:
    """`exact` أو `broad` كما هُيِّئ للمنتج — فراغٌ حين لا يُهيَّأ."""
    return str(_cited(_product(hs_code).get("hs_scope"), "") or "").strip()


def price_range(hs_code: object) -> "dict | None":
    """مدى سعرِ الحدود المعقول للمنتج (دولار/كجم) — `None` حين لا يُهيَّأ."""
    band = _product(hs_code).get("price_range") or {}
    lo = _cited(band.get("border_usd_per_kg_min"), None)
    hi = _cited(band.get("border_usd_per_kg_max"), None)
    try:
        lo_f = float(lo) if lo is not None else None
        hi_f = float(hi) if hi is not None else None
    except (TypeError, ValueError):
        return None
    if lo_f is None or hi_f is None:
        return None
    return {"min": lo_f, "max": hi_f}


# ── سجلُّ أنظمة المطابقة · conformity-scheme registry ────────────────────────
@functools.lru_cache(maxsize=1)
def schemes() -> tuple:
    """صفوفُ سجلّ الأنظمة — `(scheme, owner_iso3, owner_bloc, authority_ar)`."""
    out = []
    for r in _rows("regulatory_schemes_l1.csv"):
        name = str(r.get("scheme") or "").strip()
        if not name:
            continue
        out.append({"scheme": name,
                    "owner_iso3": _iso(r.get("owner_iso3")),
                    "owner_bloc": _iso(r.get("owner_bloc")),
                    "authority_ar": str(r.get("authority_ar") or "").strip(),
                    "source_url": str(r.get("source_url") or "").strip()})
    return tuple(out)


def scheme_owner(name: object) -> dict:
    """مالكُ نظامِ المطابقة — قاموسٌ فارغٌ لاسمٍ غيرِ مُسجَّل (لا تخمين)."""
    key = str(name or "").strip().upper()
    if not key:
        return {}
    for row in schemes():
        if row["scheme"].upper() == key:
            return dict(row)
    return {}


# اسمُ الكتلة في السجلّ ⇄ اسمُ الثابت في `silk_blocs` — الاسمُ المنشورُ للكتلة
# ليس اسمَ ثابتِها («EU» مقابل `EU27`)، وترجمةُ الاسمَين جدولٌ لا تفريع.
_BLOC_ALIASES = {"EU": "EU27", "EUROPEAN UNION": "EU27"}


def _bloc_members(bloc: str) -> frozenset:
    """أعضاءُ كتلةٍ تجارية — من `silk_blocs` القائم (مصدرُ العضوية الواحد)."""
    key = _BLOC_ALIASES.get(bloc.strip().upper(), bloc.strip().upper())
    try:
        import silk_blocs
        members = getattr(silk_blocs, key, None)
        if isinstance(members, (frozenset, set, tuple, list)):
            return frozenset(_iso(m) for m in members)
    except Exception:  # noqa: BLE001
        pass
    return frozenset()


def scheme_belongs_to(name: object, iso3: object,
                      origin_iso3: object = "") -> bool:
    """هل يخصّ هذا النظامُ هذه الدراسة؟

    نعم حين: اسمُه غيرُ مُسجَّل (لا نحكم على ما لا نعرف)، أو مالكُه دوليٌّ/مشترك
    (`NO_COUNTRY_OWNER`)، أو مالكُه القُطريُّ هو سوقُ الهدف، أو مالكُه كتلةٌ
    سوقُ الهدف عضوٌ فيها. وإلّا فلا — وهي الحالةُ الوحيدة التي يُطلِق فيها
    الحارس.

    و**دولةُ المنشأ مشروعةٌ دائماً**: اشتراطاتُ الخروج من بلد المصدّر جزءٌ
    قانونيٌّ من كلّ تقرير (`silk_requirements_agent` يثبّت صفوفَ الخروج على
    المنشأ)، فنظامُ المنشأ ليس تسرّباً. إسقاطُ هذا الاستثناء كان سيُطلِق على
    كلّ تقريرٍ يذكر جهةَ بلدِ المصدّر — أي على الصحيح.
    """
    row = scheme_owner(name)
    if not row:
        return True
    code = _iso(iso3)
    home = _iso(origin_iso3)
    bloc = row.get("owner_bloc") or ""
    if bloc in NO_COUNTRY_OWNER:
        return True
    owner = row.get("owner_iso3") or ""
    if owner and owner in (code, home):
        return True
    if bloc:
        members = _bloc_members(bloc)
        if not code:
            return True
        return code in members or (bool(home) and home in members)
    return not owner


if __name__ == "__main__":       # فحصٌ يدويّ سريع على سوقٍ مُهيَّأ
    import json
    import sys
    code = (sys.argv[1] if len(sys.argv) > 1 else "").upper()
    print(json.dumps({
        "currency": market_currency(code), "port": main_port(code),
        "standards_bodies": standards_bodies(code),
        "multi_authority": multi_authority(code),
        "target_region": target_region(code), "regions": regions(code),
        "schemes": len(schemes()),
    }, ensure_ascii=False, indent=1, default=list))
