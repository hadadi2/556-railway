"""تقرير أحجام الموجّهات وخريطة كلفة البعثات — هدف الدراسة الاحترافية، البند ٨.

قياسٌ قبل أي قطع (قاعدة الموجة ٨): يلتقط **هرمتياً** حجم موجّهي الكاتب
والمحلل ومدخلاتهما على مدوّنة قياسية (صفر نداء مدفوع — المزوّد مرقَّع)،
ويقرأ `cost_usd_by_mission` من دراسة مخزّنة (`?economics=1`) موسِماً
البعثات المغذّية للأعمدة (القاعدة الصلبة: لا قطع لأي منها).

    python3 tools/prompt_size_report.py --blob kuwait
    python3 tools/prompt_size_report.py --economics run.json
    python3 tools/prompt_size_report.py --db data/silk.db --id 14
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from unittest.mock import patch

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
for p in (_REPO_ROOT, _TOOLS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

# البعثات المغذّية لأعمدة القرار — منسوخة من قراءات
# `silk_deep_pillars.build_pillar_inputs` (اختبار الموجة ٨ يقفل التطابق
# ضد المصدر بمسح AST فلا تنجرف الخريطة صامتة).
PILLAR_FEEDING_MISSIONS = frozenset({
    "trade_flow", "competitors", "tariffs_agreements", "risk_news",
    "logistics", "demographics_economy", "customs_requirements",
})


def _blob(key: str) -> dict:
    import importlib
    from gen_verdict_baseline import CANONICAL_BLOBS
    matches = [k for k in CANONICAL_BLOBS if key in k]
    if not matches:
        raise SystemExit(f"لا مدوّنة تطابق «{key}» — المتاح: "
                         + "، ".join(sorted(CANONICAL_BLOBS)))
    mod, fn = CANONICAL_BLOBS[sorted(matches)[0]]
    return getattr(importlib.import_module(mod), fn)()


def measure_prompts(blob_key: str = "kuwait") -> dict:
    """أحجام كل نداء كلود في مسارَي المحلل والكاتب على المدوّنة — بالحرف
    (التوكن ≈ الحرف/4 تقريبٌ معلن لا قياس مزوّد). `system` هو البادئة
    القابلة للكاش (المزوّد يعلّمها `cache_control` — PR #68)."""
    blob = _blob(blob_key)
    dr = blob.get("deep_research") or {}
    missions = dr.get("missions") or {}
    calls: list[dict] = []

    def _rec(stage, system, user_len, model, cache_prefix=0):
        calls.append({"stage": stage, "system_chars": len(system or ""),
                      "input_chars": user_len, "model": model or "(افتراضي)",
                      "cache_prefix_chars": cache_prefix or 0})

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None,
                  **kw):
        import silk_ai_judge
        _pref = silk_ai_judge._cache_prefix_text.get() or ""
        _rec("writer/_call", system, len(user or ""), model,
             len(_pref) if (user or "").startswith(_pref) and _pref else 0)
        return ("## 1. الخلاصة التنفيذية\nالتوصية: قياس هرمتي — نص مموّه "
                "لالتقاط الحجم لا للتسليم.\n")

    def fake_tools(system, messages, tools=None, max_tokens=1600, model=None,
                   timeout=None, **kw):
        u = sum(len(json.dumps(m, ensure_ascii=False)) for m in (messages or []))
        u += len(json.dumps(tools or [], ensure_ascii=False))
        _rec("analyst/_call_tools", system, u, model)
        return {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": json.dumps(
                {"findings": [], "gaps": [], "summary": "قياس"},
                ensure_ascii=False)}]}

    from silk_market_resolver import resolve_market
    ref, _ = resolve_market(dr.get("market_name") or "Kuwait")
    product = str(blob.get("product") or "منتج")
    # المحلل يتوقع كائنات AgentReport حية — المدونات تخزّن dict (شكل القرص):
    # محوِّل قراءة فقط، نفس عقد الحقول.
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint

    def _revive(m: dict) -> AgentReport:
        fs = [DataPoint(f.get("value"), f.get("source", ""),
                        f.get("confidence", 0.0), f.get("note", ""),
                        f.get("retrieved_at", ""))
              for f in (m.get("findings") or [])]
        return AgentReport(m.get("agent_name", ""), fs,
                           bool(m.get("failed")), m.get("summary", ""))

    live_missions = {k: (_revive(m) if isinstance(m, dict) else m)
                     for k, m in missions.items()}
    out: dict = {"blob": blob_key, "calls": calls, "errors": {}}
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "hermetic-measure"}), \
            patch("silk_llm_runtime._call_tools", side_effect=fake_tools), \
            patch("silk_ai_judge._call", side_effect=fake_call):
        try:
            from silk_market_analyst import analyze_market
            analyze_market(ref, product, live_missions,
                           hs_code=blob.get("hs_code"))
        except Exception as exc:  # noqa: BLE001 — يُعلَن لا يُخفى
            out["errors"]["analyst"] = repr(exc)
        try:
            from silk_ai_judge import write_reviewed_report
            write_reviewed_report(missions, "ملخّص قياس", dr.get("verdict")
                                  or {}, product, ref.name_en,
                                  hs_code=blob.get("hs_code"))
        except Exception as exc:  # noqa: BLE001
            out["errors"]["writer"] = repr(exc)
    tot_sys = sum(c["system_chars"] for c in calls)
    tot_in = sum(c["input_chars"] for c in calls)
    tot_cache = sum(c["cache_prefix_chars"] for c in calls) + tot_sys
    out["totals"] = {
        "calls": len(calls), "system_chars": tot_sys, "input_chars": tot_in,
        "approx_tokens": round((tot_sys + tot_in) / 4),
        "cacheable_prefix_share_pct": round(
            100 * tot_cache / (tot_sys + tot_in), 1) if (tot_sys + tot_in)
        else 0.0,
    }
    # التوفير المتوقع (هرمتي: خفض توكنز × تسعيرة — لا ادعاء قياس حي):
    # كل نداء تنقيح/تصعيد يعيد قراءة بادئة الكاتب المكاشة بعُشر السعر.
    try:
        from silk_pricing import MODEL_PRICING
        _p_in = MODEL_PRICING.get("claude-opus-4-8", {}).get("input")
        if _p_in:
            _writer_prefix_tok = max(
                (c["cache_prefix_chars"] for c in calls), default=0) / 4
            out["totals"]["expected_saving_usd_per_extra_writer_call"] = round(
                _writer_prefix_tok / 1_000_000 * _p_in * 0.9, 4)
    except Exception:  # noqa: BLE001 — التسعير قناة تقديرية معلنة
        pass
    return out


def cost_map(economics: dict) -> list[str]:
    """أسطر خريطة الكلفة من `data_economics` دراسةٍ مخزّنة — مع وسم البعثات
    المغذّية للأعمدة وأرخص رقم آمن (لا قطع لبعثة مغذّية)."""
    lines: list[str] = []
    by_mission = economics.get("cost_usd_by_mission") or {}
    total = economics.get("cost_usd_estimate")
    if not by_mission:
        lines.append("cost_usd_by_mission فارغة — تشغيلة سابقة لوسم البعثات "
                     "(فجوة معلنة، لا اختلاق)")
    pillar_cost = other_cost = 0.0
    for k, v in sorted(by_mission.items(), key=lambda kv: -float(kv[1] or 0)):
        feeds = k in PILLAR_FEEDING_MISSIONS
        tag = "تغذي عموداً — لا تُقطع" if feeds else "لا تغذي عموداً"
        lines.append(f"  {k}: ${float(v or 0):.4f} ({tag})")
        if feeds:
            pillar_cost += float(v or 0)
        else:
            other_cost += float(v or 0)
    if by_mission:
        missions_cost = pillar_cost + other_cost
        lines.append(f"— بعثات مغذّية: ${pillar_cost:.4f}؛ غير مغذّية: "
                     f"${other_cost:.4f}")
        if total is not None:
            tail = max(0.0, float(total) - missions_cost)
            lines.append(f"— الذيل (محلل+توليف+كاتب+مراجع): ${tail:.4f} "
                         f"من إجمالي ${float(total):.4f}")
            lines.append(
                "— أرخص رقم آمن (القاعدة الصلبة): البعثات المغذّية "
                f"${pillar_cost:.4f} + كاتب/محلل حدّهما الأدنى — الذيل "
                "والبعثات غير المغذّية هما مجال التخفيض الوحيد")
    if economics.get("early_halt"):
        lines.append("— هذه التشغيلة أوقِفت مبكراً (SILK_EARLY_HALT): الذيل "
                     "المدفوع لم يُنفق")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--blob", nargs="?", const="kuwait")
    g.add_argument("--economics", help="ملف JSON لنتيجة ?economics=1")
    g.add_argument("--db", help="قاعدة sqlite (قراءة فقط)")
    ap.add_argument("--id", help="معرّف الدراسة مع --db")
    args = ap.parse_args()
    if args.blob:
        r = measure_prompts(args.blob)
        print(f"■ أحجام الموجّهات (هرمتي، مدوّنة {r['blob']}) — "
              "بالحرف؛ التوكن ≈ حرف/4 (تقريب معلن):")
        for c in r["calls"]:
            print(f"  {c['stage']} [{c['model']}]: system={c['system_chars']:,} "
                  f"input={c['input_chars']:,}")
        t = r["totals"]
        print(f"— {t['calls']} نداء؛ system={t['system_chars']:,} "
              f"input={t['input_chars']:,} ≈ {t['approx_tokens']:,} توكن؛ "
              f"بادئة قابلة للكاش {t['cacheable_prefix_share_pct']}%")
        if t.get("expected_saving_usd_per_extra_writer_call") is not None:
            print("— توفير متوقع لكل نداء كاتب إضافي (تنقيح/تصعيد) من كاش "
                  f"البادئة: ${t['expected_saving_usd_per_extra_writer_call']}"
                  " (خفض توكنز × تسعيرة — تقدير هرمتي، القياس الحي بنقرة "
                  "المالك ?economics=1)")
        for k, v in (r["errors"] or {}).items():
            print(f"⚠ {k}: {v}")
        return
    if args.economics:
        with open(args.economics, encoding="utf-8") as fh:
            blob = json.load(fh)
        eco = blob.get("data_economics") or blob
    else:
        if not args.id:
            raise SystemExit("--db يتطلب --id")
        uri = f"file:{os.path.abspath(args.db)}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            row = con.execute("SELECT json_blob FROM analyses WHERE id=?",
                              (args.id,)).fetchone()
        finally:
            con.close()
        if not row:
            raise SystemExit(f"لا دراسة بالمعرّف {args.id}")
        eco = (json.loads(row[0]) or {}).get("data_economics") or {}
    print("■ خريطة كلفة البعثات:")
    for ln in cost_map(eco):
        print(ln)


if __name__ == "__main__":
    main()
