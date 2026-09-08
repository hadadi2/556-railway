"""محلل رموز النظام المنسق (HS) لمنتجات سِلك — HS code resolver for Silk.

Maps an Arabic OR English product name to an international HS6 code using the
official CSV reference plus stdlib token matching. No network, no dependency.

> **العائلة `substring-false-positive` (مغلقةٌ في هذه الموجة).** كان الدليلُ
> يُقاس بالاحتواء الحرفيّ (`q in k or k in q`) فيمنح أيَّ تصادمٍ ٠٫٨٥ فأعلى —
> فوق عتبة البوّابة. «رقي» (بطيخ) داخل «ورقية» صنّف المناديلَ الورقية بطيخاً
> بثقة 0.875، و«طحين» داخل «طحينية» صنّف الحلاوةَ دقيقَ قمح بـ0.88. القاعدةُ
> الآن: **الدليلُ يُقاس على وحداتٍ كاملة** (`silk_hs_norm`)، والمطابقةُ
> الضبابية (difflib) محصورةٌ بنيوياً تحت عتبة القرار فلا تحسم شيئاً أبداً —
> ترشيحٌ لا قرار (البند ٧ من أمر الموجة).

Evidence is measured over whole tokens, never raw substrings; the fuzzy tier is
structurally capped below the decision threshold so it can only ever nominate a
candidate, never settle a classification.

seed scope / نطاق البيانات:
    data/hscodes_full.csv is the complete official HS2022 six-digit reference
    (5,613 codes, UN Comtrade) — chapter/heading hierarchy + English official
    description on every row, Arabic keywords (`keywords_ar`, semicolon-
    separated) on the subset migrated from the prior curated seed
    (`tools/migrate_hs_keywords.py`) plus a small hand-curated disambiguation
    set for known lexical collisions (butter: dairy/shea/cocoa/peanut; بن vs
    بنكهة). All codes are real international HS6 values; nothing is invented.
    The former partial seed (`data/hs_codes.csv`, ~5,627 rows) is retired —
    this file is now the sole reference for both resolution and validation.

Every result is a provenance-tagged DataPoint: weak/no match -> value=None,
confidence=0.0. The resolver never fabricates a code.
"""
from __future__ import annotations

import csv
import datetime
import difflib
import functools
import logging
import os

import silk_hs_norm as _hs_norm

log = logging.getLogger(__name__)

# DataPoint عقد مشترك — shared contract from the data layer, with a local
# fallback so this module imports and runs standalone (no hard dependency).
try:
    from silk_data_layer import DataPoint  # type: ignore
except Exception:  # pragma: no cover - fallback when data layer absent
    from dataclasses import dataclass

    @dataclass
    class DataPoint:  # mirrors the shared contract
        value: object
        source: str
        confidence: float
        note: str = ""
        retrieved_at: str = ""


_HERE = os.path.dirname(os.path.abspath(__file__))
_SOURCE = "Silk curated HS6 seed (HS Nomenclature / UN Comtrade)"

# نطاق سِلك: تصدير غير نفطي — الفصل 27 (وقود معدنية: نفط خام 2709، مكرر
# 2710، غازات 2711، قار ومشتقات 2712–2715، زيوت قطران 2707، فحم وكوك
# 2701–2706، كهرباء 2716) خارج النطاق بتعريف «الصادرات غير النفطية»
# الرسمي. ثابت واحد مسمّى ليضبطه المالك — فلترة نطاق لا حذف صفوف: المرجع
# الكامل يبقى في CSV، والمُحلَّل الواقع في فصل مستبعد يُعلن خارج النطاق.
EXCLUDED_HS_CHAPTERS: frozenset[str] = frozenset({"27"})

_EXCLUSION_MSG = ("منتج بترولي/وقود معدني — خارج نطاق سِلك للتصدير "
                  "غير النفطي (فصل HS {chapter})")

# فصولُ النظام المنسّق الحقيقية (بنية WCO الرسمية، ثابتٌ هيكليّ لا اسمُ منتجٍ
# أو دولة) — ٩٧ فصلاً مُرقَّماً ٠١–٩٧، والفصل ٧٧ محجوزٌ للاستعمال المستقبلي
# (غير مخصَّص لأي بضاعة اليوم). تُستعمَل لفحص «سلامة الفصل» على مرشّحي
# التصنيف العام (silk_hs_classifier.classify_general) — رمزٌ من نموذجٍ في
# فصلٍ غير موجود أصلاً (مثل «00» أو «98» تجاريًا أو رقمٍ مختلَق) يُرفَض فورًا
# قبل أيّ فحص تداخل نصّي، بمعزلٍ تامٍّ عن بذرة CSV الجزئية.
VALID_HS_CHAPTERS: frozenset[str] = frozenset(
    f"{n:02d}" for n in range(1, 98) if n != 77)


def chapter_of(hs_code: object) -> str:
    """فصل الرمز (أول رقمين) — نصٌّ فارغ إن كان الرمز أقصر من رقمين."""
    return str(hs_code or "").strip()[:2]


def chapter_valid(hs_code: object) -> bool:
    """هل فصل هذا الرمز فصلٌ حقيقيٌّ في بنية WCO؟ — فحصٌ هيكليٌّ بحت، لا
    علاقة له بمرجعنا الجزئي (CSV): رمزٌ من نموذجٍ قد يكون صحيحاً دولياً حتى
    لو غاب عن بذرتنا الـ٥٦٠٠ صفّ (المرجع الكامل ~٦٩٤٠ رمزاً)."""
    return chapter_of(hs_code) in VALID_HS_CHAPTERS


def exclusion_note(hs_code: object) -> str | None:
    """سبب الاستبعاد النطاقي لرمز HS، أو None إن كان داخل النطاق.

    نقطة الحقيقة الواحدة لفلترة النطاق — يستعملها المصنّف (أدناه)،
    والمحرّك لمسار hs_code الصريح، والاكتشاف العكسي لفلترة الفرص.
    """
    chapter = str(hs_code or "").strip()[:2]
    if chapter in EXCLUDED_HS_CHAPTERS:
        return _EXCLUSION_MSG.format(chapter=chapter)
    return None


def _abspath(path: str) -> str:
    """حوّل المسار النسبي إلى مطلق نسبةً لهذا الملف — resolve path relative to this file."""
    return path if os.path.isabs(path) else os.path.join(_HERE, path)


@functools.lru_cache(maxsize=4)
def load_hs_codes(path: str = "data/hscodes_full.csv") -> list[dict]:
    """حمّل مرجع رموز HS الكامل من CSV — load the full HS reference as dict rows.

    Cached: the 5,613-row CSV is parsed once and reused across resolve() calls.
    Every field is read as-is (csv.DictReader never coerces types — leading
    zeros in hs_code survive intact, no dtype handling needed).
    """
    fp = _abspath(path)
    try:
        with open(fp, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception as exc:  # missing/unreadable file degrades to empty
        log.warning("failed to load HS reference %s: %s", fp, exc)
        return []
    if path != "data/hscodes_full.csv":
        return rows
    # الدمج المُكيَّف لـ#139: القائمة الرسمية HS2022 لا تحمل ١٣ رمزاً قديماً
    # أعادت المراجعة ترقيمها (150910 زيت الزيتون البكر، 040310 الزبادي، …)
    # بينما بذرتنا القديمة تحملها بكلماتها العربية المنسَّقة — حذفُها يُسقِط
    # مطابقةَ منتجاتٍ حقيقية لرموزٍ خاطئة (regression مُثبَت: «زيت زيتون بكر
    # ممتاز» → 071120). الاتحاد يحفظ سلوك main حرفياً؛ ترحيلُ الرموز الـ١٣
    # لخلفائها HS2022 يتطلّب جداول الربط الرسمية (WCO correlation) بموجةٍ
    # مستقلة مستشهدةٍ بمصدرها — لا يُخترَع هنا (سابقة سوء ربط الكويت).
    seen = {r.get("hs_code") for r in rows}
    try:
        with open(_abspath("data/hs_codes.csv"), newline="",
                  encoding="utf-8") as f:
            legacy = [r for r in csv.DictReader(f)
                      if r.get("hs_code") and r["hs_code"] not in seen]
    except Exception:
        legacy = []
    return rows + legacy


def _row_desc(row: dict) -> str:
    """وصفُ صفٍّ للعرض بأيّ مخطّط — الرسمي الإنجليزي، وإلا أعمدة البذرة القديمة.
    لا يعيد None أبداً (ملاحظة DataPoint بلا 'None' حرفية)."""
    return (row.get("description_en") or row.get("name_ar")
            or row.get("name_en") or "").strip()


def _norm(s: str) -> str:
    """طبّع النص للمطابقة — **الطبقةُ المشتركة** (`silk_hs_norm`) لا نسخةٌ محلية.

    كانت هذه الدالةُ تخفض حالةَ الأحرف فقط بينما بوّابةُ التطابق الدلالي تطوي
    الألفَ والتاءَ المربوطة — تنميطان على مسارٍ واحد، عوّضهما المرجعُ بتكرار
    التهجئات صفّاً صفّاً. الآن مصدرٌ واحد (البند ٥ من أمر الموجة).
    """
    return _hs_norm.normalize(s)


def _keywords(row: dict) -> list[str]:
    """استخرج الكلمات المفتاحية لصف — keyword + description tokens for a row.

    `keywords_ar` مفصولةٌ بفاصلةٍ منقوطة `;` (لا فاصلة عادية — تفادياً لخلط
    فاصل القائمة بفاصل حقول CSV نفسه)."""
    kw = [_norm(k) for k in (row.get("keywords_ar") or "").split(";") if k.strip()]
    if not kw:  # صفٌّ بالمخطّط القديم (الرموز الـ١٣ القديمة من البذرة)
        kw = [_norm(k) for k in (row.get("keywords") or "").split(",")
              if k.strip()] + [_norm(row.get("name_ar", ""))]
        kw = [k for k in kw if k]
    return kw + [_norm(row.get("description_en", "") or row.get("name_en", ""))]


# ── رتبُ الدليل · the evidence tiers ────────────────────────────────
# ثلاثُ رتبٍ صريحةٌ مسمّاة بدل رقمٍ سحريّ مدفون. الترتيبُ بينها هو العقد:
# تطابقُ العبارة كاملةً > تطابقُ مجموعة الوحدات > تداخلٌ جزئيّ > ضبابيّ.
_EXACT_PHRASE = 1.0          # العبارةُ المُنمّطة نفسُها = مفتاحُ المرجع نفسُه
_TOKEN_SET_EQUAL = 0.95      # الوحداتُ نفسُها بترتيبٍ آخر
_PARTIAL_BASE = 0.40         # أرضيّةُ التداخل الجزئيّ
_PARTIAL_SPAN = 0.55         # مداه (فـF1=1 مستحيلٌ هنا: يساوي تطابقَ المجموعة)
# **رتبةُ مصطلح العائلة.** مفتاحُ المرجع مشروحٌ بالكامل داخل اسم المنتج
# (استرجاعٌ تامّ): «جبن» داخل «جبن شيدر»، «تمر» داخل «تمر مكنوز». الزائدُ في
# الاسم صفةُ صنفٍ لا يحملها أيُّ وصفٍ جمركيّ، فمعاقبتُه بـF1 المتماثل تُسقِط
# تصنيفاتٍ صحيحةً كثيرة. الرتبةُ تتدرّج بدقّة التغطية: كلّما كثر ما لا يشرحه
# المفتاحُ من الاسم، قلّ الدليل — و«زبدة» داخل «زبدة الفول السوداني» (دقّة
# ٠٫٣٣) تقع تحت العتبة كما يجب.
_FAMILY_BASE = 0.70
_FAMILY_SPAN = 0.25
# **السقفُ البنيويّ للمطابقة الضبابية.** difflib يقيس تشابهَ الحروف لا المعنى،
# فلا يجوز أن يحسم تصنيفاً أبداً. السقفُ دون عتبة القرار (0.80) ودون عتبة
# `resolve_all` (0.70) معاً — أي أنه **ترشيحٌ فقط**، بنيوياً لا بالمعايرة.
_FUZZY_CAP = 0.69


def _score_keys(qn: str, qt: frozenset, keys: tuple) -> float:
    """نواةُ الدليل — أعلى رتبةٍ يبلغها أيُّ مفتاحٍ من مفاتيح الصفّ.

    `keys` أزواجُ (مفتاحٌ مُنمّط، مجموعةُ وحداته) مبنيّةٌ مرّةً في الفهرس.
    القاعدةُ الحاكمة: **لا احتواءَ حرفياً عبر حدود الوحدات** — «رقي» لا تلتقي
    «ورقية» هنا مهما تشابهتا (عائلة `substring-false-positive`).
    """
    if not qn:
        return 0.0
    best = 0.0
    for kn, kt in keys:
        if not kn:
            continue
        if qn == kn:
            return _EXACT_PHRASE
        if not (qt and kt):
            continue
        inter = len(qt & kt)
        if not inter:
            continue
        if qt == kt:
            score = _TOKEN_SET_EQUAL
        elif inter == len(kt):
            # المفتاحُ كلُّه مشروحٌ داخل الاسم — رتبةُ مصطلح العائلة أعلاه.
            score = _FAMILY_BASE + _FAMILY_SPAN * (inter / len(qt))
        else:
            # F1 يوازن الاتجاهين: «كم من المنتج يشرحه المفتاح» و«كم من
            # المفتاح يشرحه المنتج». الاتجاهُ الواحد وحده يخدع — «زبدة» تُغطّى
            # بالكامل داخل «زبدة الفول السوداني» (دقّة ١٫٠) بينما المفتاحُ يصف
            # منتجاً آخر تماماً (استرجاع ٠٫٣٣). حسابٌ حتميّ لا مُعايرةٌ على اختبار.
            precision = inter / len(qt)
            recall = inter / len(kt)
            f1 = 2 * precision * recall / (precision + recall)
            score = _PARTIAL_BASE + _PARTIAL_SPAN * f1
        if score > best:
            best = score
    return round(best, 4)


def _fuzzy_score(qn: str, keys: tuple, matcher=None) -> float:
    """رتبةُ التشابه الحرفيّ — مسقوفةٌ دون القرار دائماً (ترشيحٌ لا حسم).

    البند ٢٧ (الأداء): `matcher` مُمرَّرٌ من المستدعي بمُقارَنٍ واحدٍ ثابتِ
    الطرف الثاني (الاستعلام)، فيُبنى فهرسُ الاستعلام مرّةً لا مرّةً لكل صفّ؛
    و`real_quick_ratio` يقصّ الأغلبيةَ الساحقة قبل الحساب الكامل.
    """
    if not qn or not keys:
        return 0.0
    m = matcher or difflib.SequenceMatcher(None, "", qn)
    best = 0.0
    for kn in keys:
        if not kn:
            continue
        m.set_seq1(kn)
        if m.real_quick_ratio() <= best or m.quick_ratio() <= best:
            continue
        r = m.ratio()
        if r > best:
            best = r
    return round(min(best, _FUZZY_CAP), 4)


def _row_keys(row: dict) -> tuple:
    """مفاتيحُ صفٍّ مُنمّطةً مع وحداتها — الشكلُ الذي يستهلكه `_score_keys`."""
    out = []
    for kw in _keywords(row):
        kn = _hs_norm.normalize(kw)
        if kn:
            out.append((kn, _hs_norm.token_set(kn)))
    return tuple(out)


def _fuzzy_keys(row: dict, keys: tuple | None = None) -> tuple:
    """مفاتيحُ الرتبة الضبابية لصفٍّ — **نقطةُ الحقيقة الواحدة** للمسارين.

    الاسمُ العربيّ الأساس (أوّلُ مفتاحين) + الوصفُ الرسميّ فقط — قياسُ difflib
    على كلّ مفتاحٍ من ستّةٍ يضاعف الكلفةَ بلا إشارةٍ أفضل، والرتبةُ مسقوفةٌ
    دون القرار أصلاً فدقّتُها ليست حاسمة.

    كانت `_score` تقيس الضبابيةَ على **كلّ** المفاتيح بينما `_index`/`retrieve`
    على هذا الجزء وحده — فرمزُ الكتالوج (`_catalog_lexical`) كان يُقاس على
    مقياسٍ أوسع من منافسيه في `cands.sort` واختبار `min_separation`. الآن
    الصفُّ نفسُه بالاستعلام نفسِه يعطي الرقمَ نفسَه على المسارين.
    """
    if keys is None:
        keys = _row_keys(row)
    fuzzy = tuple(kn for kn, _ in keys[:2]) + (_hs_norm.normalize(
        row.get("description_en") or row.get("name_en") or ""),)
    return tuple(k for k in fuzzy if k)


def _score(query: str, row: dict) -> float:
    """احسب قوة المطابقة 0..1 لصفٍّ واحد — نقطةُ فحصٍ/تشخيصٍ مفردة.

    المسارُ الحارّ يمرّ بالفهرس (`_index`) لا بهذه: هنا يُعاد بناءُ مفاتيح
    الصفّ في كل نداء.
    """
    qn = _hs_norm.normalize(query)
    if not qn:
        return 0.0
    keys = _row_keys(row)
    score = _score_keys(qn, _hs_norm.token_set(qn), keys)
    return score if score else _fuzzy_score(qn, _fuzzy_keys(row, keys))


# الفهرسُ مربوطٌ بهويّة قائمة الصفوف التي بُني منها — لا بذاكرةٍ مستقلّة.
# `load_hs_codes` مُخزَّنةٌ فتعيد **الكائن نفسه** حتى يُمسَح تخزينُها؛ ففحصُ
# الهويّة يجعل الفهرسَ يُعيد بناءَ نفسه تلقائياً بعد أيّ `cache_clear`.
# بذاكرتين مستقلّتين كان `extend_from_comtrade_rows` (يمسح الأولى) يترك
# الثانيةَ تُصنِّف على مرجعٍ قديم **بصمت** — أخطرُ أشكال العطل.
# القيمة: {path: (rows_obj, built)}؛ السقفُ أربعةُ مسارات — كسقف الجارة
# `_ROWS_CACHE` في silk_hs_confirm.py — عند التجاوز يُحذَف الأقدمُ إدراجياً
# (`dict` يحفظ الترتيب). هذا حذفٌ FIFO بترتيب البناء لا LRU حقيقياً — نفسُ
# التحفّظ المُوثَّق على الجارة: نداءٌ لمسارٍ قديمٍ لا يُنعِش موضعه.
_INDEX_CACHE: dict = {}
_INDEX_CACHE_MAX = 4


def _index(path: str = "data/hscodes_full.csv") -> tuple:
    """فهرسٌ مقلوبٌ مبنيٌّ مرّةً — (مدخلاتُ الصفوف، خريطةُ وحدة ⇒ صفوف).

    البند ٢٧ (الأداء): بلا هذا الفهرس كان كلُّ طلبٍ يُنمّط ٥٦١٣ صفّاً × ~٦
    مفاتيح ثمّ يقيس difflib على كلٍّ منها. الآن التنميطُ مرّةً واحدة، والطلبُ
    لا يلمس إلا الصفوفَ التي تشترك مع الاستعلام في وحدةٍ واحدة على الأقل.

    مُخزَّنٌ بعمر **كائن** الصفوف لا بمفتاح المسار (راجع `_INDEX_CACHE` أعلاه).
    """
    rows = load_hs_codes(path)
    cached = _INDEX_CACHE.get(path)
    if cached is not None and cached[0] is rows:
        return cached[1]
    entries: list = []
    postings: dict = {}
    for i, row in enumerate(rows):
        keys = _row_keys(row)
        toks: set = set()
        for _, kt in keys:
            toks |= kt
        # مفاتيحُ الرتبة الضبابية من نقطة الحقيقة الواحدة `_fuzzy_keys` —
        # المقياسُ نفسُه الذي تقيس عليه `_score` (مسارُ رمز الكتالوج).
        entries.append((row, keys, frozenset(toks), _fuzzy_keys(row, keys)))
        for t in toks:
            postings.setdefault(t, []).append(i)
    built = (tuple(entries), {t: tuple(v) for t, v in postings.items()})
    _INDEX_CACHE.pop(path, None)          # إعادةُ البناء تُجدِّد موضع الإدراج
    _INDEX_CACHE[path] = (rows, built)
    while len(_INDEX_CACHE) > _INDEX_CACHE_MAX:
        _INDEX_CACHE.pop(next(iter(_INDEX_CACHE)), None)
    return built


def retrieve(product_name: str, top_n: int = 5,
             path: str = "data/hscodes_full.csv",
             min_score: float = 0.0) -> list[dict]:
    """**استرجاعُ المرشّحين** — الخطوةُ التي تقترح، لا التي تقرّر (البند ٧).

    تُعيد قائمةً مرتّبةً من `{"row", "hs_code", "description", "score", "tier"}`
    بلا أيّ بوّابة: لا قصَّ عند ٠٫٧، ولا حجبَ بالتأكيد الدلاليّ، ولا فلترةَ
    نطاق. الحكمُ كلُّه يقع بعدها في `silk_hs_pipeline` — فصلُ الاسترجاع عن
    القرار هو عينُ ما طلبه البند ٧، وهو ما يجعل «مرشّحون معروضون» و«رمزٌ
    مُعتمَد» شيئين مختلفين لا شيئاً واحداً.

    حتميّةٌ تامّة: نفسُ المدخل ⇒ نفسُ الترتيب (كسرُ التعادل بالرمز تصاعدياً).
    """
    qn = _hs_norm.normalize(product_name)
    if not qn:
        return []
    qt = _hs_norm.token_set(qn)
    entries, postings = _index(path)
    hits: set = set()
    for t in qt:
        hits.update(postings.get(t, ()))
    scored: list = []
    for i in hits:
        row, keys, _, _fz = entries[i]
        score = _score_keys(qn, qt, keys)
        if score > 0.0:
            scored.append((score, row, "token"))
    if not scored:
        # لا وحدةَ مشتركة مع أيّ صفّ — الرتبةُ الضبابية وحدها، وهي مسقوفةٌ
        # دون القرار فلا تُنتِج إلا اقتراحاً يُسأل عنه المستخدم.
        matcher = difflib.SequenceMatcher(None, "", qn)
        for row, _keys, _toks, fuzzy in entries:
            score = _fuzzy_score(qn, fuzzy, matcher)
            if score > 0.0:
                scored.append((score, row, "fuzzy"))
    scored.sort(key=lambda t: (-t[0], str(t[1].get("hs_code") or "")))
    out: list = []
    for score, row, tier in scored[:max(1, top_n)]:
        if score < min_score:
            break
        out.append({"row": row, "hs_code": str(row.get("hs_code") or ""),
                    "description": _row_desc(row), "score": round(score, 4),
                    "tier": tier})
    return out


def resolve(product_name: str, path: str = "data/hscodes_full.csv") -> DataPoint:
    """طابق أفضل رمز HS لاسم منتج عربي أو إنجليزي — best HS6 match for one name."""
    results = resolve_all(product_name, top_n=1, path=path)
    if results:
        return results[0]
    return DataPoint(None, _SOURCE, 0.0,
                     note=f"no HS match for {product_name!r}",
                     retrieved_at=datetime.date.today().isoformat())


def resolve_all(product_name: str, top_n: int = 3,
                path: str = "data/hscodes_full.csv") -> list[DataPoint]:
    """رتّب أفضل المرشحين — ranked HS6 candidates as DataPoints (weak -> None).

    **مبنيّةٌ على `retrieve`** (مسارُ استرجاعٍ واحد لا اثنان): الاسترجاعُ
    يقترح، وهذه الدالّة تُطبّق بوّاباتِ القرار — قصُّ الضعيف، فلترةُ النطاق
    غير النفطيّ، والتأكيدُ الدلاليّ. عقدُها الخارجيّ لم يتغيّر حرفياً.
    """
    today = datetime.date.today().isoformat()
    if not load_hs_codes(path):
        return [DataPoint(None, _SOURCE, 0.0, note="HS seed empty/unavailable",
                          retrieved_at=today)]
    hits = retrieve(product_name, top_n=max(1, top_n), path=path)
    out: list[DataPoint] = []
    for hit in hits:
        sc, r = hit["score"], hit["row"]
        # قص الثقة: ضعيف جداً => لا قيمة — clamp weak matches to value=None.
        if sc < 0.7:
            out.append(DataPoint(None, _SOURCE, 0.0,
                                 note=f"weak match for {product_name!r} "
                                      f"(best='{_row_desc(r)}', "
                                      f"score={sc:.2f})",
                                 retrieved_at=today))
            continue
        # بوابة النطاق غير النفطي (8d): تطابق قوي في فصل مستبعد يُعلن خارج
        # النطاق برسالة واضحة — لا يُحلَّل ولا يُخفى سبب الرفض.
        excl = exclusion_note(r["hs_code"])
        if excl:
            out.append(DataPoint(None, _SOURCE, 0.0,
                                 note=f"{excl} — أقرب تطابق: "
                                      f"{_row_desc(r)} ({r['hs_code']})",
                                 retrieved_at=today))
            continue
        # بوّابة الصفة المميّزة (عائلة `unresolved-hs-silent-spend`، الدرس ٣٢):
        # درجةٌ عاليةٌ قد تأتي من تطابق كلمةٍ **عامّة** مُتضمَّنةٍ في اسمٍ مركّب
        # («زبدة» داخل «زبدة الفول السوداني» => رمز الألبان 040510) بينما صفةُ
        # المنتج المميّزة غائبةٌ عن وصف الرمز. عقد عدم الاختلاق: رمزٌ صفتُه
        # المميّزة غير مغطّاةٍ بوصفه **فجوةٌ معلَنة** (value=None) لا رمزٌ خاطئٌ
        # واثق — نفس نواة التداخل التي تستعملها بوّابة التأكيد (مصدرُ حقيقةٍ
        # واحد، لا استدلالٌ جديد). التأكيد `None` (لا وصف/لا صفات) لا يُخفِّض:
        # فشلٌ آمنٌ مفتوح — لا نُسقِط مطابقةً لمجرّد تعذّر الحكم عليها.
        try:
            from silk_hs_confirm import confirm_hs
            conf = confirm_hs(product_name, r["hs_code"], path=path)
        except Exception:  # noqa: BLE001 — تعذّر التأكيد لا يكسر الحلّ
            conf = None
        if conf is not None and conf.get("confirmed") is False:
            out.append(DataPoint(
                None, _SOURCE, 0.0,
                note=f"رمزٌ غير مؤكَّد لـ{product_name!r}: {conf.get('reason')}"
                     f" — أقرب تطابق {_row_desc(r)} "
                     f"({r['hs_code']}, score={sc:.2f}). صنِّف عبر المصنّف العام "
                     f"أو أدخِل الرمز يدوياً.",
                retrieved_at=today))
            continue
        out.append(DataPoint(
            r["hs_code"], _SOURCE, round(sc, 2),
            note=_row_desc(r),
            retrieved_at=today))
    if not out:
        out.append(DataPoint(None, _SOURCE, 0.0,
                             note=f"no HS match for {product_name!r}",
                             retrieved_at=today))
    return out


@functools.lru_cache(maxsize=1)
def load_hs_reference(path: str = "data/hs_reference.csv") -> dict:
    """الوصفُ الرسميُّ الكامل لكل رمز HS6 — the full official HS6 reference.

    بذرتُنا (`data/hs_codes.csv`) نُمِّيت من هذا المرجع لكنّ حقول أوصافها
    قد تكون مختصرةً أو معرَّبةً بحرّية، بينما **العتباتُ الرقمية** التي
    تُميِّز بنودَ الترويسة الواحدة (نسبة دهن/سعة/وزن/بريكس) تعيش في النصّ
    الرسميّ حصراً. أيّ قاعدةٍ تقرأ عتبةً يجب أن تقرأها من هنا لا من البذرة
    (الدرس ٣٣: **حلِّل المصدر لا النثر** — المصدرُ هنا هو المرجع الرسميّ).

    مقروءٌ مرّة واحدة ومُخزَّن؛ ملفٌّ غائب/تالف => قاموسٌ فارغ (فجوة معلنة،
    لا وصفٌ مختلَق)."""
    fp = _abspath(path)
    out: dict = {}
    try:
        with open(fp, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                code = str(row.get("hscode") or "").strip()
                desc = str(row.get("description") or "").strip()
                if len(code) == 6 and desc:
                    out[code] = desc
    except Exception as exc:  # noqa: BLE001 — مرجعٌ غائب = فجوة، لا انهيار
        log.warning("failed to load HS reference %s: %s", fp, exc)
    return out


def official_description(hs_code: object) -> str:
    """الوصف الرسميّ لرمز HS6 من المرجع الكامل — `""` إن لم يوجد (لا اختلاق)."""
    return load_hs_reference().get(str(hs_code or "").strip(), "")


def extend_from_comtrade_rows(rows: list[dict],
                              path: str = "data/hs_codes.csv") -> int:
    """[متروكة/deprecated] وسّع بذرةً قديمة الشكل (hs_code,name_en,name_ar,
    keywords) من جدول مرجع Comtrade. القائمة الحالية (`data/hscodes_full.csv`)
    كاملةٌ رسمياً أصلاً (٥٦١٣ رمزاً) فلا حاجة عملية للتوسيع، وشكل أعمدتها
    مختلفٌ عن هذه الدالة (`chapter/description_en/keywords_ar` لا
    `name_en/name_ar/keywords`) — استدعاؤها على المسار الجديد سيُفسِد الملف.
    أُبقيت للتوافق التاريخي فقط؛ راجع `tools/migrate_hs_keywords.py` للترحيل
    الفعلي المستعمَل في هذه الهجرة.

    Each input row needs at least hs_code + name_en (name_ar/keywords optional).
    Skips codes already present. Returns the number of rows added.
    """
    if os.path.basename(path) == "hscodes_full.csv":
        # القائمة الرسمية بمخطّطٍ مختلف — الإلحاق بأعمدة البذرة القديمة يُفسِدها
        # صامتاً. القاعدة مُنفَذة لا استشارية (docstring أعلاه).
        raise ValueError("extend_from_comtrade_rows لا تكتب على القائمة "
                         "الرسمية hscodes_full.csv — مخطّط أعمدتها مختلف")
    fp = _abspath(path)
    existing = {r["hs_code"] for r in load_hs_codes(path)}
    new = [r for r in rows if r.get("hs_code") and r["hs_code"] not in existing]
    if not new:
        return 0
    try:
        with open(fp, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["hs_code", "name_en", "name_ar", "keywords"])
            for r in new:
                w.writerow({k: r.get(k, "") for k in
                            ("hs_code", "name_en", "name_ar", "keywords")})
        load_hs_codes.cache_clear()  # file changed -> drop stale cached rows
        return len(new)
    except Exception as exc:
        log.warning("failed to extend HS seed %s: %s", fp, exc)
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    samples = ["تمور", "زعفران", "عسل سدر", "olive oil", "بخور عود",
               "silk scarf", "مجوهرات ذهب", "قهوة", "spaceship"]
    for name in samples:
        dp = resolve(name)
        print(f"{name:>14}  ->  hs={dp.value}  conf={dp.confidence}  | {dp.note}")
