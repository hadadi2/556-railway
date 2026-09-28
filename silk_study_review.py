"""حلقة مراجعة «دراسة السوق» المحدودة — bounded study review loop (P5-2…P5-6).

> الجولة 0: ملء فراغات (ب)/(ج) (`silk_study_export.fill_slots`) ثم مراجعة مستقلة بمعيار
> مكتوب (`silk_ai_judge.review_study`). جولتان كحدّ أقصى بعدها: يُعاد **فقط** الفراغ ذو
> ملاحظة حرجة/عالية، بتغذية المراجع، ويمرّ بالفحوص الحتمية نفسها (`Renderer._slot_ok`).
> فقرات (أ) والأرقام والجداول لا تُمس: ملاحظاتها تُسجَّل للمطوّر في `silk_ops_log`.
> التوقف عند ≥9 أو نفاد الجولات أو رفض الحارس (سقف الذيل/الميزانية/الإلغاء).
> يُسلَّم **أفضل إصدار** بدرجته، ويُحدَّد سلّم التسليم منها. بلا فراغات = بلا مراجعة.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

STOP_SCORE = 9.0
REWRITE_SEVERITIES = ("critical", "high")


def delivery_tier(score: float | None, notes: list[dict] | None) -> dict:
    """P5-6: ≥9 عادي؛ 8–9 عادي + الملاحظات المتوسطة حدودٌ معلنة؛ <8 أو بلا درجة عادي +
    تنبيه مراجعة بشرية + علم «إصدار محدَّث مجاني». التسليم لا يُحجب في أي حال."""
    if score is not None and score >= STOP_SCORE:
        return {"tier": "ready", "human_review": False, "free_update": False, "limits": []}
    if score is not None and score >= 8.0:
        lim = [n["fix"] for n in notes or [] if n.get("severity") == "medium" and n.get("fix")]
        return {"tier": "limits", "human_review": False, "free_update": False, "limits": lim}
    return {"tier": "human_review", "human_review": True, "free_update": True, "limits": []}


def _log_non_slot(notes: list[dict], slot_ids: set[str]) -> None:
    import silk_ops_log
    for n in notes:
        if n["location"] in slot_ids:
            continue
        kind = "template_error" if n["location"].startswith("#") else "data_error"
        try:
            silk_ops_log.record_error(kind, f"{n['severity']}: {n['fix'][:300]}",
                                      {"location": n["location"][:120]})
        except Exception as e:  # noqa: BLE001 — السجل قناة جانبية
            log.warning("study review note not logged: %s", e)


def run_study_tail(case: dict, knowledge: dict | None, fill, review, guard=None,
                   max_rounds: int = 2, facts: str = "") -> dict:
    from silk_study_export import fill_slots
    from silk_study_render import Renderer, load_exemplars, load_templates
    from silk_style_contract import study_slot_prompt
    guard = guard or (lambda: True)
    slots = fill_slots({"study_case": case}, fill, guard=guard)
    out = {"slots": slots, "score": None, "notes": [], "rounds": 0, "versions": [],
           "tail_capped": False}
    if not slots:
        out["delivery"] = {"tier": "no_slots", "human_review": False, "free_update": False, "limits": []}
        return out

    def render(sl: dict) -> tuple[str, Renderer]:
        r = Renderer(case, knowledge, llm_fill=lambda sid, _p: sl.get(sid), review_marks=True)
        return r.render(), r

    def do_review(sl: dict) -> dict | None:
        if not guard():
            out["tail_capped"] = True
            return None
        return review(render(sl)[0], facts)

    rev = do_review(slots)
    versions = [{"round": 0, "score": (rev or {}).get("score"), "notes": (rev or {}).get("notes") or [],
                 "slots": dict(slots)}]
    briefs = load_templates().get("llm_briefs") or {}
    ex = load_exemplars()
    cur = dict(slots)
    for rnd in range(1, max_rounds + 1):
        if rev is None or rev["score"] >= STOP_SCORE:
            break
        _log_non_slot(rev["notes"], set(cur))
        targets = {n["location"]: n["fix"] for n in rev["notes"]
                   if n["severity"] in REWRITE_SEVERITIES and n["location"] in cur}
        if not targets:
            break
        _md, checker = render(cur)
        nxt = dict(cur)
        for sid, fix in targets.items():
            if not guard():
                out["tail_capped"] = True
                break
            prompt = (study_slot_prompt(briefs.get(sid, sid), ex.get(sid))
                      + f" — ملاحظة المراجع: {fix}")
            txt = fill(sid, prompt)
            if txt and checker._slot_ok(txt, sid) is None:
                nxt[sid] = txt
        if nxt == cur:
            break
        cur = nxt
        rev = do_review(cur)
        versions.append({"round": rnd, "score": (rev or {}).get("score"),
                         "notes": (rev or {}).get("notes") or [], "slots": dict(cur)})
        out["rounds"] = rnd
        if out["tail_capped"]:
            break
    if rev is not None:
        _log_non_slot(rev["notes"], set(cur))
    # P5-4: أفضل إصدار — أعلى درجة؛ التعادل للأبكر؛ بلا درجة أدنى من أي درجة.
    best = max(versions, key=lambda v: (v["score"] if v["score"] is not None else -1, -v["round"]))
    out.update(slots=best["slots"], score=best["score"], notes=best["notes"],
               best_round=best["round"],
               versions=[{"round": v["round"], "score": v["score"]} for v in versions],
               delivery=delivery_tier(best["score"], best["notes"]))
    return out
