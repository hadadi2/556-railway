"""سجل ادعاءات نمط «دراسة السوق» — claims registry (P3-1).

> كل ادعاء في الدراسة يحمل حالةً واحدة ثابتة عبر الأقسام والجداول:
>   documented    موثّق بمصدر (رقم من مصدر رسمي)
>   reported      «يُفاد» — معلومة تجارية غير مستندة إلى وثيقة منشورة
>   gap           فجوة معلنة (مع الجهة القادرة على استكمالها)
>   estimate_rule قاعدة تقديرية (مثل 40–45% من سعر الرف)
>   forecast      توقع
> السجل يُبنى حتمياً من الحالة (`silk_study_case.build_case`) وملف المعرفة، ويُمرَّر
> للكاتب/الفراغات، ويفحص linter (`conflicts`) أن ادعاءً «يُفاد» لم يُقرَّر في موضع آخر.
"""
from __future__ import annotations

import re

STATUSES = ("documented", "reported", "gap", "estimate_rule", "forecast")
# ما يجعل جملةً تحفّظاً لا تقريراً.
HEDGES = ("يُفاد", "يفاد", "يُتحقق", "يتعين التحقق", "غير مستندة", "غير مثبت",
          "لم يُتحقق", "مؤقت", "يُستوضح", "إن صحّ", "وفق ما يُفاد")


def claim(cid: str, status: str, text: str = "", source: str | None = None,
          owner: str | None = None, anchors=(), predicate: str | None = None) -> dict:
    if status not in STATUSES:
        raise ValueError(f"حالة ادعاء غير معروفة: {status}")
    return {"id": cid, "status": status, "text": text, "source": source, "owner": owner,
            "anchors": list(anchors), "predicate": predicate}


def build_claims(case: dict, knowledge: dict | None = None) -> list[dict]:
    """السجل الكامل للحالة — حتمي، بلا نداء."""
    out: list[dict] = []
    imp = case.get("imports") or {}
    if imp.get("series"):
        out.append(claim("imports_series", "documented", "سلسلة الواردات السنوية",
                         source=imp.get("source") or "UN Comtrade"))
    sup = case.get("suppliers") or {}
    if sup.get("top"):
        out.append(claim("supplier_shares", "documented", "حصص الموردين", source="UN Comtrade"))
    tar = case.get("tariff") or {}
    if tar.get("status") and tar.get("status") != "gap":
        out.append(claim("tariff", "documented", "الرسم الجمركي", source=tar.get("source")))
    for c in case.get("claims_reported") or []:
        out.append({**claim(c["id"], "reported", c.get("text", ""), anchors=c.get("anchors") or (),
                            predicate=c.get("predicate"), source=c.get("source")),
                    "predicates": c.get("predicates")})
    for g in case.get("gaps") or []:
        label, owner = (g.get("label"), g.get("owner")) if isinstance(g, dict) else (g, None)
        out.append({**claim("gap:" + label, "gap", label, owner=owner),
                    "live": bool(case.get("live"))})
    d = case.get("decision") or {}
    if d.get("landed_low_pct") is not None:
        out.append(claim("landed_share_rule", "estimate_rule",
                         f"التكلفة الواصلة {d['landed_low_pct']}–{d.get('landed_high_pct')}% من سعر الرف"))
    if d.get("provisional_threshold_usd") is not None:
        out.append(claim("provisional_threshold", "estimate_rule",
                         f"حد مؤقت {d['provisional_threshold_usd']} دولاراً للكيلوغرام"))
    return out


_SENT = re.compile(r"(?<=[.؛!؟])\s+|\n+|\s*\|\s*")


def conflicts(md: str, claims: list[dict]) -> list[dict]:
    """ادعاء «يُفاد» مذكور بصيغة تقرير (مرساة + محمول بلا تحفّظ) في أي جملة/خلية → مخالفة."""
    v: list[dict] = []
    for c in claims or []:
        # P3-3: فجوة في حالة حية بلا جهة استكمال — الختام يدّعي ذكرها.
        if c.get("status") == "gap" and c.get("live") and not c.get("owner"):
            v.append({"rule": "gap_without_owner", "detail": c["text"]})
    for c in claims or []:
        if c.get("status") != "reported" or not c.get("anchors") or not c.get("predicate"):
            continue
        # المحمول كلمةً كاملة غير منفية («لا تشترط»/«تشترطها» ليسا تقريراً للادعاء).
        forms = "|".join(re.escape(p) for p in (c.get("predicates") or [c["predicate"]]))
        pred = re.compile(r"(?<![\u0600-\u06FF])(?<!لا )(?<!لم )(?:" + forms + r")(?![\u0600-\u06FF])")
        for sent in _SENT.split(md):
            if (pred.search(sent) and any(a in sent for a in c["anchors"])
                    and not any(h in sent for h in HEDGES)):
                v.append({"rule": "claim_status_conflict",
                          "detail": f"{c['id']}: «{sent.strip()[:70]}» يقرّر ما هو «يُفاد»"})
    return v
