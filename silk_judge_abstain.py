"""حقّ الحَكَم في الامتناع — Judge Abstain (محرك دراسة السوق، القاعدة ٥).

```
IF scope mismatch OR any pillar has zero eligible records
   OR unresolved critical conflict:
       RETURN ABSTAIN
ELSE: score from eligible records only
```

**الموجة ٣ — SHADOW فقط (تسجيلٌ لا تغيير).** يُحسَب هنا فقط ما كان الحَكَم
سيُقرِّره لو فُعِّل — لا مفهوم ABSTAIN رسمي في `silk_synthesis`/`silk_decision`
اليوم، وهذا الملف **لا يُنشئه**. لا يُمَسّ `verdict`/`score` الحقيقيّان بأيّ
حال؛ الإشارة تُرفَق إضافياً (`result["judge_abstain_shadow"]`) للقياس فقط.

**تدقيقُ ما قبل الكتابة (البند الذي طلبه أمر المُشرِف صراحةً — "الجزءُ
الخطِر، لا منطقُ الامتناع نفسه").** مسحٌ شامل لكل مستهلكي `score`/
`confidence` كأرقام عبر `silk_render.py`، `silk_reports.py`، `api.py`،
`silk_deep_pillars.py`، `web/index.html`، `web/platform.html` وجد:

- طبقةُ العرض/التقارير/الواجهة **معزولةٌ عن None بالفعل** في كل موضعٍ
  اطُّلع عليه (`isinstance(x,(int,float))`، `!= null`، `_fmt()` الذي يعيد
  «—» صراحةً عند None). لا حاجة لتغييرٍ هناك.
- الثغرتان الحقيقيتان كلتاهما في طبقة **الحساب**، لا العرض:
  `silk_agents.JuryCommittee.evaluate()` (لا يُصدر None أبداً — يُسقِط
  لصفر عند تغطيةٍ صفرية) و`silk_decision.decide()`'s `confidence` (يُحسَب
  دوماً حتى في فرع `score is None` نفسه). **هذه الموجة لا تلمس أيّاً
  منهما** — التفعيل الفعليّ (تصيير `score=None` حقاً في تلك الدالّتين)
  موجةٌ لاحقة، بعد أن يُدقَّق استهلاكُ الحقلين تحديداً في كل مستهلكٍ
  فعليّ لهما (لا العرض العام وحده).
- `api.py:2211-2214`: حارسٌ قائمٌ يُسقِط مفتاح `total_score`/`confidence`
  من صفّ السوق كلّياً حين `None` (لا يُمرِّره كـNone) — سلوكٌ يستحقّ
  ملاحظةً صريحة لأيّ موجةٍ تُفعِّل الامتناع فعلياً: الحقلُ يختفي، لا
  يظهر فارغاً.

**«الأعمدة» هنا = تقاطعات المحلل الخمسة الثابتة**
(`silk_market_analyst.REQUIRED_CATEGORIES`: demand/entry_cost/
price_competitiveness/entry_door/swot) — لا أعمدة `silk_decision`
الخمسة (تلك لمسار `/analyze` القديم، منتَجٌ مختلف). يُعاد استعمال مُطعِّم
سجلّ الحقائق (`silk_fact_records.fact_record_from_finding`) لحساب
الأهلية (Tier A + مطابقة الميثاق) على كل بند في كل عمود — لا منطق تصنيفٍ
موازٍ.

**حدٌّ معلن ثالث:** «تعارضٌ حرجٌ غير محسوم» (الشرط الثالث في القاعدة أعلاه)
**غير مربوطٍ بعد** ببيانات حقيقية — وكيل التناقض (`silk_contradiction`)
يحتاج استخراج قيم export/import/سعر من نتائج بعثاتٍ حقيقية، وهذا استخراجٌ
لم يُبنَ بعد (يحتاج تتبّعاً حياً أولاً كي لا يُخمَّن أيّ حقل نصّي يحمل أيّ
قيمة — نفس قاعدة `mission-tuning-and-evals`). هذا الملف يُعلن الغياب
صراحةً (`unresolved_critical_conflict_checked: False`) بدل افتراض `False`
صامتاً كأنه فُحص ولم يُوجَد شيء."""
from __future__ import annotations

from silk_fact_records import fact_record_from_finding


def check_pillar_eligibility(by_category: dict, charter=None) -> dict:
    """لكل عمود من الخمسة الثابتة (`REQUIRED_CATEGORIES`): هل يحمل سجلّ
    حقيقةٍ واحداً مؤهَّلاً للحكم على الأقل (درجة A ومطابقاً لنطاق الميثاق)؟
    يعيد قائمة الأعمدة الصِّفرية + تفصيل عددي لكل عمود (للتسجيل/التشخيص، لا
    للحكم). **يفحص الخمسة كلَّها دوماً** — عمودٌ غائبٌ كلياً عن `by_category`
    (لم يُصنَّف فيه بندٌ واحد) هو أسوأ حالة «صفر مؤهَّل»، لا حالةٌ تُتخطَّى."""
    from silk_market_analyst import REQUIRED_CATEGORIES
    by_category = by_category or {}
    zero_eligible: list = []
    detail: dict = {}
    for cat in REQUIRED_CATEGORIES:
        findings = by_category.get(cat) or []
        records = []
        for f in findings:
            rec, _reason = fact_record_from_finding(f, cat, charter)
            if rec is not None:
                records.append(rec)
        eligible_count = sum(1 for r in records if r.verdict_eligible)
        detail[cat] = {"total_records": len(records),
                       "eligible_records": eligible_count}
        if eligible_count == 0:
            zero_eligible.append(cat)
    return {"zero_eligible_pillars": zero_eligible, "detail": detail}


def would_abstain(charter=None, by_category: dict | None = None) -> dict:
    """الإشارة الكاملة — SHADOW: لا تُستهلَك من `synthesize`/`silk_decision`
    اليوم، مُحسَبةٌ بمعزلٍ تام لتُسجَّل فقط. `charter`: كائن `Charter` أو
    dict (`Charter.to_dict()`) — كلاهما مدعوم."""
    halted = charter.get("halted") if isinstance(charter, dict) else getattr(
        charter, "halted", False)
    halt_reason = charter.get("halt_reason") if isinstance(charter, dict) else getattr(
        charter, "halt_reason", None)
    scope_mismatch = bool(halted)

    pillar_check = check_pillar_eligibility(by_category or {}, charter)
    zero_eligible_pillars = pillar_check["zero_eligible_pillars"]

    should_abstain = scope_mismatch or bool(zero_eligible_pillars)

    reasons = []
    if scope_mismatch:
        reasons.append(f"عدم تطابق نطاق الميثاق: {halt_reason}")
    if zero_eligible_pillars:
        reasons.append("أعمدةٌ بلا سجلّ حقيقةٍ مؤهَّل: " +
                       "، ".join(zero_eligible_pillars))

    return {
        "would_abstain": should_abstain,
        "scope_mismatch": scope_mismatch,
        "zero_eligible_pillars": zero_eligible_pillars,
        "pillar_detail": pillar_check["detail"],
        # فجوةٌ معلنة — راجع توثيق الوحدة أعلاه. `None` لا `False`: لم يُفحَص،
        # لا أنه فُحص فلم يُوجَد شيء.
        "unresolved_critical_conflict_checked": False,
        "reasons": reasons,
    }
