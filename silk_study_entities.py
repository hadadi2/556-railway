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

# كلمات كاملة (لا مقاطع: «import» ليست «important»، «chain» في «supply chain» ليست
# سلسلة تجزئة). الترتيب: المستورد/الموزع أولاً — «importer & roaster» مرشحٌ لا منافس.
_ROLE_WORDS = (
    (ROLE_CANDIDATE, ("importer", "importers", "distributor", "distributors", "wholesaler",
                      "wholesale", "مستورد", "موزع", "تاجر جملة")),
    (ROLE_COMPETITOR, ("roaster", "roastery", "roasters", "manufacturer", "factory",
                       "محمصة", "مصنع")),
    (ROLE_CHANNEL, ("supermarket", "hypermarket", "grocer", "grocery", "retail chain",
                    "marketplace", "e-commerce", "سلسلة تجزئة", "متجر", "منصة تجارة")),
)
_NOT_CHANNEL = ("supply chain",)
_TYPE_BY_ROLE = {ROLE_CANDIDATE: "مستورد/موزع", ROLE_COMPETITOR: "منتج محلي",
                 ROLE_CHANNEL: "منفذ تجزئة", ROLE_PARTNER: "جهة تجارية"}


def _text(*parts) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![\w؀-ۿ]){re.escape(word)}(?![\w؀-ۿ])",
                     text) is not None


def role_of(lead: dict) -> str:
    t = _text(lead.get("category"), lead.get("kind"), lead.get("name"), lead.get("desc"))
    for bad in _NOT_CHANNEL:
        t = t.replace(bad, " ")
    for role, words in _ROLE_WORDS:
        if any(_has_word(t, w) for w in words):
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
        hit = next((s for s in snips if _has_word(s["text"], name.lower())
                    and any(_has_word(s["text"], w) for w in own)), None)
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
# صيغ المحمول التي يفحصها linter (الجنس والعدد): أي منها بلا تحفّظ = تقرير للادعاء.
OUTLET_PREDICATES = ("يشترط", "تشترط", "يشترطون", "يستلزم", "تستلزم")
_REQ = r"(?:requires|require|required|mandates|mandatory|يشترط|تشترط|يستلزم|تستلزم)(?![\w\u0600-\u06FF])"
_CERT = r"(?:halal|حلال|certificate|certification|شهادة)"
_NEG = re.compile(r"\b(?:not|no|never|unlike|except|without)\b"
                  r"|(?<![؀-ۿ])(?:لا|لم|غير|دون)(?![؀-ۿ])", re.I)


def outlet_claims(channel_findings, outlets: list[str]) -> list[dict]:
    """مقتطف يقول صراحةً «[المنفذ] يشترط … شهادة» في جملة واحدة متقاربة، بلا نفي ولا
    مقارنة ⇒ ادعاء «يُفاد» (لا يُقرَّر أبداً). المنافذ = جهات اجتازت حارس المنتج فقط."""
    out: dict[str, dict] = {}
    for s in _snippets(channel_findings):
        for sent in re.split(r"(?<=[.!?؛])\s+", s["text"]):
            for name in outlets:
                key = f"outlet_req:{name}"
                if not name or key in out:
                    continue
                m = re.search(rf"(?<![\w؀-ۿ]){re.escape(name.lower())}(?![\w؀-ۿ])"
                              rf"(.{{0,40}}?){_REQ}(.{{0,40}}?){_CERT}", sent, re.I)
                if not m or _NEG.search(sent[:m.end()]):
                    continue
                out[key] = {"id": key, "text": f"{name} يشترط شهادة للتعاقد (مقتطف بحث)",
                            "anchors": [name], "predicate": "يشترط",
                            "predicates": list(OUTLET_PREDICATES), "source": s["url"]}
    return list(out.values())
