"""وكيل الاشتراطات لسِلك — Silk requirements/compliance agent (waves 3 + 5b).

القسم الخامس من الرؤية كاملاً: **الطبقة ١** مرجع ثابت في
`data/requirements_l1.csv` (خليجي + **سلسلة القرار الأوروبية** §12.2
بلوائحها المرقّمة من EUR-Lex + بنود **الخروج السعودي** §12.6) يُقرأ من
القرص بلا شبكة؛ **الطبقة ٢** بحث حي مستهدف (أسئلة تحقق محددة، لا اكتشاف
من صفر — §12.3) اختياري بمفتاح بحث؛ **الطبقة ٣** عمل قالب العرض.

تصنيف «قابلية التقنين» (§12.5) يظهر على القائمة نفسها:
  مقنّن بالكامل (الاتحاد الأوروبي/بريطانيا) > شبه موحّد (الخليج) >
  موثّق جزئياً (البقية — بنودها تحمل «تحقق محلياً» صراحةً).

«الأهلية أولاً» (§12.2-1): منتج حيواني المصدر إلى أوروبا — بند إدراج
المنشأة يتصدر القائمة والبنود التالية تُوسم مشروطةً به، لا تُسرد كأن
الطريق سالك (§12.7-2).

حدود صريحة: مرجع يُزامَن دورياً (الملاحق الأوروبية ~كل 6 أشهر) —
**ليس** استشارة قانونية؛ سوق غير مغطى = فجوة «تحقق محلياً» لا اختلاق.
"""
from __future__ import annotations

import csv
import functools
import logging
import os

import silk_blocs
from silk_data_layer import DataPoint, _today
from silk_agents import BaseAgent, AgentReport

log = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSV = os.path.join(_HERE, "data", "requirements_l1.csv")
_SOURCE = "Silk L1 requirements reference (official portals / EUR-Lex)"

# توسعات وسوم الأسواق — market wildcards in the reference. عضويةُ الكُتل من
# المصدر الواحد (`silk_blocs`) لا مكتوبةً صلباً هنا — DEF-2: كانت `_EU` تحمل
# ١٥ عضواً فقط فتسقط سلسلةُ الامتثال عن ١٢ دولةً عضواً بصمت. الآن EU27 كاملة.
_GCC = silk_blocs.GCC
_EU = silk_blocs.EU27

# فصول HS — food (01-24) والحيواني المصدر (§12.2-1).
_FOOD_CHAPTERS = {f"{n:02d}" for n in range(1, 25)}
_ANIMAL_CHAPTERS = {"01", "02", "03", "04", "05", "16"}

# طيف قابلية التقنين (§12.5) — الدرجة تظهر على القائمة نفسها.
#
# GBR أُخرجت من «مقنّن بالكامل» عمداً (تصحيح 2026-08-17): كانت تحمل الوسم
# بينما `_matches` يوسّع صفوف "EU" إلى EU27 فقط — فتخرج بريطانيا موسومة
# «مقنّنة بالكامل» **و**«غير مغطاة بالمرجع الثابت» معاً، وسمٌ يعد بدقةٍ لا
# صفوف خلفها. تعود إلى الطيف الأعلى فقط مع صفوف retained-EU-law حقيقية في
# `data/requirements_l1.csv` باستشهاد legislation.gov.uk (قاعدة المرجع:
# «cite the regulation, don't invent one» — لا وسم بلا بيانات).
_TIERS = (
    (_EU, "مقنّن بالكامل",
     "لوائح مرقّمة (EUR-Lex) — بحث حي للتغييرات فقط؛ ثقة عالية"),
    (_GCC, "شبه موحّد",
     "خريطة من مصادر رسمية، تحديث ربع سنوي؛ ثقة متوسطة-عالية"),
)
_TIER_PARTIAL = ("موثّق جزئياً",
                 "مرجع محدود + اعتماد أكبر على البحث الحي — "
                 "البنود غير المؤكدة موسومة «تحقق محلياً»")


def codification_tier(market: str) -> tuple[str, str]:
    """درجة قابلية التقنين — the market's codification tier (§12.5)."""
    for markets, tier, note in _TIERS:
        if market in markets:
            return tier, note
    return _TIER_PARTIAL


def hs_category(hs_code: str | None) -> str:
    """صنّف فئة المرجع من رمز HS — 'food' for chapters 01-24, else 'all'."""
    digits = "".join(ch for ch in str(hs_code or "") if ch.isdigit())
    return "food" if digits[:2] in _FOOD_CHAPTERS else "all"


def is_animal_origin(hs_code: str | None) -> bool:
    """حيواني المصدر؟ — HS chapters 01-05 & 16 (vision §12.2-1)."""
    digits = "".join(ch for ch in str(hs_code or "") if ch.isdigit())
    return digits[:2] in _ANIMAL_CHAPTERS


@functools.lru_cache(maxsize=1)
def _load_reference() -> tuple[dict, ...]:
    """حمّل مرجع الطبقة ١ — read the L1 CSV once (offline, no network)."""
    try:
        with open(_CSV, newline="", encoding="utf-8") as f:
            return tuple(csv.DictReader(f))
    except Exception as exc:  # noqa: BLE001 — missing reference degrades, never crashes
        log.warning("L1 requirements reference unavailable (%s): %s", _CSV, exc)
        return ()


def _matches(row: dict, market: str, category: str, direction: str,
             animal: bool) -> bool:
    """هل ينطبق البند؟ — row applies to market×category×direction?"""
    row_market = (row.get("market") or "").strip().upper()
    market_ok = (row_market == market
                 or (row_market == "GCC" and market in _GCC)
                 or (row_market == "EU" and market in _EU))
    row_cat = (row.get("category") or "all").strip().lower()
    cat_ok = (row_cat == "all" or row_cat == category
              or (row_cat == "animal" and animal))
    dir_ok = (row.get("direction") or "").strip().lower() == direction
    return market_ok and cat_ok and dir_ok


def _seq(row: dict) -> int:
    """ترتيب سلسلة القرار — the row's decision-chain order (default 50)."""
    try:
        return int(row.get("seq") or 50)
    except ValueError:
        return 50


# ── الحجبُ والانطباق (الموجة C، §٥ من `docs/ENGINE_AUDIT.md`) ─────────────
#
# قبل هذه الموجة كان المرجعُ يحمل بنوداً **بلا درجةِ حجب**، والحالةُ «الصلبة»
# الوحيدة مُرمَّزةً صلباً في الشيفرة لصفٍّ واحد (`eligibility_first`) وأثرُها
# **تعليقُ ملاحظة** لا منعُ حكم. فحتى بوّابةُ EU 2017/625 كانت ملاحظةً لا
# بوّابة. الآن الدرجةُ **بيانٌ في المدوّنة** يقرؤه المحرّك:
#
#   hard        — تُرفَض الشحنة قانونياً بدونه. يمنع أيّ توصيةٍ إيجابية.
#   conditional — حاجبٌ لجزءٍ من الحالات فقط؛ ينطبق حين يصدق `applies_when`،
#                 وإلّا فحالتُه **غيرُ معروفة** (لا «سالك» ولا «حاجب»).
#   procedural  — يؤثّر في الزمن والتكلفة لا في الجواز.
#
# «استشهد باللائحة، لا تخترعها»: الدرجةُ تصنيفٌ لصفٍّ قائمٍ بمصدره، لا لائحةٌ
# جديدة. وصفٌّ بلا عمودٍ يُعامَل `procedural` (أضعفُ افتراضٍ ممكن) فلا تنقلب
# مدوّنةٌ قديمة إلى حواجزَ صامتة.
# وسمُ النقطة البنيوية — **معرّفٌ داخليّ**: المستهلِكون يمفصلون عليه،
# والعارضُ يستبدله بنصٍّ بلغةِ أعمالٍ قبل أيّ سطحِ عميل (C9).
REGULATORY_BLOCKER_KEY = "regulatory_blockers_v1"

BLOCKING_HARD = "hard"
BLOCKING_CONDITIONAL = "conditional"
BLOCKING_PROCEDURAL = "procedural"
_BLOCKING_LEVELS = (BLOCKING_HARD, BLOCKING_CONDITIONAL, BLOCKING_PROCEDURAL)


def blocking_level(row: dict) -> str:
    """درجةُ حجبِ الصفّ — قيمةٌ معلومةٌ حصراً، وإلا الأضعف (`procedural`)."""
    raw = (row.get("blocking") or "").strip().lower()
    return raw if raw in _BLOCKING_LEVELS else BLOCKING_PROCEDURAL


def applies_to(row: dict, hs_code: str | None, category: str) -> bool | None:
    """هل ينطبق هذا البند على هذه الحالة تحديداً؟ — حتميّ، بلا تخمين.

    يعيد `True` (ينطبق) أو `False` (لا ينطبق) أو **`None`** — والأخيرة ليست
    «لا أدري» كسولةً بل تصريحٌ بنيويّ: **الانطباق لا يُعرَف من رمز HS وحده**
    ويحتاج دليلاً خارجياً (تحليلُ مختبر لحدود المتبقيات مثلاً). العقدُ
    المؤسِّس يمنع أن نُصيّر هذه الحالةَ صفراً أو «سالكاً».

    الصيغُ المدعومة في `applies_when` (فارغٌ = ينطبق كلّما طابق الصفُّ):
      `hs_chapter:02,04,16`   فصولُ HS المنطبقة
      `category:food`         فئةُ المرجع
      `needs_evidence`        لا يُعرَف من المدخلات — يُعاد `None`
      `processing:raw,semi`   درجةُ تصنيع الصنف (الموجة د-٢)
    """
    spec = (row.get("applies_when") or "").strip()
    if not spec:
        return True
    digits = "".join(ch for ch in str(hs_code or "") if ch.isdigit())
    for clause in (c.strip() for c in spec.split(";") if c.strip()):
        if clause == "needs_evidence":
            return None
        key, _, raw_vals = clause.partition(":")
        vals = {v.strip().lower() for v in raw_vals.split(",") if v.strip()}
        key = key.strip().lower()
        if key == "hs_chapter":
            if not digits:
                return None          # لا رمزَ ⇒ الانطباقُ غيرُ معروف
            if digits[:2] not in vals:
                return False
        elif key == "category":
            if (category or "").lower() not in vals:
                return False
        elif key == "processing":
            # الموجة د-٢ (البند ٦): الاشتراطُ يُربَط بدرجة تصنيع الصنف الفعلي
            # (raw/semi/processed من data/hs_category_l1.csv) لا بالفصل العامّ.
            try:
                from silk_ai_judge import processing_level
                lvl = processing_level(hs_code)
            except Exception:  # noqa: BLE001
                lvl = None
            if lvl is None:
                return None          # فصلٌ غيرُ مصنَّف ⇒ لا يُخمَّن
            if lvl not in vals:
                return False
        else:                        # محدِّدٌ غيرُ معروف ⇒ لا يُخمَّن
            return None
    return True


def regulatory_blockers(market: str, hs_code: str | None,
                        category: str | None = None) -> list[dict]:
    """الحواجزُ التنظيمية كحقلٍ **بنيويّ** لا كنثر (§٥-٣ من الجرد).

    كلُّ حاجزٍ: `{item, authority, source_url, blocking, applies, resolved}`.

    `resolved` هنا **`None` دائماً** — سِلك لا يملك ما يُثبِت أنّ مصنعاً بعينه
    أنهى إدراجَه أو تسجيله؛ و`False` كانت ستكون ادّعاءً بعدمٍ لم يُرصَد.
    المستهلِكون يقرؤونها «غيرُ محسوم» ويطلبون الحسم، ولا يُصيّرونها رسوباً.
    """
    market = (market or "").strip().upper()
    if not market:
        return []
    cat = (category or hs_category(hs_code)).lower()
    animal = is_animal_origin(hs_code)
    out: list[dict] = []
    for row in sorted((r for r in _load_reference()
                       if _matches(r, market, cat, "entry", animal)), key=_seq):
        level = blocking_level(row)
        if level == BLOCKING_PROCEDURAL:
            continue
        applies = applies_to(row, hs_code, cat)
        if applies is False:
            continue                 # لا ينطبق ⇒ ليس حاجزاً على هذه الحالة
        out.append({
            "item": row.get("item_ar"), "authority": row.get("authority"),
            "source_url": row.get("source_url"), "blocking": level,
            "applies": applies,      # True | None (يحتاج دليلاً)
            "seq": _seq(row), "resolved": None,
        })
    return out


def regulatory_state(market: str, hs_code: str | None,
                     category: str | None = None) -> dict:
    """حالةُ الحواجز كاملةً — الحقلُ الذي يخزّنه المحرّك ويقرؤه العرضُ والبوّابة.

    تُبنى **حتى حين لا حاجزَ منطبقاً**: `checked=True` بقائمتين فارغتين تقول
    «فُحِصت ولا حاجز»، وغيابُ الحقل كلِّه يقول «لم تُفحَص». الفرقُ بينهما قرارٌ
    تجاريّ لا تفصيلٌ تقنيّ، فلا يُترَك للصمت.
    """
    blk = regulatory_blockers(market, hs_code, category)
    cat = (category or hs_category(hs_code)).lower()
    # **الموجة C (البند R-04).** `access_timeline` كان **شيفرةً ميتة**: معرَّفاً
    # ولا يُنادى، والبوّابةُ تكتفي بالبحث عن عبارة «المدة الكلية» في النثر.
    # فتقريرٌ يكتب العبارةَ بلا حساب يمرّ، وتقريرٌ يحسب المدّةَ بصياغةٍ أخرى
    # يُلام — مطابقةُ عباراتٍ لا قياس. الآن يُحسَب ويُخزَّن بنيوياً.
    try:
        timeline = access_timeline((market or "").strip().upper(), cat)
    except Exception:  # noqa: BLE001 — الجدولُ إضافةٌ لا شرطُ حالة
        timeline = {}
    return {"open_hard": open_hard_blockers(blk),
            "needs_verification": unverified_blockers(blk),
            "all": blk, "checked": True, "access_timeline": timeline}


def open_hard_blockers(blockers: list[dict]) -> list[dict]:
    """الحواجزُ الصلبةُ **المؤكَّدُ انطباقُها** وغيرُ المحسومة — تمنع الإيجاب.

    `applies is True` حصراً. حاجزٌ لا يُعرَف انطباقُه (`None`) **لا يُعَدّ
    منعاً**: عدُّه منعاً كان سيحجب كلّ تقريرٍ أوروبيّ لأنّ «الغذاء الجديد»
    بندٌ لا يُحسَم من رمز HS. يُصرَّح به في `unverified_blockers` بدلاً من ذلك
    — إعلانُ ما لا نعرفه لا يساوي ادّعاءَ منعٍ ولا ادّعاءَ سلامة.
    """
    return [b for b in (blockers or [])
            if b.get("blocking") == BLOCKING_HARD
            and b.get("applies") is True
            and not b.get("resolved")]


def unverified_blockers(blockers: list[dict]) -> list[dict]:
    """بنودٌ حاجبةٌ **لا يُعرَف انطباقُها** من المدخلات — تحتاج حسماً بدليل.

    لا تمنع الحكم، لكنها تُعرَض على المصنع بوصفها «يجب التحقّق قبل الالتزام»:
    صمتُنا عنها كان سيُقرَأ «لا تنطبق»، وهو ادّعاءٌ لم يُرصَد.
    """
    return [b for b in (blockers or [])
            if b.get("applies") is None and not b.get("resolved")]


def _row_dp(row: dict, direction: str, conditional: bool = False) -> DataPoint:
    """بند مرجع كنقطة موسومة — one checklist item as a provenance DataPoint."""
    try:
        conf = float(row.get("confidence") or 0.5)
    except ValueError:
        conf = 0.5
    note = row.get("note") or "مرجع طبقة ١ — تحقق قبل الشحن"
    if conditional:
        note += " | مشروط باجتياز بند الأهلية أعلاه — لا تعتبره سالكاً قبله"
    return DataPoint(
        value={"item": row.get("item_ar"), "authority": row.get("authority"),
               "direction": direction, "source_url": row.get("source_url"),
               "seq": _seq(row)},
        source=_SOURCE, confidence=conf, note=note, retrieved_at=_today())


def _live_verification(items: list[DataPoint], market: str) -> list[DataPoint]:
    """الطبقة ٢ — بحث حي بأسئلة تحقق محددة (§12.3)، لا اكتشاف من صفر.

    اختيارية بمفتاح بحث؛ keyless/بلا شبكة => نقطة فجوة موسومة واحدة.
    سؤال واحد مستهدف (أعلى بند بالسلسلة) — لا استعلامات عامة.
    """
    try:
        from silk_websearch_agent import web_search
        top = next((dp for dp in items if dp.value), None)
        if top is None:
            return []
        authority = str(top.value.get("authority") or "")
        query = (f"latest amendment revision {authority} import requirements "
                 f"{market}")
        raw = web_search(query, num=2)
        real = [f for f in raw if f.value is not None]
        if not real:
            note = raw[0].note if raw else "no results"
            return [DataPoint(None, "Live verification (Serper)", 0.0,
                              f"التحقق الحي غير متاح ({note}) — اعتمد على "
                              "مرجع الطبقة ١ وتاريخ مزامنته", _today())]
        return [DataPoint(f.value, "Live verification (Serper)", 0.4,
                          f"تحقق حي مستهدف: '{query}' — نتيجة غير مُتحقَّقة، "
                          "قارنها بالنص الرسمي", _today()) for f in real]
    except Exception as e:  # noqa: BLE001 — الطبقة ٢ لا تُسقط الطبقة ١
        log.warning("live verification failed for %s: %s", market, e)
        return [DataPoint(None, "Live verification (Serper)", 0.0,
                          f"التحقق الحي فشل: {type(e).__name__}", _today())]


class RequirementsAgent(BaseAgent):
    """وكيل الاشتراطات — dual-direction compliance checklist (L1 + L2)."""

    PAID = False
    PREF_KEY = "regulatory"
    SOURCE = _SOURCE

    def __init__(self) -> None:
        super().__init__("RequirementsAgent")

    def _execute(self, task: dict) -> AgentReport:
        """قائمة تحقق الدخول+الخروج — entry (market) + Saudi-exit checklist.

        task keys: market_iso3, hs_code, category (اختياري)،
        with_live_verification (اختياري — الطبقة ٢). Fully offline by default.
        """
        market = (task.get("market_iso3") or task.get("iso3") or "").strip().upper()
        if not market:
            return AgentReport(self.name, [], True,
                               "لا سوق — missing market_iso3")
        hs = task.get("hs_code")
        category = (task.get("category") or hs_category(hs)).lower()
        animal = is_animal_origin(hs)
        rows = _load_reference()
        if not rows:
            return AgentReport(
                self.name,
                [DataPoint(None, _SOURCE, 0.0,
                           "مرجع الطبقة ١ غير متاح — L1 reference unavailable",
                           _today())],
                True, "لا مرجع اشتراطات — L1 reference unavailable")

        tier, tier_note = codification_tier(market)
        entry_rows = sorted((r for r in rows
                             if _matches(r, market, category, "entry", animal)),
                            key=_seq)
        # الأهلية أولاً (§12.7-2): وجود بند حيواني seq=10 يجعل البقية مشروطة.
        eligibility_first = (animal and entry_rows
                             and (entry_rows[0].get("category") or "") == "animal")
        entry = [_row_dp(r, "entry",
                         conditional=(eligibility_first and i > 0))
                 for i, r in enumerate(entry_rows)]
        exit_items = [_row_dp(r, "exit")
                      for r in sorted((r for r in rows
                                       if _matches(r, "SAU", category,
                                                   "exit", animal)), key=_seq)]

        findings: list[DataPoint] = []
        if entry:
            findings.extend(entry)
        else:
            findings.append(DataPoint(
                None, _SOURCE, 0.0,
                f"سوق {market} ({tier}) غير مغطى بالمرجع الثابت بعد — "
                "تحقق محلياً (verify locally)", _today()))
        findings.extend(exit_items)

        if task.get("with_live_verification"):
            findings.extend(_live_verification(entry, market))

        summary = (f"[{tier}] "
                   + (f"{len(entry)} entry item(s) for {market} ({category}"
                      f"{', animal-origin' if animal else ''}) "
                      if entry else
                      f"سوق {market} بلا مرجع دخول (تحقق محلياً) ")
                   + f"+ {len(exit_items)} Saudi-exit item(s)"
                   + (" | الأهلية أولاً: البنود التالية مشروطة بها"
                      if eligibility_first else ""))
        return AgentReport(self.name, findings, False, summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk RequirementsAgent — L1 (GCC + EU chain) + optional L2, offline")
    for market, hs in (("ARE", "080410"), ("DEU", "080410"),
                       ("DEU", "040900"), ("KEN", "080410")):
        rep = RequirementsAgent().run({"market_iso3": market, "hs_code": hs})
        print(f"  [{market} × {hs}] {rep.summary}")


# ── الموجة ٥ (توجيه §5.5): الجدول الزمني للنفاذ · market-access timeline ────

def access_timeline(market: str, category: str) -> dict:
    """المدة الكلية من قرار الدخول حتى أول شحنة نظامية — كمدى، أو فجوة
    معلنة تسمّي ما ينقص. يقرأ الأعمدة الاختيارية `processing_days_min`/
    `processing_days_max`/`fee` من مرجع L1 إن قُنِّنت (إضافة الأعمدة عمل
    بياني مُرجعي — «استشهد باللائحة، لا تخترعها»)؛ غيابها = فجوة مسماة،
    لا تقدير مختلَق."""
    rows = [r for r in _load_reference()
            if _matches(r, market, category, "entry", False)]
    steps, missing = [], []
    for r in rows:
        step = {"item": r.get("item_ar"), "authority": r.get("authority"),
                "source_url": r.get("source_url")}
        try:
            dmin = float(r.get("processing_days_min") or "")
            dmax = float(r.get("processing_days_max") or dmin)
            step["days_min"], step["days_max"] = dmin, dmax
        except (TypeError, ValueError):
            missing.append(str(r.get("item_ar") or "بند"))
        if r.get("fee"):
            step["fee"] = r.get("fee")
        steps.append(step)
    if not steps:
        return {"steps": [], "total_days": None,
                "gap": ("لا صفوف اشتراطات دخول مقنّنة لهذا الزوج سوق/فئة "
                        "في المرجع — الجدول الزمني فجوة معلنة")}
    if missing:
        return {"steps": steps, "total_days": None,
                "gap": ("مدد المعالجة غير مقنّنة بعد في المرجع للبنود: "
                        + "، ".join(missing[:6])
                        + " — المدى الكلي لا يُحسب جزئياً؛ يُغلق بتقنين "
                          "عمودي processing_days_min/max بمصادرهما "
                          "الرسمية")}
    lo = sum(s["days_min"] for s in steps)
    hi = sum(s["days_max"] for s in steps)
    return {"steps": steps,
            "total_days": {"min": lo, "max": hi},
            "note": ("المدى الكلي من القرار حتى أول شحنة نظامية بافتراض "
                     "تتابع الخطوات — خطوات متوازية تُقصّره؛ المصدر: مرجع "
                     "المتطلبات L1 بصفوفه المُقنّنة")}
