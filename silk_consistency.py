"""فحص اتجاه الحكم مقابل الدليل عبر التشغيلات · cross-run verdict direction.

البند 7 من أمر إصلاح المحرّك (تقريرا #10/#11 حليب×الأردن — direct
reproduction): بين التشغيلتين هبطت الثقة (40%→20%) وهبط عددُ المؤشرات
المرصودة (108→87) وارتفعت الفجوات المعلنة (9→15)، ومع ذلك ترقّى الحكم
(«لا تدخل»→«دخول مشروط») — الحكم لا يتحرك مع الدليل. القاعدة حرفياً: لنفس
(المنتج × السوق)، إن هبطت الثقةُ **و**هبط عددُ المؤشرات **و**ارتفعت
الفجوات بينما ترقّى الحكم ⇒ يتوقف التسليم ويُبلَّغ (فحص
`verdict_evidence_direction` المُفشِل في بوابة الجودة).

حتميّ بالكامل: الإحصاءات تُعدّ من نتائج بعثات التشغيلة نفسها (مرصود =
قيمة غير فارغة؛ فجوة = قيمة فارغة معلنة)، والحكم من المصدر الواحد
`silk_narrative.authoritative_verdict`. تعذُّر المقارنة (لا تشغيلة سابقة،
حكم غير مرتَّب، ثقة غائبة) = فحص معلَن «غير قابل للمقارنة»، لا تخمين.
"""
from __future__ import annotations

import logging

log = logging.getLogger("silk.consistency")

__all__ = ["verdict_rank", "evidence_stats", "direction_check",
           "check_against_history"]


def verdict_rank(raw: object) -> "int | None":
    """رتبةُ الحكم للمقارنة الاتجاهية — أدنى فأعلى. غير المرتَّب None.

    «NO-GO» تُفحَص قبل «GO» لأنها تحتويها حرفياً؛ INSUFFICIENT/
    INCONCLUSIVE/فارغ = لا رتبة (حالةُ أدلة لا حكم — لا يُدّعى اتجاه)."""
    s = str(raw or "").strip().upper()
    if not s or "INSUFFICIENT" in s or "INCONCLUSIVE" in s:
        return None
    if "NO-GO" in s or "NO GO" in s:
        return 0
    if "WATCH" in s:
        return 1
    if "CONDITIONAL" in s:
        return 2
    if "GO" in s:
        return 3
    return None


def _findings_of(mission: object) -> list:
    if isinstance(mission, dict):
        return mission.get("findings") or []
    return getattr(mission, "findings", None) or []


def _fv(f: object) -> object:
    return f.get("value") if isinstance(f, dict) else getattr(f, "value", None)


def evidence_stats(result: dict) -> dict:
    """إحصاءات الدليل لتشغيلةٍ من نتيجتها المخزَّنة/الحيّة — حتمية.

    المرصود/الفجوات من نتائج البعثات (نفس تعريف المبدأ التأسيسي: القيمة
    الفارغة فجوةٌ معلنة)، والحكمُ والثقة من المصدر الواحد."""
    from silk_narrative import authoritative_verdict
    dr = (result or {}).get("deep_research") or {}
    raw, conf = authoritative_verdict(dr.get("verdict") or {})
    observed = gaps = 0
    for m in (dr.get("missions") or {}).values():
        for f in _findings_of(m):
            if _fv(f) is None:
                gaps += 1
            else:
                observed += 1
    try:
        conf_f = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_f = None
    return {"verdict": str(raw or ""), "verdict_rank": verdict_rank(raw),
            "confidence": conf_f, "observed": observed, "gaps": gaps}


def direction_check(prev: dict, curr: dict) -> dict:
    """هل ترقّى الحكم بينما ساءت كلُّ مؤشرات الدليل؟ (شروط الأمر الثلاثة
    مجتمعةً + الترقية). أيُّ طرفٍ غير قابلٍ للمقارنة = فحص معلَن لا حكم."""
    pr, cr = prev.get("verdict_rank"), curr.get("verdict_rank")
    pc, cc = prev.get("confidence"), curr.get("confidence")
    if pr is None or cr is None or pc is None or cc is None:
        return {"checked": True, "comparable": False, "inconsistent": False,
                "previous": prev, "current": curr,
                "note": "المقارنة الاتجاهية غير ممكنة — حكم أو ثقة غير "
                        "مرتَّبين في إحدى التشغيلتين"}
    upgraded = cr > pr
    conf_dropped = cc < pc
    observed_dropped = curr["observed"] < prev["observed"]
    gaps_rose = curr["gaps"] > prev["gaps"]
    inconsistent = bool(upgraded and conf_dropped and observed_dropped
                        and gaps_rose)
    note = ""
    if inconsistent:
        note = ("الحكم ترقّى من "
                f"«{prev['verdict']}» إلى «{curr['verdict']}» بينما ساءت "
                f"كل مؤشرات الدليل: الثقة {pc}→{cc}، المؤشرات المرصودة "
                f"{prev['observed']}→{curr['observed']}، الفجوات المعلنة "
                f"{prev['gaps']}→{curr['gaps']} — الحكم لا يتحرك مع الدليل")
    return {"checked": True, "comparable": True, "inconsistent": inconsistent,
            "previous": prev, "current": curr, "note": note}


def check_against_history(result: dict, *, analysis_id: "int | None" = None,
                          product: "str | None" = None,
                          market_name: "str | None" = None,
                          _list=None, _get=None) -> dict:
    """قارن التشغيلة الحالية بأحدث تشغيلة **مكتملة** سابقة لنفس
    (المنتج × السوق). `_list`/`_get` قابلان للحقن هرمتياً؛ افتراضهما
    مخزنُ التحليلات نفسه. لا سابقةَ = فحص معلَن «لا مقارنة»."""
    if _list is None or _get is None:
        import silk_storage
        _list = _list or silk_storage.list_analyses
        _get = _get or silk_storage.get_analysis
    product = product or str((result or {}).get("product") or "")
    if not market_name:
        mkt = (result or {}).get("market") or {}
        market_name = mkt.get("name_ar") or mkt.get("name_en") or ""
    # درس 191 (§58 الملاحظة 5): المقارنة **داخل النوع نفسه** — صفُّ /analyze
    # أحدث كان يحجب /research أقدم (أحدثية مطلقة، أول مطابقة تفوز)، فيقرأ
    # evidence_stats بلا deep_research ⇒ comparable=False دائماً، ويطبع
    # التقرير «لا تشغيلة سابقة» كاذباً رغم وجودها. النوع من شكل النتيجة الحالية.
    current_kind = "research" if (result or {}).get("deep_research") else "analyze"
    prev_row = None
    for r in _list() or []:
        if analysis_id is not None and r.get("id") == analysis_id:
            continue
        if not (str(r.get("product") or "") == product
                and str(r.get("market_name") or "") == str(market_name)
                and str(r.get("status") or "") == "completed"):
            continue
        rk = r.get("kind")
        if rk is None:
            # صفٌّ قبل عمود kind — يُستنتَج من شكل البلوب كي لا يُقصى تاريخٌ
            # حقيقيّ (نفس صنف العيب المُصلَح: إقصاءٌ صامت بمساواةٍ صارمة).
            rk = "research" if (_get(r["id"]) or {}).get("deep_research") \
                else "analyze"
        if rk != current_kind:
            continue
        prev_row = r
        break
    if prev_row is None:
        return {"checked": True, "comparable": False, "inconsistent": False,
                "note": "لا تشغيلة سابقة مكتملة لنفس المنتج والسوق — "
                        "لا مقارنة اتجاهية"}
    prev_result = _get(prev_row["id"]) or {}
    out = direction_check(evidence_stats(prev_result), evidence_stats(result))
    out["previous_analysis_id"] = prev_row["id"]
    return out
