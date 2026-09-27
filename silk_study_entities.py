"""الجهات المهيكلة وشروط المنافذ لنمط «دراسة السوق» — structured entities (P4-1، P4-3).

> حتمي فوق ما تعيده الأدوات أصلاً (صفوف `importer_leads` ونتائج بحث بعثة القنوات)؛
> لا نداء نموذج ولا توسيع لصيغة إجابة البعثات. كل جهة:
>   {name, type, role, evidence_url, date, product_confirmed}
> التأكيد بالمنتج عبر الحارس القائم `silk_style_contract.lead_product_fit` (الدرس ٢٦٣،
> تقرير ٧ §4.4): «متخصّص» = مؤكَّد؛ «عامّ» = غير مثبت ⇒ يُستبعد بسطرٍ معلَّل؛ مُسقَط
> (مقدّم خدمة/فئة أخرى) ⇒ لا يُذكر. شروط المنافذ من مقتطفات البحث («يشترط…حلال»)
> تدخل سجل الادعاءات بحالة «يُفاد» تلقائياً — لا تُقرَّر أبداً.
"""
from __future__ import annotations

import re

ROLE_CANDIDATE = "مرشح لطلب عرض أسعار"
ROLE_COMPETITOR = "منافس"
ROLE_CHANNEL = "قناة رصد"
ROLE_PARTNER = "شريك محتمل"

_ROLE_WORDS = (
    (ROLE_COMPETITOR, ("roaster", "roastery", "manufacturer", "factory", "producer",
                       "محمصة", "مصنع", "منتج")),
    (ROLE_CHANNEL, ("supermarket", "hypermarket", "grocer", "retail", "chain", "store",
                    "marketplace", "e-commerce", "سلسلة", "متجر", "منصة")),
    (ROLE_CANDIDATE, ("importer", "import", "distributor", "wholesale", "trading",
                      "مستورد", "موزع", "جملة", "تجارة")),
)
_TYPE_BY_ROLE = {ROLE_CANDIDATE: "مستورد/موزع", ROLE_COMPETITOR: "منتج محلي",
                 ROLE_CHANNEL: "منفذ تجزئة", ROLE_PARTNER: "جهة تجارية"}


def _text(*parts) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def role_of(lead: dict) -> str:
    t = _text(lead.get("category"), lead.get("kind"), lead.get("name"), lead.get("desc"))
    for role, words in _ROLE_WORDS:
        if any(w in t for w in words):
            return role
    return ROLE_PARTNER


def _snippets(channel_findings) -> list[dict]:
    out = []
    for f in channel_findings or []:
        v = f.get("value") if isinstance(f, dict) else None
        if isinstance(v, dict):
            out.append({"text": _text(v.get("title"), v.get("snippet"), v.get("description")),
                        "url": v.get("url") or v.get("link"), "date": f.get("retrieved_at")})
    return out


def _join_ar(names: list[str]) -> str:
    return names[0] if len(names) == 1 else "، ".join(names[:-1]) + " و" + names[-1]


def classify(leads, channel_findings, hs: str, product: str, market_iso3: str = "",
             limit: int = 6) -> tuple[list[dict], str | None]:
    """(الجهات المؤكَّدة المصنّفة، سطر الاستبعاد المعلَّل أو None)."""
    from silk_style_contract import EVIDENCE_SPECIALIST, _product_specific_words, lead_product_fit
    snips = _snippets(channel_findings)
    own = [w.lower() for w in _product_specific_words(str(hs or ""), str(product or ""))]
    entities, excluded = [], []
    for lead in leads or []:
        name = str(lead.get("name") or "").strip()
        if not name:
            continue
        ok, _why, status = lead_product_fit(lead, hs, product, market_iso3)
        if not ok:
            continue                       # مقدّم خدمة/فئة أخرى — لا يُذكر أصلاً
        hit = next((s for s in snips if name.lower() in s["text"]
                    and any(w in s["text"] for w in own)), None)
        confirmed = status == EVIDENCE_SPECIALIST or hit is not None
        if not confirmed:
            excluded.append(name)
            continue
        role = role_of(lead)
        entities.append({
            "name": name, "type": _TYPE_BY_ROLE[role], "role": role,
            "desc": str(lead.get("category") or lead.get("kind") or lead.get("desc")
                        or _TYPE_BY_ROLE[role]),
            "evidence_url": (hit or {}).get("url") or lead.get("website") or lead.get("maps_link"),
            "date": (hit or {}).get("date") or lead.get("retrieved_at"),
            "product_confirmed": True,
        })
        if len(entities) >= limit:
            break
    return entities, (_join_ar(excluded) if excluded else None)


# ── P4-3 شروط المنافذ ─────────────────────────────────────────────────────
_REQ = re.compile(r"(requires?|mandatory|يشترط|تشترط|تستلزم)", re.I)
_CERT = re.compile(r"(halal|حلال|certificat|شهادة)", re.I)


def outlet_claims(channel_findings, outlets: list[str]) -> list[dict]:
    """مقتطف يذكر منفذاً مسمّى + اشتراطاً + شهادة ⇒ ادعاء «يُفاد» (لا يُقرَّر)."""
    out: dict[str, dict] = {}
    for s in _snippets(channel_findings):
        m = _REQ.search(s["text"])
        if not m or not _CERT.search(s["text"]):
            continue
        for name in outlets:
            if name and name.lower() in s["text"] and f"outlet_req:{name}" not in out:
                ar = bool(re.search(r"[؀-ۿ]", m.group(1)))
                out[f"outlet_req:{name}"] = {
                    "id": f"outlet_req:{name}",
                    "text": f"{name} يشترط شهادة للتعاقد (مقتطف بحث)",
                    "anchors": [name], "predicate": m.group(1) if ar else "يشترط",
                    "source": s["url"]}
    return list(out.values())
